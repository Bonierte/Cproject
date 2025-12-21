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
        支持泵的“虚拟双节点”模型：
        - 泵的 ID (如 P1) 对应 matrix_idx (出油口 OUT)
        - 内部自动生成一个 inlet_idx (入油口 IN)
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
            else:
                node.inlet_idx = None
                node.matrix_idx = current_idx
                self.node_map[node.id] = current_idx
                current_idx += 1
                print(f"      [普通点] {node.id}: 映射为 #{node.matrix_idx}")

        self.num_total_indices = current_idx

        # 2. 建立邻接表：记录每个节点连接了哪些邻居以及通过哪根管路连接
        self.adj_list = [[] for _ in range(self.num_total_indices)]
        
        print(f"    - 拓扑连接重定向分析:")
        for pipe in self.pipes:
            # 获取物理点的索引 (此时 node_map 里存的是主索引/OUT口)
            s_main_idx = self.node_map.get(pipe.start_node_id)
            e_main_idx = self.node_map.get(pipe.end_node_id)
            
            if s_main_idx is not None and e_main_idx is not None:
                # 查找对应的节点对象
                s_node = next(n for n in self.nodes if n.matrix_idx == s_main_idx)
                e_node = next(n for n in self.nodes if n.matrix_idx == e_main_idx)

                # 起点重定向：如果是从泵出发，连到 OUT 口 (就是 s_main_idx)
                s_idx = s_main_idx
                
                # 终点重定向：如果是连入泵，连到泵的 IN 口 (inlet_idx)
                if e_node.type == 'pump':
                    e_idx = e_node.inlet_idx
                else:
                    e_idx = e_main_idx

                # 在管路对象中回存最终计算索引
                pipe.start_idx = s_idx
                pipe.end_idx = e_idx
                
                # 双向记录拓扑
                self.adj_list[s_idx].append((e_idx, pipe))
                self.adj_list[e_idx].append((s_idx, pipe))
                print(f"      [链路] {pipe.id}: {pipe.start_node_id} -> {pipe.end_node_id} (计算路径: #{s_idx} -> #{e_idx})")
            else:
                print(f"      [警告] 管路 {pipe.id} 存在悬空端点。")

        print(f"    - 拓扑构建完成: 物理节点 {len(self.nodes)} 个, 映射计算位 {self.num_total_indices} 个")
