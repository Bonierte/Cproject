import os
from PyQt5 import QtWidgets, QtGui, QtCore
from main_window import Ui_MainWindow
from design.designer_area import GridWidget
from datasystem.fittings_store import FittingsStore
from widgets.fittings_dialog import FittingsDialog


class AppWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    """主窗口封装：布局、样式、按钮逻辑、画布网格和取点"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.buttons = []
        self.points = []
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("滑油系统设计仿真平台")
        self._build_menu()
        self._build_left_buttons()
        self._build_panels()
        self._build_canvas()
        self._rebuild_layout()
        # 记录当前非拖动模式的激活按钮索引（0,2,3,4,5等），保证“拖动+单一模式”
        self._active_mode_idx = None

    def _build_menu(self):
        menubar = self.menubar
        menubar.clear()
        open_act = QtWidgets.QAction("打开", self)
        save_act = QtWidgets.QAction("保存", self)
        fittings_act = QtWidgets.QAction("管件库", self)
        calc_act = QtWidgets.QAction("压力计算", self)
        menubar.addAction(open_act)
        menubar.addAction(save_act)
        menubar.addAction(fittings_act)
        menubar.addAction(calc_act)
        self.menu_actions = {"open": open_act, "save": save_act, "fittings": fittings_act, "calc": calc_act}
        fittings_act.triggered.connect(self._open_fittings)

    def _build_left_buttons(self):
        svg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "leftsvg"))

        def icon_from(name, fallback):
            path = os.path.join(svg_dir, name)
            if os.path.exists(path):
                return QtGui.QIcon(path)
            return fallback

        icons = [
            (icon_from("getpoint.svg", self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton)), "取点"),
            (icon_from("tuodong.svg", self.style().standardIcon(QtWidgets.QStyle.SP_ArrowUp)), "拖动"),
            (icon_from("lianxian.svg", self.style().standardIcon(QtWidgets.QStyle.SP_ArrowRight)), "连接"),
            (icon_from("Beng.svg", self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload)), "油泵"),
            (icon_from("guanjian.svg", self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder)), "三通"),
            (icon_from("valve.svg", self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay)), "阀门"),
            (icon_from("delete.svg", self.style().standardIcon(QtWidgets.QStyle.SP_TrashIcon)), "删除"),
        ]
        layout = QtWidgets.QGridLayout()
        layout.setSpacing(0)
        for idx, (icon, text) in enumerate(icons):
            btn = QtWidgets.QPushButton()
            btn.setCheckable(True)
            # 设置样式：按下灰色
            btn.setStyleSheet("QPushButton:checked { background: #d9d9d9; }")
            if idx == 0:  # 取点
                btn.toggled.connect(lambda c, i=idx: self._toggle_add_point(i, c))
            elif idx == 1:  # 拖动（可与其他并存）
                btn.toggled.connect(self._toggle_drag)
            elif idx == 2:  # 连接
                btn.toggled.connect(lambda c, i=idx: self._toggle_connect(i, c))
            elif idx == 3:  # 油泵点
                btn.toggled.connect(lambda c, i=idx: self._toggle_pump_point(i, c))
            elif idx == 4:  # 三通点
                btn.toggled.connect(lambda c, i=idx: self._toggle_tee_point(i, c))
            elif idx == 5:  # 阀门点
                btn.toggled.connect(lambda c, i=idx: self._toggle_valve_point(i, c))
            else:
                btn.toggled.connect(lambda checked, name=text, i=idx: self._toggle_placeholder(i, name, checked))
            btn.setIcon(icon)
            btn.setToolTip(text)
            btn.setFixedSize(40, 36)
            layout.addWidget(btn, idx // 3, idx % 3)
            self.buttons.append(btn)
        self.design_buttons.setLayout(layout)

    def _build_panels(self):
        def make_title(text):
            lbl = QtWidgets.QLabel(text)
            lbl.setStyleSheet("background: white; padding: 4px;")
            return lbl

        catalog_layout = QtWidgets.QVBoxLayout()
        catalog_layout.setContentsMargins(0,0, 0, 0)
        catalog_layout.addWidget(make_title("管路结构"))
        catalog_layout.addStretch()
        self.catalog.setLayout(catalog_layout)

        info_layout = QtWidgets.QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.addWidget(make_title("节点参数"))
        info_layout.addStretch()
        self.information.setLayout(info_layout)

        calc_layout = QtWidgets.QVBoxLayout()
        calc_layout.setContentsMargins(0,0,0,0)
        calc_layout.addWidget(make_title("计算结果"))
        calc_layout.addStretch()
        self.caculate.setLayout(calc_layout)

        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(make_title("日志信息"))
        log_layout.addStretch()
        self.log.setLayout(log_layout)

    def _build_canvas(self):
        canvas_layout = QtWidgets.QVBoxLayout()
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.grid = GridWidget(self.canvas)
        canvas_layout.addWidget(self.grid)
        self.canvas.setLayout(canvas_layout)

    def _rebuild_layout(self):
        for frame in [self.design_buttons, self.catalog, self.information, self.canvas, self.caculate, self.log]:
            frame.setFrameShape(QtWidgets.QFrame.Box)
            frame.setFrameShadow(QtWidgets.QFrame.Plain)
            frame.setLineWidth(4)
            frame.setStyleSheet("border: 4px solid #d9d9d9;")

        main_layout = QtWidgets.QHBoxLayout(self.centralwidget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_col = QtWidgets.QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(0)
        left_col.addWidget(self.design_buttons)
        splitter_left = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter_left.addWidget(self.catalog)
        splitter_left.addWidget(self.information)
        splitter_left.setSizes([1, 1])
        left_col.addWidget(splitter_left, 1)
        left_wrap = QtWidgets.QWidget()
        left_wrap.setLayout(left_col)
        left_wrap.setFixedWidth(240)

        right_col = QtWidgets.QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)
        right_col.addWidget(self.canvas, 3)

        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(0)
        bottom_row.addWidget(self.caculate, 2)
        bottom_row.addWidget(self.log, 1)
        bottom_wrap = QtWidgets.QWidget()
        bottom_wrap.setLayout(bottom_row)
        bottom_wrap.setFixedHeight(220)

        right_col.addWidget(bottom_wrap)
        right_wrap = QtWidgets.QWidget()
        right_wrap.setLayout(right_col)

        main_layout.addWidget(left_wrap)
        main_layout.addWidget(right_wrap, 1)

    def _toggle_add_point(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_add_point_enabled(checked)
            self.grid.set_point_type("normal")
            if checked:
                self.grid.set_connect_enabled(False)

    def _toggle_drag(self, checked: bool):
        if hasattr(self, "grid"):
            self.grid.set_drag_enabled(checked)
            # 拖动可与其他模式并存，不互斥

    def _toggle_connect(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_connect_enabled(checked)
            if checked:
                self.grid.set_add_point_enabled(False)
            else:
                self.grid.set_connect_enabled(False)

    def _toggle_pump_point(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_add_point_enabled(checked)
            self.grid.set_connect_enabled(False)
            self.grid.set_point_type("pump")
            if not checked:
                self.grid.set_add_point_enabled(False)

    def _toggle_tee_point(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_add_point_enabled(checked)
            self.grid.set_connect_enabled(False)
            self.grid.set_point_type("tee")
            if not checked:
                self.grid.set_add_point_enabled(False)

    def _toggle_valve_point(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_add_point_enabled(checked)
            self.grid.set_connect_enabled(False)
            self.grid.set_point_type("valve")
            if not checked:
                self.grid.set_add_point_enabled(False)

    def _toggle_placeholder(self, idx: int, name: str, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        self._placeholder_action(name)

    def _allow_mode_toggle(self, idx: int, checked: bool) -> bool:
        """非拖动按钮的互斥逻辑：只能存在一个非拖动模式；拖动可并存。
        - 若已存在其他非拖动模式，新的非拖动按钮不会被置为选中，会被立即回退。
        - 取消只有再次点击自身才行（即本按钮 toggled False 时才清空 active）。"""
        if idx == 1:
            return True
        if checked:
            if self._active_mode_idx is None or self._active_mode_idx == idx:
                self._active_mode_idx = idx
                # 取消其他非拖动按钮的选中（只有在它们自身再点击时才会 False，这里不动）
                return True
            else:
                # 不允许同时存在第二个非拖动模式，回退本次勾选
                btn = self.buttons[idx]
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                return False
        else:
            # 仅当取消的是当前激活的非拖动模式时清空
            if self._active_mode_idx == idx:
                self._active_mode_idx = None
            return True

    def _placeholder_action(self, name):
        QtWidgets.QMessageBox.information(self, "提示", f"{name} 功能暂未实现")

    def _open_fittings(self):
        store = FittingsStore(os.path.join(os.path.dirname(__file__), "datasystem"))
        dialog = FittingsDialog(store, self)
        dialog.exec_()

