import json
import os
from .models import Node, Pipe
from .topology import NetworkGraph
from .lahi_solver import LAHISolver


class CalculationManager:
    def __init__(self, json_path):
        self.json_path = json_path

    def run(self, fluid=None):
        """主入口"""
        print("\n" + ">>>" * 15)
        print("仿真任务启动: 正在从 JSON 链路同步数据...")
        try:
            # 1. 读取数据
            if not os.path.exists(self.json_path):
                print(f"[-] 错误: 找不到数据文件 {self.json_path}")
                return {"success": False, "msg": "找不到临时数据文件"}

            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                p_count = len(data.get("points", []))
                l_count = len(data.get("lines", []))
                print(f"[1/4] 数据加载成功: 原始点数={p_count}, 原始线数={l_count}")

            # 2. 转换模型
            print(f"[2/4] 模型实例化: 正在转换物理对象...")
            nodes = [Node(d) for d in data.get("points", [])]
            pipes = [Pipe(d) for d in data.get("lines", [])]
            
            for node in nodes:
                if node.type == "pump":
                    print(f"    - 识别泵节点: {node.id}, 模式: {node.pump_mode}, 设定: {node.pump_params}")
            
            if not nodes:
                print("[-] 错误: 画布为空")
                return {"success": False, "msg": "画布上没有节点，请先添加节点"}

            # 3. 构建拓扑
            print(f"[3/4] 拓扑分析: 正在建立网络连接图...")
            graph = NetworkGraph(nodes, pipes)
            graph.build()

            # 4. 求解
            print(f"[4/4] 进入求解引擎: 准备执行 LAHI 迭代...")
            solver = LAHISolver(graph)
            if fluid:
                solver.fluid = fluid
                print(f"    - 注入流体物性: {fluid.name}, rho={fluid.rho:.1f} kg/m³")
            
            success, results = solver.solve()

            if success:
                print("[+] 计算完成: 系统已收敛至稳态。")
                print(">>>" * 15 + "\n")
                return {"success": True, "msg": "计算成功收敛", "result": results}
            else:
                print("[-] 计算失败: 迭代未收敛。")
                print(">>>" * 15 + "\n")
                return {"success": False, "msg": "计算迭代失败，请检查拓扑连接或物理参数"}
        except Exception as e:
            import traceback
            print(f"[-] 异常崩溃: \n{traceback.format_exc()}")
            return {"success": False, "msg": f"计算过程发生异常: {str(e)}"}
