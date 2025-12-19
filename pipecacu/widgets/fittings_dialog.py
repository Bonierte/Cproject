import os
from PyQt5 import QtWidgets, QtGui, QtCore
from datasystem.fittings_store import FittingsStore


class FittingsDialog(QtWidgets.QDialog):
    """管件库：仅管理“条例”条目（名称/分类/角度/K等），不与取点对接。"""

    def __init__(self, store: FittingsStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("管件库")
        self.resize(960, 560)
        self._build_ui()
        self._bind()
        self._refresh_table()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        top_bar = QtWidgets.QHBoxLayout()
        self.filter_box = QtWidgets.QComboBox()
        self.filter_box.addItems(["全部", "弯头", "渐扩", "渐缩", "三通", "阀门", "泵", "直管", "其他"])
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("搜索名称/分类")
        self.add_btn = QtWidgets.QPushButton("新增管件")
        top_bar.addWidget(self.filter_box)
        top_bar.addWidget(self.search_edit, 1)
        top_bar.addWidget(self.add_btn)

        body = QtWidgets.QHBoxLayout()
        # 左侧表格
        self.table = QtWidgets.QTableWidget()
        self._set_table_columns("默认")
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        body.addWidget(self.table, 2)

        # 右侧表单
        form_wrap = QtWidgets.QWidget()
        form_layout = QtWidgets.QVBoxLayout(form_wrap)
        self.form_stack = QtWidgets.QStackedWidget()

        # 通用表单（弯头/渐扩/渐缩/其他）
        general_widget = QtWidgets.QWidget()
        general_form = QtWidgets.QFormLayout(general_widget)
        self.id_edit = QtWidgets.QLineEdit()
        self.name_edit = QtWidgets.QLineEdit()
        self.category_box = QtWidgets.QComboBox()
        self.category_box.addItems(["弯头", "渐扩", "渐缩", "三通", "阀门", "泵", "直管", "其他"])
        self.angle_edit = QtWidgets.QLineEdit()
        self.k_edit = QtWidgets.QLineEdit()
        self.in_edit = QtWidgets.QLineEdit()
        self.out_edit = QtWidgets.QLineEdit()
        self.remark_edit = QtWidgets.QLineEdit()
        general_form.addRow("ID", self.id_edit)
        general_form.addRow("名称*", self.name_edit)
        general_form.addRow("分类", self.category_box)
        general_form.addRow("角度/类型", self.angle_edit)
        general_form.addRow("K 值", self.k_edit)
        general_form.addRow("入径", self.in_edit)
        general_form.addRow("出径", self.out_edit)
        general_form.addRow("备注", self.remark_edit)

        # 直管表单
        pipe_widget = QtWidgets.QWidget()
        pipe_form = QtWidgets.QFormLayout(pipe_widget)
        self.id_edit_p = QtWidgets.QLineEdit()
        self.name_edit_p = QtWidgets.QLineEdit()
        self.dn_edit = QtWidgets.QLineEdit()
        self.od_edit = QtWidgets.QLineEdit()
        self.thickness_edit = QtWidgets.QLineEdit()
        self.idmm_edit = QtWidgets.QLineEdit()
        self.remark_edit_p = QtWidgets.QLineEdit()
        pipe_form.addRow("ID", self.id_edit_p)
        pipe_form.addRow("名称*", self.name_edit_p)
        pipe_form.addRow("公称通径DN", self.dn_edit)
        pipe_form.addRow("外径(mm)", self.od_edit)
        pipe_form.addRow("壁厚(mm)", self.thickness_edit)
        pipe_form.addRow("计算内径(mm)", self.idmm_edit)
        pipe_form.addRow("备注", self.remark_edit_p)

        self.form_stack.addWidget(general_widget)  # idx 0
        self.form_stack.addWidget(pipe_widget)     # idx 1

        form_layout.addWidget(self.form_stack)

        btn_bar = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("保存")
        self.del_btn = QtWidgets.QPushButton("删除")
        btn_bar.addWidget(self.save_btn)
        btn_bar.addWidget(self.del_btn)
        form_layout.addLayout(btn_bar)
        body.addWidget(form_wrap, 1)

        main_layout.addLayout(top_bar)
        main_layout.addLayout(body)

    def _bind(self):
        self.add_btn.clicked.connect(self._on_add)
        self.save_btn.clicked.connect(self._on_save)
        self.del_btn.clicked.connect(self._on_delete)
        self.filter_box.currentIndexChanged.connect(self._refresh_table)
        self.search_edit.textChanged.connect(self._refresh_table)
        self.table.itemSelectionChanged.connect(self._on_select_row)
        self.category_box.currentTextChanged.connect(self._on_category_change)

    def _on_add(self):
        # 填入默认空值
        self.id_edit.setText(f"fit_{int(QtCore.QDateTime.currentMSecsSinceEpoch())}")
        self.name_edit.clear()
        self.category_box.setCurrentIndex(0)
        self.angle_edit.clear()
        self.k_edit.clear()
        self.in_edit.setText("/")
        self.out_edit.setText("/")
        self.remark_edit.clear()
        self.id_edit_p.setText(f"pipe_{int(QtCore.QDateTime.currentMSecsSinceEpoch())}")
        self.name_edit_p.clear()
        self.dn_edit.clear()
        self.od_edit.clear()
        self.thickness_edit.clear()
        self.idmm_edit.clear()
        self.remark_edit_p.clear()
        self._switch_form(self.category_box.currentText())

    def _on_save(self):
        cat = self.category_box.currentText()
        if cat == "直管":
            name = self.name_edit_p.text().strip()
            if not name:
                QtWidgets.QMessageBox.warning(self, "提示", "名称必填")
                return
            item = {
                "id": self.id_edit_p.text().strip() or f"pipe_{int(QtCore.QDateTime.currentMSecsSinceEpoch())}",
                "name": name,
                "category": "直管",
                "dn": self._to_number(self.dn_edit.text().strip()),
                "od": self._to_number(self.od_edit.text().strip()),
                "thickness": self._to_number(self.thickness_edit.text().strip()),
                "id_mm": self._to_number(self.idmm_edit.text().strip()),
                "remark": self.remark_edit_p.text().strip(),
            }
        else:
            name = self.name_edit.text().strip()
            if not name:
                QtWidgets.QMessageBox.warning(self, "提示", "名称必填")
                return
            item = {
                "id": self.id_edit.text().strip() or f"fit_{int(QtCore.QDateTime.currentMSecsSinceEpoch())}",
                "name": name,
                "category": cat,
                "angle": self.angle_edit.text().strip(),
                "k": self._to_number(self.k_edit.text().strip()),
                "inDiameter": self.in_edit.text().strip() or "/",
                "outDiameter": self.out_edit.text().strip() or "/",
                "remark": self.remark_edit.text().strip(),
            }
        self.store.upsert(item)
        self._refresh_table()
        self._select_by_id(item["id"])

    def _on_delete(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item_id = self.table.item(rows[0].row(), 0).text()
        self.store.delete(item_id)
        self._refresh_table()

    def _on_select_row(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        item_id = self.table.item(row, 0).text()
        item = self.store.get(item_id)
        cat_text = item.get("category", "")
        if cat_text == "直管":
            self.category_box.setCurrentText("直管")
            self.id_edit_p.setText(item.get("id", ""))
            self.name_edit_p.setText(item.get("name", ""))
            self.dn_edit.setText(str(item.get("dn", "")))
            self.od_edit.setText(str(item.get("od", "")))
            self.thickness_edit.setText(str(item.get("thickness", "")))
            self.idmm_edit.setText(str(item.get("id_mm", "")))
            self.remark_edit_p.setText(item.get("remark", ""))
        else:
            self.id_edit.setText(item.get("id", ""))
            self.name_edit.setText(item.get("name", ""))
            self.category_box.setCurrentText(cat_text or "弯头")
            self.angle_edit.setText(str(item.get("angle", item.get("spec", ""))))
            self.k_edit.setText(str(item.get("k", "")))
            self.in_edit.setText(str(item.get("inDiameter", "")))
            self.out_edit.setText(str(item.get("outDiameter", "")))
            self.remark_edit.setText(item.get("remark", ""))
        self._switch_form(self.category_box.currentText())

    def _refresh_table(self):
        items = self.store.all()
        filt = self.filter_box.currentText()
        keyword = self.search_edit.text().strip()
        filtered = []
        for it in items:
            if filt != "全部" and it.get("category") != filt:
                continue
            if keyword and keyword not in it.get("name", "") and keyword not in it.get("category", ""):
                continue
            filtered.append(it)

        cat_for_table = filt if filt != "全部" else "默认"
        self._set_table_columns(cat_for_table)
        self.table.setRowCount(len(filtered))
        for r, it in enumerate(filtered):
            self._fill_row(self.table, r, it, cat_for_table)

    def _select_by_id(self, item_id: str):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).text() == item_id:
                self.table.selectRow(r)
                break

    @staticmethod
    def _to_number(val: str):
        if val == "":
            return ""
        try:
            return float(val)
        except Exception:
            return val

    def _current_table_category(self):
        filt = self.filter_box.currentText()
        return filt if filt != "全部" else "默认"

    def _switch_form(self, cat: str):
        if cat == "直管":
            self.form_stack.setCurrentIndex(1)
        else:
            self.form_stack.setCurrentIndex(0)

    def _on_category_change(self, text: str):
        self._switch_form(text)

    def _set_table_columns(self, cat: str):
        if cat == "直管":
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(["ID", "名称", "公称通径DN", "外径(mm)", "壁厚(mm)", "计算内径(mm)", "备注"])
        elif cat == "阀门":
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(["ID", "名称", "公称通径DN", "Cv", "Kv", "阻力特性", "备注"])
        elif cat == "泵":
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(["ID", "名称", "型号", "额定流量", "额定压力", "用途", "备注"])
        elif cat == "三通":
            self.table.setColumnCount(6)
            self.table.setHorizontalHeaderLabels(["ID", "名称", "规格", "直通阻力", "支路阻力", "备注"])
        else:
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(["ID", "名称", "分类", "角度/类型", "K", "入径", "出径"])

    def _fill_row(self, table, r: int, it: dict, cat_for_table: str):
        if cat_for_table == "直管":
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it.get("id", ""))))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(it.get("name", ""))))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(it.get("dn", ""))))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(it.get("od", ""))))
            table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(it.get("thickness", ""))))
            table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(it.get("id_mm", ""))))
            table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(it.get("remark", ""))))
        elif cat_for_table == "阀门":
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it.get("id", ""))))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(it.get("name", ""))))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(it.get("dn", ""))))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(it.get("Cv", ""))))
            table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(it.get("Kv", ""))))
            table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(it.get("resistance", ""))))
            table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(it.get("remark", ""))))
        elif cat_for_table == "泵":
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it.get("id", ""))))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(it.get("name", ""))))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(it.get("model", ""))))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(it.get("flow", ""))))
            table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(it.get("pressure", ""))))
            table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(it.get("usage", it.get("remark", "")))))
            table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(it.get("remark", ""))))
        elif cat_for_table == "三通":
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it.get("id", ""))))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(it.get("name", ""))))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(it.get("spec", ""))))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(it.get("k_run", ""))))
            table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(it.get("k_branch", ""))))
            table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(it.get("remark", ""))))
        else:
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(it.get("id", ""))))
            table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(it.get("name", ""))))
            table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(it.get("category", ""))))
            table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(it.get("angle", it.get("spec", "")))))
            table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(it.get("k", ""))))
            table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(it.get("inDiameter", ""))))
            table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(it.get("outDiameter", ""))))

