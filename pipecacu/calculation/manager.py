import json
import os
from .models import Node, Pipe
from .topology import NetworkGraph
from .lahi_solver import LAHISolver


class CalculationManager:
    def __init__(self, json_path):
        self.json_path = json_path

    def run(self):
        """主入口"""
        # 1. 读取数据
        if not os.path.exists(self.json_path):
            return {"success": False, "msg": "找不到临时数据文件"}

        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 2. 转换模型
        nodes = [Node(d) for d in data.get("points", [])]
        pipes = [Pipe(d) for d in data.get("lines", [])]

        # 3. 构建拓扑
        graph = NetworkGraph(nodes, pipes)
        graph.build()

        # 4. 求解
        solver = LAHISolver(graph)
        success, pressures = solver.solve()

        if success:
            return {"success": True, "msg": "计算收敛", "result": pressures}
        else:
            return {"success": False, "msg": "计算失败"}