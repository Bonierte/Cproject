class Node:
    """计算节点对象"""

    def __init__(self, data: dict):
        # 基础属性
        self.id = data.get("label", "")
        self.type = data.get("ptype", "normal")  # normal, pump, valve, tee
        self.x = data.get("x", 0)
        self.y = data.get("y", 0)

        # 物理属性 (待求解)
        self.pressure = 0.0  # 当前压力 (Pa)
        self.flow_net = 0.0  # 净流出/流入量 (m3/s)

        # 矩阵索引 (由 Topology 分配)
        self.matrix_idx = -1


class Pipe:
    """计算管路对象"""

    def __init__(self, data: dict):
        self.id = data.get("label", "")
        self.start_node_id = data.get("start_label", "")
        self.end_node_id = data.get("end_label", "")

        # 几何参数 (需处理单位转换)
        raw_dia = float(data.get("diameter", 0) or 0.040)  # 默认 40mm
        self.diameter = raw_dia / 1000.0  # mm -> m

        raw_len = float(data.get("length", 0) or 10.0)  # 默认 10m
        self.length = raw_len  # m

        self.roughness = 0.045e-3  # 绝对粗糙度 (m)

        # 动态参数
        self.flow = 0.0  # 流量 (m3/s)
        self.velocity = 0.0  # 流速 (m/s)