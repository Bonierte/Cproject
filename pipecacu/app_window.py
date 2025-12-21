import os
import json
import shutil
from PyQt5 import QtWidgets, QtGui, QtCore
from main_window import Ui_MainWindow
from design.designer_area import GridWidget
from datasystem.fittings_store import FittingsStore
from widgets.fittings_dialog import FittingsDialog
from calculation.physics import Fluid # 新增导入
from calculation.manager import CalculationManager


class AppWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    """主窗口封装：布局、样式、按钮逻辑、画布网格和取点"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        
        # 初始全局流体设置 (默认使用用户指定的 VG320)
        self.current_fluid = Fluid(name="VG320 滑油", temp=40.0)
        
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
        new_act = QtWidgets.QAction("新建", self)
        save_act = QtWidgets.QAction("保存", self)
        fittings_act = QtWidgets.QAction("管件库", self)
        calc_act = QtWidgets.QAction("压力计算", self)
        menubar.addAction(open_act)
        menubar.addAction(new_act)
        menubar.addAction(save_act)
        menubar.addAction(fittings_act)
        menubar.addAction(calc_act)
        self.menu_actions = {"open": open_act, "new": new_act, "save": save_act, "fittings": fittings_act, "calc": calc_act}
        fittings_act.triggered.connect(self._open_fittings)
        open_act.triggered.connect(self._open_project)
        new_act.triggered.connect(self._new_project)
        save_act.triggered.connect(self._save_project)
        calc_act.triggered.connect(self._run_calculation)

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
            (icon_from("Yxiang.svg", self.style().standardIcon(QtWidgets.QStyle.SP_DriveHDIcon)), "油箱"),
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
            elif idx == 3:  # 油箱点
                btn.toggled.connect(lambda c, i=idx: self._toggle_tank_point(i, c))
            elif idx == 4:  # 油泵点
                btn.toggled.connect(lambda c, i=idx: self._toggle_pump_point(i, c))
            elif idx == 5:  # 三通点
                btn.toggled.connect(lambda c, i=idx: self._toggle_tee_point(i, c))
            elif idx == 6:  # 阀门点
                btn.toggled.connect(lambda c, i=idx: self._toggle_valve_point(i, c))
            elif idx == 7:  # 删除
                btn.toggled.connect(lambda c, i=idx: self._toggle_delete(i, c))
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
            lbl = QtWidgets.QLabel(f"  {text}")  # 加两个空格增加缩进感
            lbl.setFixedHeight(30)  # 固定高度，更有条理性
            # 标题背景色与边框色一致，文字深灰，去掉底部边框，使其与面板融为一体
            lbl.setStyleSheet("""
                background-color: #d9d9d9; 
                color: #333333; 
                font-weight: bold; 
                border: none;
            """)
            return lbl

        # 目录面板 (管路结构)
        catalog_layout = QtWidgets.QVBoxLayout()
        catalog_layout.setContentsMargins(0, 0, 0, 0)
        catalog_layout.setSpacing(0)
        
        # 项目名称标签 - 优化为更高级的深色调，与标题区分开
        self.project_label = QtWidgets.QLabel("  项目：未命名项目")
        self.project_label.setFixedHeight(32)
        self.project_label.setStyleSheet("""
            background-color: #01579b; 
            color: white; 
            font-weight: bold;
            border: none;
        """)
        catalog_layout.addWidget(self.project_label)
        
        catalog_layout.addWidget(make_title("管路结构"))
        
        # 树状目录容器 - 增加 4px 的边距，让列表不贴边
        tree_container = QtWidgets.QWidget()
        tree_layout = QtWidgets.QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(4, 4, 4, 4)
        
        self.catalog_tree = QtWidgets.QTreeWidget()
        self.catalog_tree.setHeaderHidden(True)
        self.catalog_tree.setIndentation(15)
        self.catalog_tree.setStyleSheet("QTreeWidget { border: none; background: transparent; }")
        
        # 初始化顶层节点
        self.node_group = QtWidgets.QTreeWidgetItem(self.catalog_tree, ["节点"])
        self.line_group = QtWidgets.QTreeWidgetItem(self.catalog_tree, ["管路"])
        self.catalog_tree.expandAll()
        
        tree_layout.addWidget(self.catalog_tree)
        catalog_layout.addWidget(tree_container)
        self.catalog.setLayout(catalog_layout)

        # 节点参数面板
        info_layout = QtWidgets.QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)
        info_layout.addWidget(make_title("节点参数"))
        
        info_content = QtWidgets.QWidget()
        info_content_layout = QtWidgets.QVBoxLayout(info_content)
        info_content_layout.setContentsMargins(6, 6, 6, 6)
        # 这里预留给参数表
        info_content_layout.addStretch()
        
        info_layout.addWidget(info_content)
        self.information.setLayout(info_layout)

        # 计算结果面板
        calc_layout = QtWidgets.QVBoxLayout()
        calc_layout.setContentsMargins(0, 0, 0, 0)
        calc_layout.setSpacing(0)
        calc_layout.addWidget(make_title("计算结果"))
        
        calc_content = QtWidgets.QWidget()
        calc_content_layout = QtWidgets.QVBoxLayout(calc_content)
        calc_content_layout.setContentsMargins(2, 2, 2, 2)
        
        # 使用表格展示压力和流量
        self.result_table = QtWidgets.QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["名称", "类型", "压力 (kPa)", "流量 (m³/h)"])
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.result_table.setStyleSheet("QTableWidget { border: none; }")
        calc_content_layout.addWidget(self.result_table)
        
        calc_layout.addWidget(calc_content)
        self.caculate.setLayout(calc_layout)

        # 日志信息面板
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(0)
        log_layout.addWidget(make_title("日志信息"))
        
        log_content = QtWidgets.QWidget()
        log_content_layout = QtWidgets.QVBoxLayout(log_content)
        log_content_layout.setContentsMargins(2, 2, 2, 2)
        
        # 使用文本框展示日志
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("QTextEdit { border: none; background: #fdfdfd; font-family: 'Consolas'; }")
        log_content_layout.addWidget(self.log_text)
        
        log_layout.addWidget(log_content)
        self.log.setLayout(log_layout)

    def _build_canvas(self):
        canvas_layout = QtWidgets.QVBoxLayout()
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.grid = GridWidget(self.canvas)
        canvas_layout.addWidget(self.grid)
        self.canvas.setLayout(canvas_layout)
        # 连接数据变化信号
        self.grid.data_changed.connect(self._refresh_catalog)
        # 初始刷新一次
        self._refresh_catalog()

    def _refresh_catalog(self):
        """刷新左侧目录树"""
        if not hasattr(self, "catalog_tree"):
            return
            
        self.node_group.takeChildren()
        self.line_group.takeChildren()
        
        # 添加点
        for p in self.grid._points:
            label = p.get("label", "")
            QtWidgets.QTreeWidgetItem(self.node_group, [label])
            
        # 添加线
        for ln in self.grid._lines:
            label = ln.get("label", "")
            QtWidgets.QTreeWidgetItem(self.line_group, [label])
            
        self.catalog_tree.expandAll()

    def _rebuild_layout(self):
        # 统一面板样式：取消系统默认边框，完全交给 CSS 控制，实现标题栏与边框的无缝融合
        panel_style = "QFrame { border: 4px solid #d9d9d9; background-color: white; }"
        for frame in [self.design_buttons, self.catalog, self.information, self.canvas, self.caculate, self.log]:
            frame.setFrameShape(QtWidgets.QFrame.NoFrame)  # 取消原生形状
            frame.setLineWidth(1)
            frame.setStyleSheet(panel_style)

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

    def _toggle_tank_point(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_add_point_enabled(checked)
            self.grid.set_connect_enabled(False)
            self.grid.set_point_type("tank")
            if not checked:
                self.grid.set_add_point_enabled(False)

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

    def _toggle_delete(self, idx: int, checked: bool):
        if not self._allow_mode_toggle(idx, checked):
            return
        if hasattr(self, "grid"):
            self.grid.set_delete_enabled(checked)
            if checked:
                self.grid.set_add_point_enabled(False)
                self.grid.set_connect_enabled(False)

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

    def _new_project(self):
        """新建工程：确认后清空当前画布和临时数据"""
        if not hasattr(self, "grid") or not hasattr(self.grid, "temp_data"):
            return

        reply = QtWidgets.QMessageBox.question(
            self, "新建工程", "确定要新建工程吗？当前未保存的设计将会丢失。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.grid.temp_data.clear()
            self.grid.load_from_temp()
            self.project_label.setText("项目：未命名项目")
            self.result_table.setRowCount(0)
            self.log_text.clear()
            QtWidgets.QMessageBox.information(self, "提示", "已创建新画布")

    def _save_project(self):
        """将当前临时数据保存为正式文件"""
        if not hasattr(self, "grid") or not hasattr(self.grid, "temp_data"):
            return
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存工程", "", "Project Files (*.json)")
        if path:
            try:
                # 直接将当前内存中的数据写入目标路径
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.grid.temp_data.data, f, ensure_ascii=False, indent=2)
                
                # 更新项目名称显示
                filename = os.path.basename(path)
                self.project_label.setText(f"项目：{filename}")
                
                QtWidgets.QMessageBox.information(self, "成功", f"工程已保存至：\n{path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "错误", f"保存失败：\n{str(e)}")

    def _open_project(self):
        """打开现有工程文件并加载到画布"""
        if not hasattr(self, "grid") or not hasattr(self.grid, "temp_data"):
            return

        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "打开工程", "", "Project Files (*.json)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                
                # 简单校验
                if "points" not in new_data or "lines" not in new_data:
                    raise ValueError("无效的工程文件格式")

                # 更新临时数据并同步到文件
                self.grid.temp_data.data = new_data
                self.grid.temp_data._save()
                
                # 更新项目名称显示
                filename = os.path.basename(path)
                self.project_label.setText(f"项目：{filename}")
                
                # 让画布重新从临时数据加载
                self.grid.load_from_temp()
                QtWidgets.QMessageBox.information(self, "成功", "工程加载完成")
                self._add_log(f"成功打开工程: {filename}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "错误", f"打开失败：\n{str(e)}")

    def _run_calculation(self):
        """执行仿真计算"""
        # 1. 查找系统中的油品设置 (从油箱节点获取)
        selected_fluid = None
        if hasattr(self, "grid"):
            # 遍历所有点，寻找油箱类型并获取其油品数据
            for p in self.grid._points:
                if p.get("ptype") == "tank" and p.get("fluid_data"):
                    fluid_data = p.get("fluid_data")
                    selected_fluid = Fluid(name=fluid_data["name"])
                    selected_fluid.OIL_DATABASE[fluid_data["name"]] = {
                        "rho_15": fluid_data.get("rho_15", 900.0),
                        "v_40": fluid_data.get("v_40", 40.0)
                    }
                    selected_fluid.update_properties()
                    break # 找到一个油箱的油品设置即可，暂不考虑多种油品混合
        
        if not selected_fluid:
            QtWidgets.QMessageBox.warning(self, "提示", "系统中未找到油箱或油箱未设置油品。请先添加油箱并选择油品。")
            return

        self.current_fluid = selected_fluid
        self._add_log(f"开始压力仿真... (选中油品: {self.current_fluid.name})")
        
        # 2. 执行仿真
        if not hasattr(self, "grid") or not hasattr(self.grid, "temp_data"):
            return
            
        json_path = self.grid.temp_data.json_path
        manager = CalculationManager(json_path)
        response = manager.run(fluid=self.current_fluid)
        
        if response.get("success"):
            self._add_log(f"计算完成", "green")
            self._display_results(response.get("result", {}))
        else:
            self._add_log(f"计算失败: {response['msg']}", "red")
            QtWidgets.QMessageBox.warning(self, "计算失败", response['msg'])

    def _display_results(self, results):
        """在表格中展示计算结果"""
        pressures = results.get("pressures", {})
        node_flows = results.get("node_flows", {}) 
        flows = results.get("flows", {})
        
        # 合并展示
        self.result_table.setRowCount(0)
        self.result_table.setRowCount(len(pressures) + len(flows))
        
        row = 0
        # 展示节点数据
        for node_id in pressures.keys():
            p_val = pressures[node_id]
            q_node = node_flows.get(node_id, 0.0)
            
            self.result_table.setItem(row, 0, QtWidgets.QTableWidgetItem(node_id))
            self.result_table.setItem(row, 1, QtWidgets.QTableWidgetItem("节点"))
            self.result_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{p_val / 1000.0:.3f}"))
            self.result_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{q_node * 3600.0:.4f}")) # 换算为 m3/h
            row += 1
            
        # 展示管路流量
        for line_id, q_val in flows.items():
            self.result_table.setItem(row, 0, QtWidgets.QTableWidgetItem(line_id))
            self.result_table.setItem(row, 1, QtWidgets.QTableWidgetItem("管路"))
            self.result_table.setItem(row, 2, QtWidgets.QTableWidgetItem("-")) # 管路两端压力不同，不显示单点压力
            self.result_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{q_val * 3600.0:.4f}")) # 换算为 m3/h
            row += 1

    def _add_log(self, message, color="black"):
        """向日志面板添加带时间戳的信息"""
        timestamp = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        formatted_msg = f'<span style="color: gray;">[{timestamp}]</span> <span style="color: {color};">{message}</span>'
        self.log_text.append(formatted_msg)

    def closeEvent(self, event):
        """窗口关闭时清空临时数据，防止下次启动干扰"""
        if hasattr(self, "grid") and hasattr(self.grid, "temp_data"):
            self.grid.temp_data.clear()
        event.accept()

