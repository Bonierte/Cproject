import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.linalg import spsolve
from .topology import NetworkGraph
from .physics import (
    Fluid, calc_pipe_conductance, calc_valve_conductance, 
    calc_local_conductance, calc_pump_pressure_delta
)

class LAHISolver:
    """
    LAHI (Linearized Alternative Hydraulic Iteration) 求解器
    实现原理：
    1. 线性预测层：假设各元件流导 G 为常数，通过矩阵 GP = Q 快速计算全场初始压力场。
    2. 局部物理审计：在给定压力场下，利用高精度的非线性物理公式（Darcy, Churchill等）计算各元件的“真实流量”。
    3. 流导修正层：对比线性预测流量与真实流量的差异，通过松弛因子 omega 修正流导 G，进入下一轮迭代。
    """
    def __init__(self, graph: NetworkGraph):
        self.graph = graph
        self.fluid = Fluid()  # 默认物性
        
        # 算法配置
        self.tolerance = 1e-6      # 收敛容差：节点质量流量残差 (kg/s)
        self.max_iter = 50         # 最大迭代步数
        self.omega = 0.8           # 初始松弛因子
        self.min_omega = 0.1       # 最小松弛因子
        self.max_omega = 1.0       # 最大松弛因子
        
        # 状态存储 - 使用拓扑分配的实际计算位总数
        self.num_nodes = graph.num_total_indices 
        self.P = np.ones(self.num_nodes) * 1.01325e5  # 压力向量 (Pa)
        self.G_map = {}  # 存储管路/元件当前的等效流导
    
    def _init_conductance(self):
        """
        初始化流导。为防止矩阵奇异，初始给予一个极小的经验流导。
        """
        for pipe in self.graph.pipes:
            self.G_map[pipe.id] = 1e-6
        
        for node in self.graph.nodes:
            if node.type in ["valve", "tee"]:
                self.G_map[f"node_{node.id}"] = 1e-6

    def solve(self):
        """执行 LAHI 迭代求解主循环"""
        if self.num_nodes == 0:
            print("LAHI Error: 节点数为 0，取消计算。")
            return False, {}

        self._init_conductance()
        prev_residual_norm = float('inf')
        
        # 打印仿真元数据
        print("\n" + "="*50)
        print("LAHI 求解器启动...")
        print(f"网络规模: {self.num_nodes} 节点, {len(self.graph.pipes)} 管路")
        print(f"流体: {self.fluid.name}, 密度={self.fluid.rho}kg/m³")
        print("="*50)

        for it in range(self.max_iter):
            # --- 第一步：线性预测步 (Linear Prediction) ---
            # 组装线性方程组 GP = Q
            G_matrix, Q_source = self._assemble_system()
            
            # 求解大型稀疏矩阵方程 GP = Q 得到压力分布 P
            try:
                self.P = spsolve(G_matrix.tocsr(), Q_source)
            except Exception as e:
                print(f"LAHI Error: 矩阵求解失败 (检查拓扑孤岛) - {e}")
                return False, {}

            # 数值保护：负压截止 (物理上系统压力通常不低于大气压)
            self.P = np.maximum(self.P, 100.0) 

            # --- 第二步：局部物理审计 (Local Physical Audit) ---
            # 利用非线性公式计算当前压力场下的“真实物理流量”和“质量守恒残差”
            real_flows, residuals = self._audit_physics()
            
            # 忽略大气压参考点的残差（该点作为系统的平衡油箱）
            ref_idx = self._find_reference_index()
            residuals[ref_idx] = 0.0 
            
            # 计算当前系统的最大不平衡量 (无穷范数)
            residual_norm = np.linalg.norm(residuals, np.inf)
            
            # 实时反馈迭代进度
            print(f"迭代 [{it+1:3d}]: 残差 = {residual_norm:.4e}, 松弛因子 omega = {self.omega:.2f}")
            
            # 判断是否满足收敛条件
            if residual_norm < self.tolerance:
                print("="*50)
                print(f"LAHI: 求解成功！收敛于第 {it+1} 步。")
                
                results = self._format_results(real_flows)
                # 打印摘要到终端
                self._print_terminal_summary(results)
                
                return True, results

            # --- 第三步：自适应策略 (Adaptive Strategy) ---
            # 论文 4.2.3：如果残差变大，减小松弛因子（抑制震荡）；如果变小，增大（加速收敛）。
            if residual_norm > prev_residual_norm:
                self.omega = max(self.min_omega, self.omega * 0.5)
            else:
                self.omega = min(self.max_omega, self.omega * 1.1)
            
            prev_residual_norm = residual_norm

            # --- 第四步：等效流导更新 (Conductance Update) ---
            # 基于本次计算的真实物理流量，反推下一轮矩阵中使用的等效流导 G
            self._update_conductance(real_flows)

        print(f"LAHI: 达到最大迭代次数 {self.max_iter}，计算未收敛。")
        return False, {}

    def _find_reference_index(self):
        """寻找系统中作为基准的大气压点。现在优先选择泵的入油口。"""
        # 策略：寻找第一个泵的入油口作为全局大气压参考点
        for node in self.graph.nodes:
            if node.type == "pump" and node.inlet_idx is not None:
                return node.inlet_idx
        
        # 兜底：寻找第一个普通节点
        for node in self.graph.nodes:
            if node.type != "pump":
                return node.matrix_idx
        return 0

    def _assemble_system(self):
        """组装线性方程组 G * P = Q"""
        n = self.num_nodes
        G = lil_matrix((n, n))
        Q = np.zeros(n)

        # 1. 填充管路流导项
        for pipe in self.graph.pipes:
            i, j = pipe.start_idx, pipe.end_idx
            g = self.G_map.get(pipe.id, 1e-6)
            G[i, i] += g
            G[j, j] += g
            G[i, j] -= g
            G[j, i] -= g

        # 2. 注入动力源 (泵的“吸吐”模型)
        for node in self.graph.nodes:
            if node.type == "pump":
                in_idx = node.inlet_idx
                out_idx = node.matrix_idx
                
                if node.pump_mode == "constant_flow":
                    q_source = node.pump_params.get("Q_source", 0)
                    # 泵的行为：从 IN 抽走 Q，向 OUT 吐出 Q
                    Q[out_idx] += q_source 
                    Q[in_idx] -= q_source
                elif node.pump_mode == "curve":
                    p_a = node.pump_params.get("A", 0)
                    # 离心泵在预测步：给出口一个初始压力趋势
                    Q[out_idx] += p_a * 1e-6
                    Q[in_idx] -= p_a * 1e-6

        # 3. 设置参考压强锚点 ( Dirichlet 边界条件)
        ref_idx = self._find_reference_index()
        G[ref_idx, ref_idx] += 1e6 
        Q[ref_idx] += 1e6 * 1.01325e5 

        return G, Q

    def _audit_physics(self):
        """物理审计步：计算真实流量并核算质量守恒"""
        real_flows = {pipe.id: 0.0 for pipe in self.graph.pipes}
        node_residuals = np.zeros(self.num_nodes)

        # 1. 计算管道真实流量
        for pipe in self.graph.pipes:
            i, j = pipe.start_idx, pipe.end_idx
            dp = self.P[i] - self.P[j]
            g_audit = calc_pipe_conductance(pipe, self.fluid, dp)
            q = g_audit * dp
            real_flows[pipe.id] = q
            
            node_residuals[i] -= q
            node_residuals[j] += q

        # 2. 核算泵的质量平衡
        for node in self.graph.nodes:
            if node.type == "pump":
                in_idx = node.inlet_idx
                out_idx = node.matrix_idx
                
                # 无论哪种泵，物理上它都是从 IN 抽流量，向 OUT 吐流量
                # 这里假设泵内部流量守恒 Q_in = Q_out = Q_pump
                if node.pump_mode == "constant_flow":
                    q_pump = node.pump_params.get("Q_source", 0)
                else:
                    # 曲线泵：根据当前泵口压差反推真实流量
                    dp_pump = self.P[out_idx] - self.P[in_idx]
                    # Q = sqrt((A - dP)/B) 的变形，这里简化处理或调用 physics
                    q_pump = node.pump_params.get("Q_source", 0) # 暂用额定
                
                node_residuals[out_idx] += q_pump # 向出口注油
                node_residuals[in_idx] -= q_pump # 从入口抽油

        return real_flows, node_residuals

    def _update_conductance(self, real_flows):
        """
        更新等效流导。这是 LAHI 算法最巧妙的地方：
        将非线性特性隐含在动态变化的流导 G 中。
        """
        for pipe in self.graph.pipes:
            i, j = pipe.start_idx, pipe.end_idx
            dp = self.P[i] - self.P[j]
            
            # 根据 Q = G * dP 反推 G_target = Q_real / dP
            if abs(dp) < 1e-2:
                g_target = 1e-6
            else:
                g_target = abs(real_flows[pipe.id] / dp)
            
            # 使用松弛因子 omega 进行加权平滑，防止迭代发散
            g_old = self.G_map.get(pipe.id, 1e-6)
            self.G_map[pipe.id] = (1 - self.omega) * g_old + self.omega * g_target

    def _format_results(self, flows):
        """格式化计算输出：将内部计算节点的压力/流量映射回 UI 物理节点"""
        node_flow_results = {}
        pressures = {}

        for node in self.graph.nodes:
            # 压力：始终取主节点（出口）的压力
            out_idx = node.matrix_idx
            pressures[node.id] = float(self.P[out_idx])
            
            # 流量汇总逻辑
            if node.type == "pump":
                # 对于泵，流量就是其额定/计算流量
                if node.pump_mode == "constant_flow":
                    node_flow_results[node.id] = node.pump_params.get("Q_source", 0)
                else:
                    # 简化：取出口连接管路的总流量
                    node_flow_results[node.id] = node.pump_params.get("Q_source", 0)
            else:
                # 对于普通节点，汇总流入流量
                q_sum = 0.0
                for pipe in self.graph.pipes:
                    q = flows[pipe.id]
                    # 如果这根管子连入该节点
                    if pipe.end_idx == out_idx:
                        q_sum += max(0, q)
                    # 或者如果这根管子反向流入该节点
                    elif pipe.start_idx == out_idx:
                        q_sum += max(0, -q)
                node_flow_results[node.id] = q_sum

        return {
            "pressures": pressures,
            "flows": flows,
            "node_flows": node_flow_results
        }

    def _print_terminal_summary(self, results):
        """美化打印终端摘要"""
        print("\n--- 计算结果摘要 (SI单位/常用单位) ---")
        print(f"{'节点ID':<10} | {'压力 (Pa)':<15} | {'压力 (kPa)':<12} | {'总流量 (m³/h)':<12}")
        print("-" * 60)
        for node_id, p in results["pressures"].items():
            q_m3h = results["node_flows"].get(node_id, 0) * 3600.0
            print(f"{node_id:<10} | {p:15.2f} | {p/1e3:12.4f} | {q_m3h:12.4f}")
        print("-" * 60 + "\n")
