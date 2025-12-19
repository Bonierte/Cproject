from typing import List, Dict
from .models import Node, Pipe


class NetworkGraph:
    def __init__(self, nodes: List[Node], pipes: List[Pipe]):
        self.nodes = nodes
        self.pipes = pipes

        # 映射表: label -> matrix_index
        self.node_map: Dict[str, int] = {}
        self.adj_list = []  # 邻接表

    def build(self):
        """构建拓扑关系"""
        # 1. 分配矩阵索引
        for idx, node in enumerate(self.nodes):
            node.matrix_idx = idx
            self.node_map[node.id] = idx

        # 2. 建立连接关系 (这里暂时留空，后续写)
        print(f"拓扑构建完成: 共 {len(self.nodes)} 节点, {len(self.pipes)} 管路")