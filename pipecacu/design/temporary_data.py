import json
import os
from typing import Dict, List, Optional


class TemporaryData:
    """
    临时拓扑数据（点、线），存储到 JSON 以供后续计算。
    points: [{label,x,y,ptype,...扩展}]
    lines: [{label,start_label,end_label,diameter,length,remark}]
    """

    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data = {"points": [], "lines": []}
        self._load()

    def _load(self):
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"points": [], "lines": []}
        else:
            self._save()

    def _save(self):
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # Points
    def upsert_point(self, point: Dict):
        label = point.get("label")
        if not label:
            return
        found = False
        for i, p in enumerate(self.data.get("points", [])):
            if p.get("label") == label:
                self.data["points"][i] = point
                found = True
                break
        if not found:
            self.data["points"].append(point)
        self._save()

    def get_point(self, label: str) -> Optional[Dict]:
        for p in self.data.get("points", []):
            if p.get("label") == label:
                return p
        return None

    # Lines
    def upsert_line(self, line: Dict):
        label = line.get("label")
        if not label:
            return
        found = False
        for i, ln in enumerate(self.data.get("lines", [])):
            if ln.get("label") == label:
                self.data["lines"][i] = line
                found = True
                break
        if not found:
            self.data["lines"].append(line)
        self._save()

    def get_line(self, label: str) -> Optional[Dict]:
        for ln in self.data.get("lines", []):
            if ln.get("label") == label:
                return ln
        return None

    def delete_point(self, label: str):
        """删除特定点及其关联的所有线"""
        self.data["points"] = [p for p in self.data.get("points", []) if p.get("label") != label]
        # 同时删除所有起止点包含该 label 的线
        self.data["lines"] = [ln for ln in self.data.get("lines", []) 
                             if ln.get("start_label") != label and ln.get("end_label") != label]
        self._save()

    def delete_line(self, label: str):
        """删除特定线"""
        self.data["lines"] = [ln for ln in self.data.get("lines", []) if ln.get("label") != label]
        self._save()

    def clear(self):
        """清空所有临时数据"""
        self.data = {"points": [], "lines": []}
        self._save()