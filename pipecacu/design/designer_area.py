from PyQt5 import QtWidgets, QtGui, QtCore, QtSvg
import os
import math
from datasystem.fittings_store import FittingsStore
from .temporary_data import TemporaryData


class GridWidget(QtWidgets.QWidget):
    """画板区域：绘制网格并支持缩放、取点"""
    data_changed = QtCore.pyqtSignal()  # 当数据（点、线）发生变化时触发

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self._pattern = self._build_pattern()
        self._scale = 1.0
        self._min_scale = 0.3
        self._max_scale = 4.0
        self._offset = QtCore.QPointF(0, 0)
        self._last_pos = None
        self._points = []  # list of dict: {x,y,label,ptype}
        self.add_point_enabled = False
        self.drag_enabled = False
        self.delete_enabled = False
        self.current_point_type = "normal"
        self._point_radius = 10
        # 连线状态
        self.connect_enabled = False
        self._start_point = None  # dict 与 _points 同结构，或 None
        self._temp_line = None  # {"start": (x,y), "end": (x,y)}
        self._lines = []  # {"start": (x,y), "end": (x,y), "label": "L1"}
        self._next_line_idx = 1
        self._hover_point = None  # dict or None
        self._hover_line = None   # index or None
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "datasystem"))
        self.temp_data = TemporaryData(os.path.join(data_dir, "temporary_data.json"))
        self.fittings_store = FittingsStore(data_dir)
        # 加载油泵/三通/阀门图标（多候选以防缺失）
        self.pump_icon = self._load_svg_icon(["Beng.svg", "beng.svg"], 24)
        self.tee_icon = self._load_svg_icon(["D_fittings.svg", "guanjian.svg", "Tee.svg"], 24)
        self.valve_icon = self._load_svg_icon(["valve.svg", "Valve.svg"], 24)
        # 初始化时加载已有数据
        self.load_from_temp()

    def _load_svg_icon(self, filename, size: int):
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "leftsvg"))
            candidates = filename if isinstance(filename, (list, tuple)) else [filename]
            for fn in candidates:
                path = os.path.join(base_dir, fn)
                if not os.path.exists(path):
                    continue
                renderer = QtSvg.QSvgRenderer(path)
                pix = QtGui.QPixmap(size, size)
                pix.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(pix)
                renderer.render(painter)
                painter.end()
                return pix
            return None
        except Exception:
            return None

    def _build_pattern(self) -> QtGui.QPixmap:
        # 放大纹理尺寸以提升清晰度，斜率 ±0.625，间距 14，保持与 React 网格比例一致
        w, h = 448,280  # 再放大一倍，提高清晰度，比例保持 224:140 的 4 倍
        step = 56
        m = 0.625
        app = QtWidgets.QApplication.instance()
        dpr = app.devicePixelRatio() if app else 1
        pix = QtGui.QPixmap(int(w * dpr), int(h * dpr))
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.scale(dpr, dpr)
        pen = QtGui.QPen(QtGui.QColor("#7f7f7f"))
        pen.setWidthF(2)
        painter.setPen(pen)
        # "\" 方向
        for x in range(-w, w * 2, step):
            painter.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x + w, m * w))
        # "/" 方向
        for x in range(-w, w * 2, step):
            painter.drawLine(QtCore.QPointF(x, h), QtCore.QPointF(x + w, h - m * w))
        painter.end()
        pix.setDevicePixelRatio(dpr)
        return pix

    def set_points(self, pts):
        # 兼容旧格式 (x,y,label)
        norm = []
        for p in pts:
            if isinstance(p, dict):
                norm.append({
                    "x": p.get("x", 0),
                    "y": p.get("y", 0),
                    "label": p.get("label", ""),
                    "ptype": p.get("ptype", "normal")
                })
            else:
                try:
                    x, y, label = p
                    norm.append({"x": x, "y": y, "label": label, "ptype": "normal"})
                except Exception:
                    continue
        self._points = norm
        self.update()

    def set_add_point_enabled(self, enabled: bool):
        self.add_point_enabled = enabled
        self.update()

    def set_drag_enabled(self, enabled: bool):
        self.drag_enabled = enabled
        if not enabled:
            self._last_pos = None
        self.update()

    def set_delete_enabled(self, enabled: bool):
        self.delete_enabled = enabled
        self.update()

    def set_point_type(self, ptype: str):
        self.current_point_type = ptype or "normal"

    def set_connect_enabled(self, enabled: bool):
        self.connect_enabled = enabled
        if not enabled:
            self._start_point = None
            self._temp_line = None
        self.update()

    def load_from_temp(self):
        """从 TemporaryData 加载数据同步到画布"""
        data = self.temp_data.data
        self._points = data.get("points", [])
        
        # 将线数据从 label 格式转回坐标格式以便绘制
        new_lines = []
        max_line_idx = 0
        for ln in data.get("lines", []):
            s_label = ln.get("start_label")
            e_label = ln.get("end_label")
            p_s = self._find_point_by_label(s_label)
            p_e = self._find_point_by_label(e_label)
            if p_s and p_e:
                line_copy = ln.copy()
                line_copy["start"] = (p_s["x"], p_s["y"])
                line_copy["end"] = (p_e["x"], p_e["y"])
                new_lines.append(line_copy)
                # 更新下一个线的索引计数
                try:
                    l_idx = int(ln.get("label", "L0")[1:])
                    if l_idx > max_line_idx:
                        max_line_idx = l_idx
                except:
                    pass
        self._lines = new_lines
        self._next_line_idx = max_line_idx + 1
        self.data_changed.emit()
        self.update()

    def _find_point_by_label(self, label: str):
        for p in self._points:
            if p.get("label") == label:
                return p
        return None

    def _hit_point(self, x: float, y: float):
        thr = self._point_radius * 1.1
        thr2 = thr * thr
        for p in self._points:
            dx = p.get("x", 0) - x
            dy = p.get("y", 0) - y
            if dx * dx + dy * dy <= thr2:
                return p
        return None

    def _hit_line(self, x: float, y: float, threshold: float = 10.0):
        best_idx = None
        best_dist2 = None
        for i, ln in enumerate(self._lines):
            s = ln.get("start", (0, 0))
            e = ln.get("end", (0, 0))
            dist2 = self._point_to_segment_dist2(x, y, s, e)
            if dist2 <= threshold * threshold:
                if best_dist2 is None or dist2 < best_dist2:
                    best_dist2 = dist2
                    best_idx = i
        return best_idx

    @staticmethod
    def _point_to_segment_dist2(px, py, s, e):
        sx, sy = s
        ex, ey = e
        dx = ex - sx
        dy = ey - sy
        if dx == 0 and dy == 0:
            return (px - sx) ** 2 + (py - sy) ** 2
        t = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = sx + t * dx
        proj_y = sy + t * dy
        return (px - proj_x) ** 2 + (py - proj_y) ** 2

    def _draw_arrow_line(self, painter: QtGui.QPainter, start: tuple, end: tuple, color: str = "#0d47a1"):
        """绘制带箭头的线段，颜色统一深蓝。"""
        line_color = QtGui.QColor(color)
        pen = QtGui.QPen(line_color)
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.setBrush(line_color)
        s_pt = QtCore.QPointF(*start)
        e_pt = QtCore.QPointF(*end)
        painter.drawLine(s_pt, e_pt)
        # 箭头
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        arrow_len = 14
        arrow_ang = math.radians(25)
        p1 = QtCore.QPointF(
            end[0] - arrow_len * math.cos(angle - arrow_ang),
            end[1] - arrow_len * math.sin(angle - arrow_ang),
        )
        p2 = QtCore.QPointF(
            end[0] - arrow_len * math.cos(angle + arrow_ang),
            end[1] - arrow_len * math.sin(angle + arrow_ang),
        )
        painter.drawPolygon(QtGui.QPolygonF([e_pt, p1, p2]))

    def wheelEvent(self, event: QtGui.QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1 / 1.1
        new_scale = max(self._min_scale, min(self._max_scale, self._scale * factor))
        self._scale = new_scale
        self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if self.drag_enabled and event.button() == QtCore.Qt.LeftButton:
            self._last_pos = QtCore.QPointF(event.pos())
            return
        if self.delete_enabled and event.button() == QtCore.Qt.LeftButton:
            x = (event.x() / self._scale) - self._offset.x()
            y = (event.y() / self._scale) - self._offset.y()
            hit_p = self._hit_point(x, y)
            if hit_p:
                label = hit_p.get("label")
                self.temp_data.delete_point(label)
                # 重新加载本地数据以保持同步
                self.load_from_temp()
                return
            hit_l_idx = self._hit_line(x, y)
            if hit_l_idx is not None:
                label = self._lines[hit_l_idx].get("label")
                self.temp_data.delete_line(label)
                self.load_from_temp()
            return
        if self.add_point_enabled and event.button() == QtCore.Qt.LeftButton:
            x = (event.x() / self._scale) - self._offset.x()
            y = (event.y() / self._scale) - self._offset.y()
            # 防止与现有点重合/相交
            threshold = self._point_radius * 2
            for p in self._points:
                dx = p.get("x", 0) - x
                dy = p.get("y", 0) - y
                if (dx * dx + dy * dy) < (threshold * threshold):
                    return  # 太近则忽略落点
            label = f"P{len(self._points) + 1}"
            new_point = {
                "x": x,
                "y": y,
                "label": label,
                "ptype": self.current_point_type,
                "diameter": "",
                "remark": "",
                "fitting_id": "",
                "fitting_name": "",
                "fitting_k": "",
                "fitting_angle": "",
                "pump_model": "",
                "pump_head": "",
                "pump_eff": "",
                "pump_speed": "",
                "pump_flow": "",
                "pump_npsh": "",
                "pump_in_dia": "",
                "pump_out_dia": "",
                "tee_angle": "",
                "tee_ratio": "",
                "tee_k": "",
                "tee_main_dia": "",
                "tee_branch_dia": "",
                "valve_type": "",
                "valve_dia": "",
                "valve_open": "",
                "valve_k": "",
            }
            self._points.append(new_point)
            self._persist_point(new_point)
            self.data_changed.emit()
            self.update()
            return
        if self.connect_enabled and event.button() == QtCore.Qt.LeftButton:
            x = (event.x() / self._scale) - self._offset.x()
            y = (event.y() / self._scale) - self._offset.y()
            hit = self._hit_point(x, y)
            if self._start_point is None:
                if hit is None:
                    return
                self._start_point = hit
                self._temp_line = None
                self.update()
                return
            # 已有起点时，按下不立即落线，等待 mouseRelease
            return
        # 记录 hover（点击时也更新）
        x = (event.x() / self._scale) - self._offset.x()
        y = (event.y() / self._scale) - self._offset.y()
        self._update_hover(x, y)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        x = (event.x() / self._scale) - self._offset.x()
        y = (event.y() / self._scale) - self._offset.y()
        if self.drag_enabled and self._last_pos is not None and event.buttons() & QtCore.Qt.LeftButton:
            delta = QtCore.QPointF(event.pos()) - self._last_pos
            self._offset += delta / self._scale
            self._last_pos = QtCore.QPointF(event.pos())
            self.update()
        if self.connect_enabled and self._start_point is not None:
            sx, sy = self._start_point.get("x", 0), self._start_point.get("y", 0)
            self._temp_line = {"start": (sx, sy), "end": (x, y)}
            self.update()
        self._update_hover(x, y)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if self.drag_enabled and event.button() == QtCore.Qt.LeftButton:
            self._last_pos = None
        if self.connect_enabled and event.button() == QtCore.Qt.LeftButton and self._start_point is not None:
            x = (event.x() / self._scale) - self._offset.x()
            y = (event.y() / self._scale) - self._offset.y()
            hit = self._hit_point(x, y)
            if hit is not None and hit is not self._start_point:
                start = (self._start_point.get("x", 0), self._start_point.get("y", 0))
                end = (hit.get("x", 0), hit.get("y", 0))
                # 去重（无向）
                for ln in self._lines:
                    s = ln.get("start")
                    e = ln.get("end")
                    if (s == start and e == end) or (s == end and e == start):
                        self._start_point = None
                        self._temp_line = None
                        self.update()
                        return
                label = f"L{self._next_line_idx}"
                self._next_line_idx += 1
                new_line = {"start": start, "end": end, "label": label, "diameter": "", "length": "", "remark": ""}
                self._lines.append(new_line)
                self._persist_line(new_line)
                self.data_changed.emit()
            self._start_point = None
            self._temp_line = None
        self.update()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        x = (event.x() / self._scale) - self._offset.x()
        y = (event.y() / self._scale) - self._offset.y()
        hit_point = self._hit_point(x, y)
        if hit_point:
            self._open_point_dialog(hit_point)
            return
        line_idx = self._hit_line(x, y)
        if line_idx is not None and 0 <= line_idx < len(self._lines):
            self._open_line_dialog(line_idx)

    def leaveEvent(self, event: QtCore.QEvent):
        self._hover_point = None
        self._hover_line = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.scale(self._scale, self._scale)
        painter.translate(self._offset)
        brush = QtGui.QBrush(self._pattern)
        # 扩大网格覆盖范围（更大的可视区域，网格数量更多）
        painter.fillRect(QtCore.QRectF(-8000, -8000, 16000, 16000), brush)

        # 原点标记（红色）
        origin_pen = QtGui.QPen(QtGui.QColor("#e53935"))
        origin_brush = QtGui.QBrush(QtGui.QColor("#e53935"))
        painter.setPen(origin_pen)
        painter.setBrush(origin_brush)
        painter.drawEllipse(QtCore.QPointF(0, 0), 8, 8)

        # 取点
        font = painter.font()
        font.setPixelSize(18)
        painter.setFont(font)
        for p in self._points:
            x = p.get("x", 0)
            y = p.get("y", 0)
            label = p.get("label", "")
            ptype = p.get("ptype", "normal")
            if ptype == "pump":
                pen = QtGui.QPen(QtGui.QColor("#0d47a1"))
                brush = QtGui.QBrush(QtGui.QColor("#42a5f5"))
            elif ptype == "tee":
                pen = QtGui.QPen(QtGui.QColor("#e65100"))
                brush = QtGui.QBrush(QtGui.QColor("#ffb74d"))
            elif ptype == "valve":
                pen = QtGui.QPen(QtGui.QColor("#4a148c"))
                brush = QtGui.QBrush(QtGui.QColor("#ba68c8"))
            else:
                pen = QtGui.QPen(QtGui.QColor("#7CFC00"))
                brush = QtGui.QBrush(QtGui.QColor("#7CFC00"))
            is_hover = (p is self._hover_point)
            if is_hover:
                # 渐变发散型微光
                grad = QtGui.QRadialGradient(QtCore.QPointF(x, y), self._point_radius * 2.2)
                base = pen.color()
                center_color = QtGui.QColor(base.red(), base.green(), base.blue(), 150)
                edge_color = QtGui.QColor(base.red(), base.green(), base.blue(), 0)
                grad.setColorAt(0.0, center_color)
                grad.setColorAt(1.0, edge_color)
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QBrush(grad))
                painter.drawEllipse(QtCore.QPointF(x, y), self._point_radius * 2.2, self._point_radius * 2.2)
            painter.setPen(pen)
            painter.setBrush(brush)
            r = 10
            # 特殊类型用透明圆，视觉由图标替代；普通点保持绿色圆
            if ptype == "normal":
                painter.drawEllipse(QtCore.QPointF(x, y), self._point_radius, self._point_radius)
            else:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawEllipse(QtCore.QPointF(x, y), self._point_radius, self._point_radius)
            painter.setPen(QtGui.QColor("#000000"))  # 文本黑色
            painter.drawText(QtCore.QPointF(x + 12, y - 12), label)
            # 覆盖图标
            if ptype == "pump" and self.pump_icon:
                painter.drawPixmap(QtCore.QPointF(x - self.pump_icon.width() / 2, y - self.pump_icon.height() / 2), self.pump_icon)
            if ptype == "tee" and self.tee_icon:
                painter.drawPixmap(QtCore.QPointF(x - self.tee_icon.width() / 2, y - self.tee_icon.height() / 2), self.tee_icon)
            if ptype == "valve" and self.valve_icon:
                painter.drawPixmap(QtCore.QPointF(x - self.valve_icon.width() / 2, y - self.valve_icon.height() / 2), self.valve_icon)
        # 连线（先画已落线，再画预览线）
        for idx, ln in enumerate(self._lines):
            s = ln.get("start", (0, 0))
            e = ln.get("end", (0, 0))
            is_hover_line = (self._hover_line == idx)
            if is_hover_line:
                # 渐变发散型微光：先绘制粗透明笔触
                glow_pen = QtGui.QPen(QtGui.QColor(13, 71, 161, 90))
                glow_pen.setWidthF(10.0)
                glow_pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(glow_pen)
                painter.drawLine(QtCore.QPointF(*s), QtCore.QPointF(*e))
                glow_pen2 = QtGui.QPen(QtGui.QColor(13, 71, 161, 140))
                glow_pen2.setWidthF(7.0)
                glow_pen2.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(glow_pen2)
                painter.drawLine(QtCore.QPointF(*s), QtCore.QPointF(*e))
            self._draw_arrow_line(painter, s, e, "#0d47a1")
            mx = (s[0] + e[0]) / 2
            my = (s[1] + e[1]) / 2
            painter.drawText(QtCore.QPointF(mx + 6, my - 6), ln.get("label", ""))
        if self._temp_line:
            s = self._temp_line["start"]
            e = self._temp_line["end"]
            self._draw_arrow_line(painter, s, e, "#0d47a1")
        painter.end()

    def _update_hover(self, x: float, y: float):
        prev_point = self._hover_point
        prev_line = self._hover_line
        self._hover_point = self._hit_point(x, y)
        if self._hover_point is None:
            self._hover_line = self._hit_line(x, y)
        else:
            self._hover_line = None
        if self._hover_point is not prev_point or self._hover_line != prev_line:
            self.update()

    def _persist_point(self, point: dict):
        base = {
            "label": point.get("label", ""),
            "x": point.get("x", 0),
            "y": point.get("y", 0),
            "ptype": point.get("ptype", "normal"),
            "elevation": point.get("elevation", ""),
            "diameter": point.get("diameter", ""),
            "remark": point.get("remark", ""),
            "fitting_id": point.get("fitting_id", ""),
            "fitting_name": point.get("fitting_name", ""),
            "fitting_k": point.get("fitting_k", ""),
            "fitting_angle": point.get("fitting_angle", ""),
            "pump_model": point.get("pump_model", ""),
            "pump_head": point.get("pump_head", ""),
            "pump_eff": point.get("pump_eff", ""),
            "pump_speed": point.get("pump_speed", ""),
            "pump_flow": point.get("pump_flow", ""),
            "pump_npsh": point.get("pump_npsh", ""),
            "pump_in_dia": point.get("pump_in_dia", ""),
            "pump_out_dia": point.get("pump_out_dia", ""),
            "tee_angle": point.get("tee_angle", ""),
            "tee_ratio": point.get("tee_ratio", ""),
            "tee_k": point.get("tee_k", ""),
            "tee_main_dia": point.get("tee_main_dia", ""),
            "tee_branch_dia": point.get("tee_branch_dia", ""),
            "valve_type": point.get("valve_type", ""),
            "valve_dia": point.get("valve_dia", ""),
            "valve_open": point.get("valve_open", ""),
            "valve_k": point.get("valve_k", ""),
        }
        self.temp_data.upsert_point(base)

    def _persist_line(self, line: dict):
        base = {
            "label": line.get("label", ""),
            "start_label": self._find_point_label(line.get("start")),
            "end_label": self._find_point_label(line.get("end")),
            "diameter": line.get("diameter", ""),
            "length": line.get("length", ""),
            "remark": line.get("remark", ""),
        }
        self.temp_data.upsert_line(base)

    def _find_point_label(self, coord):
        if coord is None:
            return ""
        x, y = coord
        for p in self._points:
            if abs(p.get("x", 0) - x) < 1e-6 and abs(p.get("y", 0) - y) < 1e-6:
                return p.get("label", "")
        return ""

    def _open_point_dialog(self, point: dict):
        # 实时从文件重新加载管件库，确保在对话框中能看到最新添加的管件
        self.fittings_store._load()
        
        dlg = QtWidgets.QDialog(self)
        dlg.resize(450, 450)
        dlg.setWindowTitle(point.get("label", "点"))
        layout = QtWidgets.QVBoxLayout(dlg)
        form_top = QtWidgets.QFormLayout()
        lbl_label = QtWidgets.QLabel(point.get("label", ""))
        lbl_coord = QtWidgets.QLabel(f"({point.get('x', 0):.2f}, {point.get('y', 0):.2f})")
        def _ptype_to_display(pt):
            return {"normal": "普通", "pump": "泵", "tee": "三通", "valve": "阀门"}.get(pt, "普通")

        def _display_to_ptype(txt):
            return {"普通": "normal", "泵": "pump", "三通": "tee", "阀门": "valve"}.get(txt, "normal")

        type_box = QtWidgets.QComboBox()
        type_box.addItems(["普通", "泵", "三通", "阀门"])
        type_box.setCurrentText(_ptype_to_display(point.get("ptype", "normal")))
        elevation_edit = QtWidgets.QLineEdit(str(point.get("elevation", "")))
        form_top.addRow("标签", lbl_label)
        form_top.addRow("坐标", lbl_coord)
        form_top.addRow("类型", type_box)
        form_top.addRow("高度(m)", elevation_edit)
        layout.addLayout(form_top)

        stack = QtWidgets.QStackedWidget()
        # normal form
        normal_widget = QtWidgets.QWidget()
        normal_form = QtWidgets.QFormLayout(normal_widget)
        fittings_combo = QtWidgets.QComboBox()
        fittings_combo.addItem("（不选择）", userData=None)
        for item in self.fittings_store.all():
            cat = item.get("category", "")
            if cat in ("弯头", "渐扩", "渐缩"):
                text = f"{item.get('name','')} | K={item.get('k','')} | {item.get('angle','')}"
                fittings_combo.addItem(text, userData=item)
        diameter_edit = QtWidgets.QLineEdit(str(point.get("diameter", "")))
        remark_edit_n = QtWidgets.QLineEdit(str(point.get("remark", "")))
        normal_form.addRow("管件", fittings_combo)
        normal_form.addRow("备注", remark_edit_n)
        # 预选当前管件
        current_fid = point.get("fitting_id", "")
        if current_fid:
            for idx in range(fittings_combo.count()):
                data = fittings_combo.itemData(idx)
                if data and data.get("id") == current_fid:
                    fittings_combo.setCurrentIndex(idx)
                    break

        # pump form
        pump_widget = QtWidgets.QWidget()
        pump_form = QtWidgets.QFormLayout(pump_widget)
        pump_combo = QtWidgets.QComboBox()
        pump_combo.addItem("（不选择）", userData=None)
        for item in self.fittings_store.all():
            if item.get("category") == "泵":
                txt = f"{item.get('name','')} | Q={item.get('flow','')} | P={item.get('pressure','')}"
                pump_combo.addItem(txt, userData=item)
                if point.get("pump_type") == item.get("pump_type") and point.get("pump_flow") == item.get("flow"):
                    pump_combo.setCurrentIndex(pump_combo.count() - 1)
        
        pump_type_combo = QtWidgets.QComboBox()
        pump_type_combo.addItems(["容积泵 (齿轮/螺杆)", "离心泵 (性能曲线)"])
        
        pump_flow = QtWidgets.QLineEdit(str(point.get("pump_flow", ""))) # m3/h
        pump_head = QtWidgets.QLineEdit(str(point.get("pump_head", ""))) # bar
        pump_shutoff = QtWidgets.QLineEdit(str(point.get("pump_speed", ""))) # bar (离心泵关死扬程)
        remark_edit_p = QtWidgets.QLineEdit(str(point.get("remark", "")))
        
        pump_form.addRow("数据库选型", pump_combo)
        pump_form.addRow("计算类型", pump_type_combo)
        pump_form.addRow("设定流量(m³/h)", pump_flow)
        pump_form.addRow("设定压力/扬程(bar)", pump_head)
        pump_form.addRow("关死压力(bar, 仅离心泵)", pump_shutoff)
        pump_form.addRow("备注", remark_edit_p)

        def on_pump_selected(idx):
            data = pump_combo.itemData(idx)
            if data:
                pump_flow.setText(str(data.get("flow", "")))
                pump_head.setText(str(data.get("pressure", "")))
                pump_shutoff.setText(str(data.get("shutoff_pressure", "")))
                if data.get("pump_type") == "curve":
                    pump_type_combo.setCurrentIndex(1)
                else:
                    pump_type_combo.setCurrentIndex(0)

        pump_combo.currentIndexChanged.connect(on_pump_selected)
        # 初始化类型选择
        if point.get("pump_type") == "curve":
            pump_type_combo.setCurrentIndex(1)
        else:
            pump_type_combo.setCurrentIndex(0)

        # tee form
        tee_widget = QtWidgets.QWidget()
        tee_form = QtWidgets.QFormLayout(tee_widget)
        tee_combo = QtWidgets.QComboBox()
        tee_combo.addItem("（不选择）", userData=None)
        for item in self.fittings_store.all():
            if item.get("category") == "三通":
                txt = f"{item.get('name','')} | 直:{item.get('k_run','')} 支:{item.get('k_branch','')}"
                tee_combo.addItem(txt, userData=item)
                if point.get("tee_angle") and str(point.get("tee_angle")) == str(item.get("spec", "")):
                    tee_combo.setCurrentIndex(tee_combo.count() - 1)
        tee_angle = QtWidgets.QLineEdit(str(point.get("tee_angle", "")))
        tee_ratio = QtWidgets.QLineEdit(str(point.get("tee_ratio", "")))
        tee_k = QtWidgets.QLineEdit(str(point.get("tee_k", "")))
        tee_main_dia = QtWidgets.QLineEdit(str(point.get("tee_main_dia", "")))
        tee_branch_dia = QtWidgets.QLineEdit(str(point.get("tee_branch_dia", "")))
        remark_edit_t = QtWidgets.QLineEdit(str(point.get("remark", "")))
        tee_form.addRow("选型", tee_combo)
        tee_form.addRow("主干直径(mm)", tee_main_dia)
        tee_form.addRow("支管直径(mm)", tee_branch_dia)
        tee_form.addRow("分支角度(°)", tee_angle)
        tee_form.addRow("分流比例(%)", tee_ratio)
        tee_form.addRow("局阻系数K", tee_k)
        tee_form.addRow("备注", remark_edit_t)

        # valve form
        valve_widget = QtWidgets.QWidget()
        valve_form = QtWidgets.QFormLayout(valve_widget)
        valve_combo = QtWidgets.QComboBox()
        valve_combo.addItem("（不选择）", userData=None)
        for item in self.fittings_store.all():
            if item.get("category") == "阀门":
                txt = f"{item.get('name','')} | Cv={item.get('Cv','')} Kv={item.get('Kv','')}"
                valve_combo.addItem(txt, userData=item)
                if point.get("valve_type") and str(point.get("valve_type")) == str(item.get("name", "")):
                    valve_combo.setCurrentIndex(valve_combo.count() - 1)
        valve_type = QtWidgets.QLineEdit(str(point.get("valve_type", "")))
        valve_dia = QtWidgets.QLineEdit(str(point.get("valve_dia", "")))
        valve_open = QtWidgets.QLineEdit(str(point.get("valve_open", "")))
        valve_k = QtWidgets.QLineEdit(str(point.get("valve_k", "")))
        remark_edit_v = QtWidgets.QLineEdit(str(point.get("remark", "")))
        valve_form.addRow("选型", valve_combo)
        valve_form.addRow("阀型", valve_type)
        valve_form.addRow("口径(mm)", valve_dia)
        valve_form.addRow("开度(%)", valve_open)
        valve_form.addRow("流量系数(Cv/Kv)", valve_k)
        valve_form.addRow("备注", remark_edit_v)

        stack.addWidget(normal_widget)  # index 0 normal
        stack.addWidget(pump_widget)    # index 1 pump
        stack.addWidget(tee_widget)     # index 2 tee
        stack.addWidget(valve_widget)   # index 3 valve
        layout.addWidget(stack)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        ok_btn = btn_box.button(QtWidgets.QDialogButtonBox.Ok)
        cancel_btn = btn_box.button(QtWidgets.QDialogButtonBox.Cancel)
        if ok_btn:
            ok_btn.setText("确定")
            ok_btn.setMinimumHeight(32)
            ok_btn.setMinimumWidth(88)
            ok_btn.setStyleSheet("background:#1890ff; color:white; border:none; padding:6px 12px; border-radius:4px;")
        if cancel_btn:
            cancel_btn.setText("取消")
            cancel_btn.setMinimumHeight(32)
            cancel_btn.setMinimumWidth(88)
            cancel_btn.setStyleSheet("background:#d9d9d9; color:#333; border:none; padding:6px 12px; border-radius:4px;")
        layout.addWidget(btn_box)

        def switch_form(ptype: str):
            if ptype == "pump":
                stack.setCurrentIndex(1)
            elif ptype == "tee":
                stack.setCurrentIndex(2)
            elif ptype == "valve":
                stack.setCurrentIndex(3)
            else:
                stack.setCurrentIndex(0)

        def _fill_pump(item):
            if not item:
                return
            pump_model.setText(str(item.get("model", "")))
            pump_flow.setText(str(item.get("flow", "")))
            pump_head.setText(str(item.get("pressure", "")))
            remark_edit_p.setText(str(item.get("remark", "")))

        def _fill_tee(item):
            if not item:
                return
            tee_angle.setText(str(item.get("spec", "")))
            tee_k.setText(str(item.get("k_branch", "")))
            tee_ratio.setText(str(item.get("k_run", "")))
            remark_edit_t.setText(str(item.get("remark", "")))

        def _fill_valve(item):
            if not item:
                return
            valve_type.setText(str(item.get("name", "")))
            valve_dia.setText(str(item.get("dn", "")))
            valve_k.setText(str(item.get("Kv", "")))
            remark_edit_v.setText(str(item.get("remark", "")))

        switch_form(_display_to_ptype(type_box.currentText()))
        type_box.currentTextChanged.connect(lambda txt: switch_form(_display_to_ptype(txt)))
        tee_combo.currentIndexChanged.connect(lambda idx: _fill_tee(tee_combo.itemData(idx)))
        valve_combo.currentIndexChanged.connect(lambda idx: _fill_valve(valve_combo.itemData(idx)))

        def on_accept():
            ptype = _display_to_ptype(type_box.currentText())
            point["ptype"] = ptype
            point["elevation"] = elevation_edit.text().strip()
            if ptype == "normal":
                data = fittings_combo.currentData()
                point["fitting_id"] = data.get("id", "") if data else ""
                point["fitting_name"] = data.get("name", "") if data else ""
                point["fitting_k"] = data.get("k", "") if data else ""
                point["fitting_angle"] = data.get("angle", "") if data else ""
                point["remark"] = remark_edit_n.text().strip()
                point["pump_model"] = point["pump_head"] = point["pump_eff"] = point["pump_speed"] = ""
                point["pump_flow"] = point["pump_npsh"] = point["pump_in_dia"] = point["pump_out_dia"] = ""
                point["tee_angle"] = point["tee_ratio"] = point["tee_k"] = ""
                point["tee_main_dia"] = point["tee_branch_dia"] = ""
                point["valve_type"] = point["valve_dia"] = point["valve_open"] = point["valve_k"] = ""
            elif ptype == "pump":
                point["pump_type"] = "curve" if pump_type_combo.currentIndex() == 1 else "gear"
                point["pump_flow"] = pump_flow.text().strip()
                point["pump_head"] = pump_head.text().strip()
                point["pump_speed"] = pump_shutoff.text().strip() # 借用 speed 存离心泵关死压力
                point["remark"] = remark_edit_p.text().strip()
                
                point["fitting_id"] = point["fitting_name"] = point["fitting_k"] = point["fitting_angle"] = ""
                point["pump_eff"] = point["pump_npsh"] = point["pump_in_dia"] = point["pump_out_dia"] = ""
                point["tee_angle"] = point["tee_ratio"] = point["tee_k"] = ""
                point["tee_main_dia"] = point["tee_branch_dia"] = ""
                point["diameter"] = ""
                point["valve_type"] = point["valve_dia"] = point["valve_open"] = point["valve_k"] = ""
            elif ptype == "tee":
                data = tee_combo.currentData()
                if data:
                    point["tee_angle"] = str(data.get("spec", ""))
                    point["tee_ratio"] = str(data.get("k_run", ""))
                    point["tee_k"] = str(data.get("k_branch", ""))
                    point["remark"] = data.get("remark", "")
                else:
                    point["tee_angle"] = tee_angle.text().strip()
                    point["tee_ratio"] = tee_ratio.text().strip()
                    point["tee_k"] = tee_k.text().strip()
                point["tee_angle"] = tee_angle.text().strip()
                point["tee_ratio"] = tee_ratio.text().strip()
                point["tee_k"] = tee_k.text().strip()
                point["tee_main_dia"] = tee_main_dia.text().strip()
                point["tee_branch_dia"] = tee_branch_dia.text().strip()
                point["remark"] = remark_edit_t.text().strip()
                point["fitting_id"] = point["fitting_name"] = point["fitting_k"] = point["fitting_angle"] = ""
                point["pump_model"] = point["pump_head"] = point["pump_eff"] = point["pump_speed"] = ""
                point["pump_flow"] = point["pump_npsh"] = point["pump_in_dia"] = point["pump_out_dia"] = ""
                point["diameter"] = ""
                point["valve_type"] = point["valve_dia"] = point["valve_open"] = point["valve_k"] = ""
            elif ptype == "valve":
                data = valve_combo.currentData()
                if data:
                    point["valve_type"] = data.get("name", "")
                    point["valve_dia"] = str(data.get("dn", ""))
                    point["valve_k"] = str(data.get("Kv", ""))
                    point["remark"] = data.get("remark", "")
                else:
                    point["valve_type"] = valve_type.text().strip()
                    point["valve_dia"] = valve_dia.text().strip()
                    point["valve_k"] = valve_k.text().strip()
                point["valve_type"] = valve_type.text().strip()
                point["valve_dia"] = valve_dia.text().strip()
                point["valve_open"] = valve_open.text().strip()
                point["valve_k"] = valve_k.text().strip()
                point["remark"] = remark_edit_v.text().strip()
                point["fitting_id"] = point["fitting_name"] = point["fitting_k"] = point["fitting_angle"] = ""
                point["pump_model"] = point["pump_head"] = point["pump_eff"] = point["pump_speed"] = ""
                point["pump_flow"] = point["pump_npsh"] = point["pump_in_dia"] = point["pump_out_dia"] = ""
                point["tee_angle"] = point["tee_ratio"] = point["tee_k"] = ""
                point["tee_main_dia"] = point["tee_branch_dia"] = ""
                point["diameter"] = ""
            self._persist_point(point)
            self.update()
            dlg.accept()

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dlg.reject)
        dlg.exec_()

    def _open_line_dialog(self, idx: int):
        if idx < 0 or idx >= len(self._lines):
            return
        
        # 实时从文件重新加载管件库
        self.fittings_store._load()
        
        line = self._lines[idx]
        dlg = QtWidgets.QDialog(self)
        dlg.resize(300, 500)
        dlg.setWindowTitle(line.get("label", "线"))
        layout = QtWidgets.QVBoxLayout(dlg)
        form = QtWidgets.QFormLayout()
        lbl_se = QtWidgets.QLabel(f"{self._find_point_label(line.get('start'))} -> {self._find_point_label(line.get('end'))}")
        pipe_combo = QtWidgets.QComboBox()
        pipe_combo.addItem("（不选择）", userData=None)
        for item in self.fittings_store.all():
            if item.get("category") == "直管":
                txt = f"{item.get('name','')} | DN{item.get('dn','')} | ID={item.get('id_mm','')}"
                pipe_combo.addItem(txt, userData=item)
        dia_edit = QtWidgets.QLineEdit(str(line.get("diameter", "")))
        len_edit = QtWidgets.QLineEdit(str(line.get("length", "")))
        remark_edit = QtWidgets.QLineEdit(str(line.get("remark", "")))
        form.addRow("两端", lbl_se)
        form.addRow("类型/规格", pipe_combo)
        form.addRow("直径(mm)", dia_edit)
        form.addRow("长度(m)", len_edit)
        form.addRow("备注", remark_edit)
        layout.addLayout(form)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        ok_btn = btn_box.button(QtWidgets.QDialogButtonBox.Ok)
        cancel_btn = btn_box.button(QtWidgets.QDialogButtonBox.Cancel)
        if ok_btn:
            ok_btn.setText("确定")
            ok_btn.setMinimumHeight(32)
            ok_btn.setMinimumWidth(88)
            ok_btn.setStyleSheet("background:#1890ff; color:white; border:none; padding:6px 12px; border-radius:4px;")
        if cancel_btn:
            cancel_btn.setText("取消")
            cancel_btn.setMinimumHeight(32)
            cancel_btn.setMinimumWidth(88)
            cancel_btn.setStyleSheet("background:#d9d9d9; color:#333; border:none; padding:6px 12px; border-radius:4px;")
        layout.addWidget(btn_box)

        # 预选：若直径与某直管ID(计算内径)匹配，则选中
        try:
            dia_val = str(line.get("diameter", "")).strip()
            for idx in range(pipe_combo.count()):
                data = pipe_combo.itemData(idx)
                if not data:
                    continue
                if dia_val and str(data.get("id_mm", "")) == dia_val:
                    pipe_combo.setCurrentIndex(idx)
                    break
        except Exception:
            pass

        def on_pipe_change(idx: int):
            data = pipe_combo.itemData(idx)
            if data:
                dia_edit.setText(str(data.get("id_mm", "")))
                if not remark_edit.text().strip():
                    remark_edit.setText(str(data.get("name", "")))

        pipe_combo.currentIndexChanged.connect(on_pipe_change)

        def on_accept():
            data = pipe_combo.currentData()
            if data:
                line["diameter"] = str(data.get("id_mm", ""))
                if not len_edit.text().strip():
                    line["length"] = ""
                line["remark"] = remark_edit.text().strip() or str(data.get("name", ""))
            else:
                line["diameter"] = dia_edit.text().strip()
            line["length"] = len_edit.text().strip()
            line["remark"] = remark_edit.text().strip()
            self._persist_line(line)
            self.update()
            dlg.accept()

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dlg.reject)
        dlg.exec_()

    def _show_info_dialog(self, title: str):
        # 已废弃，保留接口占位
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle(title or "")
        msg.setText("")
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        msg.exec_()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        # 使网格中心与画布中心对齐
        self._offset = QtCore.QPointF(-self.width() / (2 * self._scale), -self.height() / (2 * self._scale))
        super().resizeEvent(event)

