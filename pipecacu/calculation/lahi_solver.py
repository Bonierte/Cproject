import numpy as np
import math
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
        self.tolerance = 1e-7      # 提高收敛精度：节点体积流量残差 (m3/s)
        self.max_iter = 100        # 增加最大迭代步数以支持更复杂的网络
        self.omega = 0.5           # 初始松弛因子降至 0.5，提高稳定性
        self.min_omega = 0.05      # 最小松弛因子
        self.max_omega = 0.9       # 最大松弛因子
        
        # 状态存储 - 使用拓扑分配的实际计算位总数
        self.num_nodes = graph.num_total_indices 
        self.P = np.ones(self.num_nodes) * 1.01325e5  # 压力向量 (Pa)
        self.G_map = {}  # 存储管路/元件当前的等效流导
    
    def _init_conductance(self):
        """
        初始化流导。不再使用统一的 1e-6，而是根据物理参数进行首次估算。
        """
        # 假设初始压降为 1000 Pa 进行估算
        dummy_dp = 1000.0
        for pipe in self.graph.pipes:
            # 特殊管路（如吸油管）会在此处获得物理真实的初始大流导
            g0 = calc_pipe_conductance(pipe, self.fluid, dummy_dp)
            self.G_map[pipe.id] = g0
        
        for node in self.graph.nodes:
            if node.type in ["valve", "tee"]:
                # 阀门和局部阻力件也进行估算
                g0 = 1e-6
                if node.type == "valve":
                    g0 = calc_valve_conductance(node, self.fluid, dummy_dp)
                elif node.type == "tee":
                    g0 = calc_local_conductance(node.tee_k, 0.04, self.fluid, dummy_dp)
                self.G_map[f"node_{node.id}"] = g0

    def solve(self):
        """执行 LAHI 迭代求解主循环"""
        if self.num_nodes == 0:
            print("LAHI Error: 节点数为 0，取消计算。")
            return False, {}

        self._init_conductance()
        prev_residual_norm = float('inf')
        
        # 打印仿真元数据
        print("\n" + "="*50)
        print("LAHI 求解器启动 (多基准锚定模式)...")
        print(f"网络规模: {self.num_nodes} 节点, {len(self.graph.pipes)} 管路")
        print(f"流体: {self.fluid.name}, 密度={self.fluid.rho}kg/m³")
        print("="*50)

        # 找到系统中的压力锚点 (吸油口大气压, 泵出口设定压)
        anchors = self._find_pressure_anchors()

        for it in range(self.max_iter):
            # --- 第一步：线性预测步 (Linear Prediction) ---
            # 组装线性方程组 GP = Q，并应用多压力锚点
            G_matrix, Q_source = self._assemble_system(anchors)
            
            # 求解压力分布 P
            try:
                self.P = spsolve(G_matrix.tocsr(), Q_source)
            except Exception as e:
                print(f"LAHI Error: 矩阵求解失败 (检查拓扑孤岛) - {e}")
                return False, {}

            self.P = np.maximum(self.P, 100.0) 

            # --- 第二步：局部物理审计 (Local Physical Audit) ---
            real_flows, residuals = self._audit_physics()
            
            # 重要：将审计得到的真实流量回写到管路对象中，供下一轮线性预测使用
            for pipe in self.graph.pipes:
                pipe.flow = real_flows[pipe.id]
            
            # 忽略所有锚点（基准点）的残差，因为它们是质量源/汇
            for idx in anchors.keys():
                residuals[idx] = 0.0 
            
            # 计算当前系统的最大不平衡量
            residual_norm = np.linalg.norm(residuals, np.inf)
            
            # 实时反馈迭代进度
            print(f"迭代 [{it+1:3d}]: 残差 = {residual_norm:.4e}, 松弛因子 omega = {self.omega:.2f}")
            
            if residual_norm < self.tolerance:
                print("="*50)
                print(f"LAHI: 求解成功！收敛于第 {it+1} 步。")
                
                results = self._format_results(real_flows)
                self._print_terminal_summary(results)
                
                return True, results

            # --- 第三步：自适应策略 ---
            if residual_norm > prev_residual_norm:
                self.omega = max(self.min_omega, self.omega * 0.5)
            else:
                self.omega = min(self.max_omega, self.omega * 1.1)
            
            prev_residual_norm = residual_norm

            # --- 第四步：等效流导更新 ---
            self._update_conductance(real_flows)

        print(f"LAHI: 达到最大迭代次数 {self.max_iter}，计算未收敛。")
        return False, {}

    def _find_pressure_anchors(self):
        """
        寻找系统中的压力锚点：
        1. 所有油箱的 OUT (吸油口) -> 101.325 kPa (标准大气压)
        2. 所有油箱的 IN (回油口) -> 101.325 kPa
        3. 所有泵的 OUT (出油口) -> 用户设定值 (绝对压力)
        """
        anchors = {}
        for node in self.graph.nodes:
            if node.type == "tank":
                # 油箱吸油口 (matrix_idx) 是标准大气压
                anchors[node.matrix_idx] = 1.01325e5
                # 油箱回油口 (inlet_idx) 也是标准大气压
                if node.inlet_idx is not None:
                    anchors[node.inlet_idx] = 1.01325e5
            elif node.type == "pump":
                # 泵排油口 (matrix_idx) 采用用户设定值作为绝对压力
                set_p_pa = node.pump_params.get("P_max", 0)
                if set_p_pa > 1.0:
                    anchors[node.matrix_idx] = set_p_pa
        
        if not anchors:
            anchors[0] = 1.01325e5
        return anchors

    def _assemble_system(self, anchors):
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

        # 2. 泵的吸入联动 (维持泵 IN/OUT 流量平衡)
        # 核心逻辑：泵出口流出多少油，入口就得从吸油管抽走多少油
        for node in self.graph.nodes:
            if node.type == "pump":
                in_idx = node.inlet_idx
                out_idx = node.matrix_idx
                
                # 计算当前排油段的总排量 (m3/s)
                q_to_system = 0.0
                for pipe in self.graph.pipes:
                    if pipe.start_idx == out_idx:
                        q_to_system += pipe.flow
                    elif pipe.end_idx == out_idx:
                        q_to_system -= pipe.flow
                
                # 在吸油口注入一个“负流量源”，强制吸油管产生压降
                Q[in_idx] -= q_to_system

        # 3. 应用压力锚点 (Dirichlet 边界条件)
        for idx, p_val in anchors.items():
            G[idx, idx] += 1e6 
            Q[idx] += 1e6 * p_val

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

        # 2. 核算泵的质量平衡 (进出流量必须一致)
        for node in self.graph.nodes:
            if node.type == "pump":
                in_idx = node.inlet_idx
                out_idx = node.matrix_idx
                
                # 泵出口作为压力锚点，其“真实流量”由下游阻力决定
                # 我们计算从该锚点流出的净流量
                q_actual_out = 0.0
                for pipe in self.graph.pipes:
                    if pipe.start_idx == out_idx:
                        q_actual_out += real_flows[pipe.id]
                    elif pipe.end_idx == out_idx:
                        q_actual_out -= real_flows[pipe.id]
                
                # 泵入口必须从吸油管抽走同样多的流量
                # 理想情况下 node_residuals[in_idx] + q_actual_out 应为 0
                node_residuals[in_idx] -= q_actual_out 
            
            elif node.type == "tank":
                # 油箱入口和出口的残差将在 solve() 中被 mask 掉
                pass

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
            # 即使压差很小，也使用物理计算出的流导，不再强行归零
            if abs(dp) < 0.1:
                # 极小压差下，使用物理公式（层流极限）直接计算流导
                g_target = calc_pipe_conductance(pipe, self.fluid, 0.5) 
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
                # 对于固定压力泵，显示其在该压力下向系统输出的真实流量
                q_pump_out = 0.0
                for pipe in self.graph.pipes:
                    if pipe.start_idx == out_idx:
                        q_pump_out += flows[pipe.id]
                    elif pipe.end_idx == out_idx:
                        q_pump_out -= flows[pipe.id]
                node_flow_results[node.id] = q_pump_out
            else:
                # 对于普通节点或油箱，汇总流入流量
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
