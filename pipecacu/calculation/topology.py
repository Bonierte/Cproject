from typing import List, Dict
from .models import Node, Pipe

class NetworkGraph:
    """
    网络拓扑类：负责将 UI 传来的零散节点和直线转换为数学计算所需的图结构。
    """
    def __init__(self, nodes: List[Node], pipes: List[Pipe]):
        self.nodes = nodes
        self.pipes = pipes

        # 映射表: 节点标签(Label) -> 矩阵索引(Index)
        # 矩阵索引决定了节点在线性方程组 GP=Q 中的行/列位置
        self.node_map: Dict[str, int] = {}
        self.adj_list = []  # 邻接表：用于快速查询节点的连接情况

    def build(self):
        """
        构建拓扑关系并完成索引分配。
        支持组件的“虚拟化”模型：
        - 泵 (Pump): 虚拟化为 IN(吸油口) 和 OUT(出油口)，通过泵动力关联。
        - 油箱 (Tank): 虚拟化为统一的“基准位”，支持多路回油流入和吸油流出。
        """
        current_idx = 0
        print(f"    - 索引分配分析:")
        for node in self.nodes:
            if node.type == 'pump':
                # 泵节点占用两个矩阵位置：IN 和 OUT
                node.inlet_idx = current_idx
                node.matrix_idx = current_idx + 1 # matrix_idx 依然代表 UI 上的物理点
                self.node_map[node.id] = node.matrix_idx
                current_idx += 2
                print(f"      [泵节点] {node.id}: 虚拟化为 IN(#{node.inlet_idx}) -> OUT(#{node.matrix_idx})")
            elif node.type == 'tank':
                # 油箱虚拟化为两个逻辑点：IN (回油口) 和 OUT (吸油口)
                # 这有助于在拓扑上分离“吸油链路”和“回油链路”，避免参考点强行锁定回油压
                node.inlet_idx = current_idx
                node.matrix_idx = current_idx + 1 # OUT口作为主索引 (吸油)
                self.node_map[node.id] = node.matrix_idx
                current_idx += 2
                print(f"      [油箱点] {node.id}: 虚拟化为 IN(#{node.inlet_idx}) 和 OUT(#{node.matrix_idx})")
            else:
                node.inlet_idx = None
                node.matrix_idx = current_idx
                self.node_map[node.id] = current_idx
                current_idx += 1
                print(f"      [普通点] {node.id}: 映射为 #{node.matrix_idx}")

        self.num_total_indices = current_idx

        # 2. 建立邻接表并重定向管路连接
        self.adj_list = [[] for _ in range(self.num_total_indices)]
        
        print(f"    - 拓扑连接重定向分析:")
        for pipe in self.pipes:
            # 获取物理点的对象
            s_node = next(n for n in self.nodes if n.id == pipe.start_node_id)
            e_node = next(n for n in self.nodes if n.id == pipe.end_node_id)

            # --- 起点重定向策略 ---
            # 如果管路从泵或油箱出发，均连接到其逻辑出口 (matrix_idx / OUT)
            s_idx = s_node.matrix_idx
            
            # --- 终点重定向策略 ---
            # 如果管路连入泵或油箱，必须连接到其逻辑入口 (inlet_idx / IN)
            if e_node.type in ['pump', 'tank']:
                e_idx = e_node.inlet_idx
            else:
                # 连入普通点，直接连到 matrix_idx
                e_idx = e_node.matrix_idx

            # 在管路对象中回存最终计算索引
            pipe.start_idx = s_idx
            pipe.end_idx = e_idx
            
            # 双向记录拓扑（用于后续可能的图遍历）
            self.adj_list[s_idx].append((e_idx, pipe))
            self.adj_list[e_idx].append((s_idx, pipe))
            print(f"      [链路] {pipe.id}: {pipe.start_node_id} -> {pipe.end_node_id} (计算路径: #{s_idx} -> #{e_idx})")

        print(f"    - 拓扑构建完成: 物理节点 {len(self.nodes)} 个, 映射计算位 {self.num_total_indices} 个")
