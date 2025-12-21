class Node:
    """
    计算节点类：封装了 UI 节点的几何信息与物理特性。
    在计算引擎中，节点是压力的载体。
    """

    def __init__(self, data: dict):
        # 基础属性：从 temporary_data.json 中读取
        self.id = data.get("label", "")
        self.type = data.get("ptype", "normal")  # 节点类型: normal(普通), pump(油泵), valve(阀门), tee(三通), tank(油箱)
        self.x = float(data.get("x", 0))
        self.y = float(data.get("y", 0))
        self.elevation = float(data.get("elevation", 0) or 0)  # 节点高程 (m)

        # 物理状态量 (计算引擎实时更新)
        self.pressure = 0.0  # 节点的静压力 (Pa)
        self.flow_net = 0.0  # 节点的净流量 (m³/s)

        # --- 油箱数据 (如果是油箱) ---
        self.fluid_data = data.get("fluid_data", {})

        # --- 动力源 (泵) 参数解析 ---
        # 这里的解析逻辑决定了油泵在计算中是以“恒流源”还是“压力-流量曲线”的形式存在
        self.pump_mode = None
        self.pump_params = {}
        
        if self.type == 'pump':
            p_type_str = data.get("pump_type", "gear") # gear: 容积泵(齿轮泵) / curve: 离心泵
            
            if p_type_str == "gear":
                # === 容积式泵 (恒流模型) ===
                # 特点：在额定压力范围内提供几乎恒定的流量
                self.pump_mode = "constant_flow"
                q_m3h = float(data.get("pump_flow", 0) or 0)
                self.pump_params = {
                    "Q_source": q_m3h / 3600.0, # 换算为 SI 单位 m³/s
                    "P_max": float(data.get("pump_head", 0) or 0) * 1e3 # kPa -> Pa (额定最大压力)
                }
            else:
                # === 离心泵 (P-Q 曲线模型) ===
                # 特点：升压能力随流量增大而下降
                self.pump_mode = "curve"
                H_rated_kpa = float(data.get("pump_head", 500)) # 额定压力 (kPa)
                Q_rated_m3h = float(data.get("pump_flow", 10)) # 额定流量 (m³/h)
                # 离心泵的关键参数：关死扬程 (流量为0时的压力)
                H_shutoff_kpa = float(data.get("pump_speed", H_rated_kpa * 1.2) or H_rated_kpa * 1.2)
                
                # 预计算二次曲线系数: P = A - B*Q²
                # A = 关死压力
                # B = (A - 额定压力) / 额定流量²
                Q_rated_si = Q_rated_m3h / 3600.0
                B_coeff = 0.0
                if Q_rated_si > 1e-6:
                    B_coeff = (H_shutoff_kpa - H_rated_kpa) / (Q_rated_si ** 2)
                
                self.pump_params = {
                    "A": H_shutoff_kpa * 1e3, # Pa
                    "B": B_coeff * 1e3       # Pa/(m³/s)²
                }

        # 阀门与元件属性
        self.valve_cv = float(data.get("valve_k", 0) or 0)  # 阀门额定 Cv
        self.valve_open = float(data.get("valve_open", 100) or 100) / 100.0 # 当前开度 (0~1)
        self.tee_k = float(data.get("tee_k", 0) or 0)      # 三通局部阻力系数

        # 拓扑索引
        self.matrix_idx = -1


class Pipe:
    """
    计算管路类：连接两个节点的直线，是压力损失（能量耗散）的主要载体。
    """

    def __init__(self, data: dict):
        self.id = data.get("label", "")
        self.start_node_id = data.get("start_label", "")
        self.end_node_id = data.get("end_label", "")
        self.remark = data.get("remark", "") # 获取备注，用于识别吸油管等特殊管路

        # 几何参数：计算压力损失的核心依据
        raw_dia = float(data.get("diameter", 0) or 0.040)  # 默认 40mm
        self.diameter = raw_dia / 1000.0  # UI 单位为 mm，计算必须换算为 m

        raw_len = float(data.get("length", 0) or 10.0)    # 默认 10m
        self.length = raw_len  # m

        # 绝对粗糙度 (m): 工业常用碳钢管取 0.045mm，影响湍流区的摩阻系数
        self.roughness = 0.045e-3 

        # 物理量 (计算引擎更新)
        self.flow = 0.0  # 流量 (m³/s)
        self.velocity = 0.0  # 流速 (m/s)
