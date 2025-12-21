import json
import os
import time
from typing import List, Dict


class FittingsStore:
    """简单的管件库存取：存为 JSON，条目即“条例”，不关联实际模型。"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.path = os.path.join(base_dir, "fittings.json")
        self.data: List[Dict] = []
        self._ensure_dir()
        self._load()

    def _ensure_dir(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def _default_data(self) -> List[Dict]:
        return [
            {"id": "elbow45", "name": "45°弯头", "category": "弯头", "angle": 45, "k": 0.3, "inDiameter": "/", "outDiameter": "/", "remark": "单位:角度(°),直径(mm)"},
            {"id": "elbow90", "name": "90°弯头", "category": "弯头", "angle": 90, "k": 1.2, "inDiameter": "/", "outDiameter": "/", "remark": "单位:角度(°),直径(mm)"},
            {"id": "expansion", "name": "渐扩", "category": "渐扩", "angle": "", "k": 0.4, "inDiameter": "/", "outDiameter": "/", "remark": "单位:直径(mm)"},
            {"id": "contraction", "name": "渐缩", "category": "渐缩", "angle": "", "k": 0.8, "inDiameter": "/", "outDiameter": "/", "remark": "单位:直径(mm)"},
            # 直管示例（GB/T 8163 部分规格）
            {"id": "pipe_dn15", "name": "DN15", "category": "直管", "dn": 15, "od": 21.3, "thickness": 2.8, "id_mm": 15.7, "remark": "单位:mm"},
            {"id": "pipe_dn20", "name": "DN20", "category": "直管", "dn": 20, "od": 26.9, "thickness": 2.8, "id_mm": 21.3, "remark": "单位:mm"},
            {"id": "pipe_dn25", "name": "DN25", "category": "直管", "dn": 25, "od": 33.7, "thickness": 3.2, "id_mm": 27.3, "remark": "单位:mm"},
            {"id": "pipe_dn32", "name": "DN32", "category": "直管", "dn": 32, "od": 42.4, "thickness": 3.5, "id_mm": 35.4, "remark": "单位:mm"},
            {"id": "pipe_dn40", "name": "DN40", "category": "直管", "dn": 40, "od": 48.3, "thickness": 3.5, "id_mm": 41.3, "remark": "单位:mm"},
            {"id": "pipe_dn50", "name": "DN50", "category": "直管", "dn": 50, "od": 60.3, "thickness": 3.8, "id_mm": 52.7, "remark": "单位:mm"},
            {"id": "pipe_dn65", "name": "DN65", "category": "直管", "dn": 65, "od": 76.1, "thickness": 4.0, "id_mm": 68.1, "remark": "单位:mm"},
            {"id": "pipe_dn80", "name": "DN80", "category": "直管", "dn": 80, "od": 88.9, "thickness": 4.0, "id_mm": 80.9, "remark": "单位:mm"},
            {"id": "pipe_dn100", "name": "DN100", "category": "直管", "dn": 100, "od": 114.3, "thickness": 4.5, "id_mm": 105.3, "remark": "单位:mm"},
            # 弯头/弯管
            {"id": "elbow45_long", "name": "45°长半径弯头", "category": "弯头", "angle": 45, "k": 0.20, "remark": "R≈1.5D"},
            {"id": "elbow90_long", "name": "90°长半径弯头", "category": "弯头", "angle": 90, "k": 0.30, "remark": "R≈1.5D"},
            {"id": "elbow90_short", "name": "90°短半径弯头", "category": "弯头", "angle": 90, "k": 0.45, "remark": "R≈1.0D"},
            {"id": "elbow90_miter", "name": "90°直角弯头", "category": "弯头", "angle": 90, "k": 1.10, "remark": "R≈0"},
            {"id": "elbow180_return", "name": "180°回弯头", "category": "弯头", "angle": 180, "k": 0.35, "remark": "R≈1.5D"},
            {"id": "elbow60_bend", "name": "60°煨弯管", "category": "弯头", "angle": 60, "k": 0.15, "remark": "R≥3D"},
            # 三通
            {"id": "tee_equal", "name": "等径三通", "category": "三通", "spec": "Equal Tee", "k_run": 0.15, "k_branch": 0.85, "remark": "单位:mm, 主支管径一致"},
            {"id": "tee_45_y", "name": "45°Y型三通", "category": "三通", "spec": "45° Y-Tee", "k_run": 0.12, "k_branch": 0.40, "remark": "单位:mm, 分流更顺畅"},
            {"id": "tee_reducing", "name": "异径三通", "category": "三通", "spec": "Reducing Tee", "k_run": 0.20, "k_branch": 0.90, "remark": "单位:mm, 支管口径小于主管"},
            # 变径
            {"id": "reducer_concentric", "name": "同心渐缩管", "category": "渐缩", "spec": "Concentric Reducer", "angle": "≈15°", "k": 0.05, "remark": "水平/垂直管路通用"},
            {"id": "reducer_eccentric", "name": "偏心渐缩管", "category": "渐缩", "spec": "Eccentric Reducer", "angle": "≈15°", "k": 0.06, "remark": "泵入口专用防气蚀"},
            {"id": "reducer_sudden_con", "name": "突缩管", "category": "渐缩", "spec": "Sudden Contraction", "angle": "90°", "k": 0.50, "remark": "直接变径阻力大"},
            {"id": "reducer_sudden_exp", "name": "突扩管", "category": "渐扩", "spec": "Sudden Expansion", "angle": "90°", "k": 1.00, "remark": "出口排入油箱类突扩"},
            # 阀门
            {"id": "valve_ball_dn25", "name": "球阀 DN25", "category": "阀门", "dn": 25, "Cv": 35, "Kv": 30, "resistance": "极低阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_ball_dn50", "name": "球阀 DN50", "category": "阀门", "dn": 50, "Cv": 180, "Kv": 155, "resistance": "极低阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_globe_dn25", "name": "截止阀 DN25", "category": "阀门", "dn": 25, "Cv": 13, "Kv": 11, "resistance": "高阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_globe_dn50", "name": "截止阀 DN50", "category": "阀门", "dn": 50, "Cv": 45, "Kv": 39, "resistance": "高阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_globe_dn80", "name": "截止阀 DN80", "category": "阀门", "dn": 80, "Cv": 110, "Kv": 95, "resistance": "高阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_butterfly_dn100", "name": "蝶阀 DN100", "category": "阀门", "dn": 100, "Cv": 350, "Kv": 300, "resistance": "中阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_check_dn25", "name": "单向阀 DN25", "category": "阀门", "dn": 25, "Cv": 15, "Kv": 13, "resistance": "中阻力", "remark": "Cv单位:gpm"},
            {"id": "valve_check_dn50", "name": "单向阀 DN50", "category": "阀门", "dn": 50, "Cv": 55, "Kv": 47, "resistance": "中阻力", "remark": "Cv单位:gpm"},
            # 泵 - 简化为两类
            {"id": "pump_displacement", "name": "容积泵 (齿轮/螺杆)", "category": "泵", "pump_type": "gear", "flow": 1.5, "pressure": 250.0, "remark": "流量恒定, 压力随阻力变化"},
            {"id": "pump_centrifugal", "name": "离心泵 (性能曲线)", "category": "泵", "pump_type": "curve", "flow": 10.0, "pressure": 500.0, "shutoff_pressure": 600.0, "remark": "流量随压力增加而减小"},
            # 油品 (流体) - 仅保留三种特定油品
            {"id": "oil_vg320", "name": "VG320 滑油", "category": "油品", "rho_15": 920.0, "v_40": 347.8, "v_100": 25.0, "remark": "密度920kg/m³, 40℃粘度0.32Pa·s"},
            {"id": "oil_vg220", "name": "VG220 滑油", "category": "油品", "rho_15": 900.0, "v_40": 244.4, "v_100": 19.0, "remark": "密度900kg/m³, 40℃粘度0.22Pa·s"},
            {"id": "oil_vg46", "name": "VG46 液压油", "category": "油品", "rho_15": 875.0, "v_40": 46.0, "v_100": 6.8, "remark": "常用轻质润滑油"},
        ]

    def _load(self):
        if not os.path.exists(self.path):
            self.data = self._default_data()
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            if not isinstance(self.data, list):
                self.data = self._default_data()
        except Exception:
            self.data = self._default_data()
            self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def all(self) -> List[Dict]:
        return list(self.data)

    def upsert(self, item: Dict):
        # 保证 ID 存在
        if not item.get("id"):
            item["id"] = f"fit_{int(time.time() * 1000)}"
        exists = False
        for i, d in enumerate(self.data):
            if d.get("id") == item["id"]:
                self.data[i] = item
                exists = True
                break
        if not exists:
            self.data.append(item)
        self.save()

    def get(self, item_id: str) -> Dict:
        for d in self.data:
            if d.get("id") == item_id:
                return d
        return {}

    def delete(self, item_id: str):
        self.data = [d for d in self.data if d.get("id") != item_id]
        self.save()

