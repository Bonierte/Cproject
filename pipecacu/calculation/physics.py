import math

class Fluid:
    """
    流体物性类：管理油品的密度、粘度等物理属性。
    在 LAHI 算法中，流导 G 的计算高度依赖于流体的运动粘度 nu。
    """
    OIL_DATABASE = {
        "VG320 滑油": {"rho_15": 920.0, "v_40": 347.8, "v_100": 25.0},
        "VG220 滑油": {"rho_15": 900.0, "v_40": 244.4, "v_100": 19.0},
        "VG46 液压油": {"rho_15": 875.0, "v_40": 46.0, "v_100": 6.8},
        "自定义": {"rho_15": 860.0, "v_40": 40.0, "v_100": 6.0}
    }

    def __init__(self, name="VG320 滑油", temp=40.0):
        self.name = name
        self.temp = temp # 摄氏度
        self.rho = 900.0 # 密度 kg/m³
        self.mu = 0.0288 # 动力粘度 Pa·s
        self.nu = 0.000032 # 运动粘度 m²/s
        self.update_properties()

    def update_properties(self):
        """
        根据选择的油品更新物性参数。
        换算公式：
        1 cSt = 10^-6 m²/s (运动粘度)
        mu (动力粘度) = nu (运动粘度) * rho (密度)
        """
        data = self.OIL_DATABASE.get(self.name, self.OIL_DATABASE["自定义"])
        
        # 密度取 15℃ 基准值 (项目中不考虑温度引起的膨胀)
        self.rho = data.get("rho_15", 900.0)
        
        # 将运动粘度从 cSt 转换为 SI 单位 m²/s
        v40 = data.get("v_40", 40.0)
        self.nu = v40 * 1e-6
        
        # 计算动力粘度 (用于雷诺数 Re 相关的压力损失计算)
        self.mu = self.nu * self.rho

def calc_reynolds(v: float, D: float, nu: float) -> float:
    """
    计算雷诺数 (Reynolds Number): Re = v * D / nu
    雷诺数决定了流态（层流/湍流），从而影响摩擦系数。
    v: 流速 (m/s), D: 管径 (m), nu: 运动粘度 (m²/s)
    """
    if abs(v) < 1e-9: return 0.0
    return abs(v * D / nu)

def calc_friction_factor(re: float, roughness: float, diameter: float) -> float:
    """
    计算达西摩阻系数 lambda (Darcy Friction Factor)
    采用 Churchill (1977) 全流态关联式：
    该公式能够平滑地过渡层流、临界区和湍流区，避免数值计算中的间断。
    re: 雷诺数, roughness: 绝对粗糙度, diameter: 管径
    """
    if re < 1e-3: return 64.0 / 1e-3 # 极低雷诺数处理
    
    # Churchill 公式的内部系数
    A = (2.457 * math.log(1.0 / ((7.0 / re)**0.9 + 0.27 * (roughness / diameter))))**16
    B = (37530.0 / re)**16
    
    # 摩擦系数 f (即 lambda)
    f = 8.0 * ((8.0 / re)**12 + 1.0 / (A + B)**1.5)**(1.0 / 12.0)
    return f

def calc_pipe_conductance(pipe, fluid: Fluid, dP: float) -> float:
    """
    核心物理模型：计算直管的等效流导 G (m³/s/Pa)
    原理：基于 Darcy-Weisbach 方程: dP = lambda * (L/D) * (rho*v²/2)
    反推流量 Q = Area * v = G * dP
    推导得出：G = Area * sqrt( 2*D / (lambda * L * rho * |dP|) )
    dP: 压差 (Pa), fluid: 流体物性对象
    """
    # 极小压差下的数值处理：不再强行切断，而是切换为层流解析解
    # 层流下 G = (pi * D^4) / (128 * mu * L)
    if abs(dP) < 1.0: 
        g_laminar = (math.pi * pipe.diameter**4) / (128.0 * fluid.mu * pipe.length)
        return max(g_laminar, 1e-10)
    
    D = pipe.diameter
    L = pipe.length
    area = math.pi * (D**2) / 4.0
    
    # 1. 估算当前流速 (用于计算雷诺数)
    # 初始 lambda 假设为 0.03
    v = math.sqrt((2.0 * D * abs(dP)) / (0.03 * L * fluid.rho))
    
    # 2. 计算雷诺数和真实的摩阻系数
    re = calc_reynolds(v, D, fluid.nu)
    f = calc_friction_factor(re, pipe.roughness, D)
    
    # 3. 计算等效流导 G = Q / dP
    denominator = f * L * fluid.rho * abs(dP)
    if denominator < 1e-12: return 1e-8
    
    g = area * math.sqrt((2.0 * D) / denominator)
    return max(g, 1e-10) # 确保 G 不为 0，防止矩阵奇异

def calc_local_conductance(k: float, diameter: float, fluid: Fluid, dP: float) -> float:
    """
    计算局部阻力元件（如弯头、三通）的流导 G
    原理：dP = K * (rho * v² / 2)
    Q = Area * v = Area * sqrt( 2 * dP / (K * rho) )
    故 G = Area * sqrt( 2 / (K * rho * |dP|) )
    k: 局部阻力系数 (无量纲)
    """
    if abs(dP) < 1e-2 or k <= 0: return 1e-5
    
    area = math.pi * (diameter**2) / 4.0
    denominator = k * fluid.rho * abs(dP)
    
    if denominator < 1e-12: return 1e-5
    
    g = area * math.sqrt(2.0 / denominator)
    return max(g, 1e-10)

def calc_valve_conductance(node, fluid: Fluid, dP: float) -> float:
    """
    计算阀门的流导 G
    采用 ISA-75.01 标准公式简化版：
    Q = Cv * N * sqrt( dP / SG )，其中 SG 是流体相对于水的比重。
    """
    if abs(dP) < 1e-2: return 1e-8
    
    sg = fluid.rho / 1000.0 # 相对密度
    n_si = 1.156e-7         # Cv 到 SI 单位的换算系数
    
    # 考虑开度影响的有效 Cv
    cv_eff = node.valve_cv * node.valve_open
    
    # G = Q / dP = (Cv * N / sqrt(dP * SG))
    g = (cv_eff * n_si) / math.sqrt(sg * abs(dP))
    return max(g, 1e-10)

def calc_pump_pressure_delta(node, flow: float) -> float:
    """
    泵的升压特性模型
    1. 容积泵 (constant_flow): 提供恒定流量 Q_source。
    2. 离心泵 (curve): 遵循 H-Q 曲线 P = A - B * Q²。
    """
    if node.pump_mode == "constant_flow":
        # 对于容积泵，其在 LAHI 算法中主要作为源项注入 Q 向量。
        # 此处返回其额定升压能力，用于物理审计步的参考。
        return node.pump_params.get("P_max", 0)

    elif node.pump_mode == "curve":
        # 离心泵 P-Q 曲线模型
        # A 为关死压力，B 为阻力系数
        a = node.pump_params.get("A", 0)
        b = node.pump_params.get("B", 0)
        
        # 升压随着流量增大而减小
        dp = a - b * (flow ** 2)
        return max(0.0, dp)
        
    return 0.0
