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
        这是计算开始前的第一步，确保物理对象与数学矩阵一一对应。
        """
        # 1. 为每个节点分配唯一的矩阵索引 (从 0 到 N-1)
        for idx, node in enumerate(self.nodes):
            node.matrix_idx = idx
            self.node_map[node.id] = idx

        # 2. 建立邻接表：记录每个节点连接了哪些邻居以及通过哪根管路连接
        self.adj_list = [[] for _ in range(len(self.nodes))]
        
        print(f"    - 拓扑连接分析:")
        for pipe in self.pipes:
            # 根据标签找到对应的矩阵索引
            s_idx = self.node_map.get(pipe.start_node_id)
            e_idx = self.node_map.get(pipe.end_node_id)
            
            if s_idx is not None and e_idx is not None:
                # 在管路对象中回存索引，方便后续矩阵组装时直接调用
                pipe.start_idx = s_idx
                pipe.end_idx = e_idx
                
                # 双向记录拓扑（无向图性质）
                self.adj_list[s_idx].append((e_idx, pipe))
                self.adj_list[e_idx].append((s_idx, pipe))
                print(f"      [链路] {pipe.id}: 从 {pipe.start_node_id}(#{s_idx}) 连向 {pipe.end_node_id}(#{e_idx})")
            else:
                # 异常情况：直线的一端没有连接到任何点
                print(f"      [警告] 管路 {pipe.id} 存在悬空端点，计算时将忽略该支路。")

        print(f"    - 拓扑构建完成: 共识别 {len(self.nodes)} 有效节点, {len(self.pipes)} 有效管路")
