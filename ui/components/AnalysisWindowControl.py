import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QComboBox,
    QDateTimeEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QCheckBox,
    QScrollArea,
    QFrame,
    QSpinBox,
    QPlainTextEdit,
    QSplitter,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QTextCursor


class AnalysisWindowControl(QWidget):
    """分析窗口左侧控制面板 - 仅支持 telemetry_data 表"""

    # 信号定义
    query_requested = Signal(dict)  # 查询请求
    clear_requested = Signal()  # 清空请求
    export_requested = Signal()  # 导出请求
    field_filter_changed = Signal(dict)  # 字段过滤变更
    info_message = Signal(str, bool)  # 信息消息 (message, is_error)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("AnalysisWindowControl")

        # telemetry_data 表字段定义
        self.telemetry_fields = [
            "id",
            "device_id",
            "device_type",
            "channel",
            "recipe",
            "step",
            "lot_number",
            "wafer_id",
            "pressure",
            "temperature",
            "rf_power",
            "endpoint",
            "gas",
            "timestamp_us",
            "data_timestamp",
            "created_at",
        ]

        self.field_checkboxes = {}

        self.setup_ui()
        self.setup_connections()
        self.initialize_controls()

    def setup_ui(self):
        """设置UI界面"""
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)

        # 使用垂直分割器，上半部分为控制区，下半部分为信息显示区
        self.main_splitter = QSplitter(Qt.Vertical)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(self.main_splitter)

        # 上半部分：控制区域
        control_widget = self.create_control_area()
        self.main_splitter.addWidget(control_widget)

        # 下半部分：信息显示区域
        info_widget = self.create_info_display_area()
        self.main_splitter.addWidget(info_widget)

        # 设置分割器初始比例 (控制区:信息区 = 3:1)
        self.main_splitter.setSizes([600, 200])

        # 设置分割器最小尺寸
        control_widget.setMinimumHeight(400)
        info_widget.setMinimumHeight(100)

    def create_control_area(self) -> QWidget:
        """创建控制区域"""
        control_widget = QWidget()
        layout = QVBoxLayout(control_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 查询设置组
        layout.addWidget(self.create_query_control_group())

        # 字段过滤组（使用滚动区域）
        layout.addWidget(self.create_field_filter_group())

        # 操作按钮组
        layout.addWidget(self.create_action_buttons_group())

        layout.addStretch()

        return control_widget

    def create_info_display_area(self) -> QWidget:
        """创建信息显示区域"""
        info_widget = QGroupBox("系统信息")
        layout = QVBoxLayout(info_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 信息显示文本框
        self.info_text = QPlainTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setFont(QFont("Consolas", 9))
        self.info_text.setPlainText("系统初始化完成，等待操作...")

        # 设置样式
        self.info_text.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 6px;
                color: #495057;
                line-height: 1.4;
            }
        """
        )

        layout.addWidget(self.info_text, 1)  # 占用所有可用空间

        # 操作按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        clear_info_btn = QPushButton("清除")
        clear_info_btn.setFixedHeight(24)
        clear_info_btn.clicked.connect(self.clear_info)
        button_layout.addWidget(clear_info_btn)

        save_info_btn = QPushButton("保存日志")
        save_info_btn.setFixedHeight(24)
        save_info_btn.clicked.connect(self.save_info_log)
        button_layout.addWidget(save_info_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        return info_widget

    def create_query_control_group(self) -> QGroupBox:
        """创建查询控制组 - 使用 FormLayout"""
        group = QGroupBox("查询设置")
        layout = QFormLayout(group)
        layout.setSpacing(8)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # 设备ID过滤
        self.device_filter_edit = QLineEdit()
        self.device_filter_edit.setPlaceholderText("设备ID (支持通配符 %)")
        layout.addRow("设备过滤:", self.device_filter_edit)

        # 设备类型过滤
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["全部", "ETCH", "PVD", "CVD", "WET"])
        layout.addRow("设备类型:", self.device_type_combo)

        # 工艺过滤
        self.recipe_filter_edit = QLineEdit()
        self.recipe_filter_edit.setPlaceholderText("工艺名称 (支持通配符 %)")
        layout.addRow("工艺过滤:", self.recipe_filter_edit)

        # 批次过滤
        self.lot_filter_edit = QLineEdit()
        self.lot_filter_edit.setPlaceholderText("批次号 (支持通配符 %)")
        layout.addRow("批次过滤:", self.lot_filter_edit)

        # 开始时间
        self.start_time_edit = QDateTimeEdit()
        self.start_time_edit.setCalendarPopup(True)
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.start_time_edit.setDateTime(datetime.now() - timedelta(hours=24))
        layout.addRow("开始时间:", self.start_time_edit)

        # 结束时间
        self.end_time_edit = QDateTimeEdit()
        self.end_time_edit.setCalendarPopup(True)
        self.end_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.end_time_edit.setDateTime(datetime.now())
        layout.addRow("结束时间:", self.end_time_edit)

        # 记录数限制
        self.limit_spinbox = QSpinBox()
        self.limit_spinbox.setRange(100, 50000)
        self.limit_spinbox.setValue(5000)
        self.limit_spinbox.setSuffix(" 条")
        layout.addRow("记录限制:", self.limit_spinbox)

        return group

    def create_field_filter_group(self) -> QGroupBox:
        """创建字段过滤组 - 使用滚动区域"""
        group = QGroupBox("显示字段")
        main_layout = QVBoxLayout(group)
        main_layout.setSpacing(4)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(180)  # 限制高度
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动内容区域
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        scroll_layout.setSpacing(2)

        # 字段复选框
        for field in self.telemetry_fields:
            checkbox = QCheckBox(self.get_field_display_name(field))
            checkbox.setChecked(True)
            checkbox.toggled.connect(self.on_field_filter_changed)
            self.field_checkboxes[field] = checkbox
            scroll_layout.addWidget(checkbox)

        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # 快速操作按钮
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedHeight(24)
        select_all_btn.clicked.connect(self.select_all_fields)

        clear_all_btn = QPushButton("清空")
        clear_all_btn.setFixedHeight(24)
        clear_all_btn.clicked.connect(self.clear_all_fields)

        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_all_btn)
        main_layout.addLayout(btn_layout)

        return group

    def create_action_buttons_group(self) -> QGroupBox:
        """创建操作按钮组"""
        group = QGroupBox("操作")
        layout = QVBoxLayout(group)

        # 查询操作
        query_layout = QHBoxLayout()

        self.query_button = QPushButton("🔍 执行查询")
        self.clear_button = QPushButton("🗑️ 清空")

        query_layout.addWidget(self.query_button)
        query_layout.addWidget(self.clear_button)
        layout.addLayout(query_layout)

        # 导出操作
        self.export_button = QPushButton("💾 导出数据")
        self.export_button.setEnabled(False)
        layout.addWidget(self.export_button)

        return group

    def get_field_display_name(self, field: str) -> str:
        """获取字段显示名称"""
        field_names = {
            "id": "ID",
            "device_id": "设备ID",
            "device_type": "设备类型",
            "channel": "通道",
            "recipe": "工艺",
            "step": "步骤",
            "lot_number": "批次号",
            "wafer_id": "晶圆ID",
            "pressure": "压力(Torr)",
            "temperature": "温度(°C)",
            "rf_power": "RF功率(W)",
            "endpoint": "端点信号",
            "gas": "气体流量",
            "timestamp_us": "时间戳(微秒)",
            "data_timestamp": "数据时间",
            "created_at": "创建时间",
        }
        return field_names.get(field, field)

    def setup_connections(self):
        """设置信号连接"""
        self.query_button.clicked.connect(self.on_query_clicked)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)

        # 监听控件变化，记录操作信息
        self.device_filter_edit.textChanged.connect(
            lambda text: self.add_info_message(
                f"设备过滤条件更改: {text}" if text else "设备过滤条件已清空"
            )
        )
        self.device_type_combo.currentTextChanged.connect(
            lambda text: self.add_info_message(f"设备类型选择: {text}")
        )
        self.recipe_filter_edit.textChanged.connect(
            lambda text: self.add_info_message(
                f"工艺过滤条件更改: {text}" if text else "工艺过滤条件已清空"
            )
        )
        self.lot_filter_edit.textChanged.connect(
            lambda text: self.add_info_message(
                f"批次过滤条件更改: {text}" if text else "批次过滤条件已清空"
            )
        )
        self.start_time_edit.dateTimeChanged.connect(
            lambda dt: self.add_info_message(
                f"开始时间更改: {dt.toString('yyyy-MM-dd hh:mm')}"
            )
        )
        self.end_time_edit.dateTimeChanged.connect(
            lambda dt: self.add_info_message(
                f"结束时间更改: {dt.toString('yyyy-MM-dd hh:mm')}"
            )
        )
        self.limit_spinbox.valueChanged.connect(
            lambda value: self.add_info_message(f"记录限制更改: {value} 条")
        )

    def initialize_controls(self):
        """初始化控件"""
        self.add_info_message("控制面板初始化完成")
        self.add_info_message("默认查询时间范围: 最近24小时")
        self.add_info_message("默认记录限制: 5000条")
        self.add_info_message("所有显示字段默认已选中")

    def get_query_params(self) -> dict:
        """获取查询参数"""
        params = {
            "device_id": self.device_filter_edit.text().strip() or None,
            "device_type": (
                None
                if self.device_type_combo.currentText() == "全部"
                else self.device_type_combo.currentText()
            ),
            "recipe": self.recipe_filter_edit.text().strip() or None,
            "lot_number": self.lot_filter_edit.text().strip() or None,
            "start_time": self.start_time_edit.dateTime().toPython(),
            "end_time": self.end_time_edit.dateTime().toPython(),
            "limit": self.limit_spinbox.value(),
        }

        # 记录查询参数
        self.add_info_message(f"查询参数设置: {self._format_query_params(params)}")

        return params

    def _format_query_params(self, params: dict) -> str:
        """格式化查询参数用于显示"""
        parts = []
        if params.get("device_id"):
            parts.append(f"设备ID={params['device_id']}")
        if params.get("device_type"):
            parts.append(f"设备类型={params['device_type']}")
        if params.get("recipe"):
            parts.append(f"工艺={params['recipe']}")
        if params.get("lot_number"):
            parts.append(f"批次={params['lot_number']}")

        time_range = f"时间={params['start_time'].strftime('%m-%d %H:%M')}~{params['end_time'].strftime('%m-%d %H:%M')}"
        parts.append(time_range)
        parts.append(f"限制={params['limit']}条")

        return ", ".join(parts)

    def set_buttons_enabled(
        self, query_enabled: bool = True, data_buttons_enabled: bool = False
    ):
        """设置按钮启用状态"""
        self.query_button.setEnabled(query_enabled)
        self.export_button.setEnabled(data_buttons_enabled)

        status = "启用" if query_enabled else "禁用"
        self.add_info_message(f"查询按钮状态: {status}")

    def select_all_fields(self):
        """全选字段"""
        for checkbox in self.field_checkboxes.values():
            checkbox.setChecked(True)
        self.add_info_message("已全选所有显示字段")

    def clear_all_fields(self):
        """清空字段选择"""
        for checkbox in self.field_checkboxes.values():
            checkbox.setChecked(False)
        self.add_info_message("已清空所有显示字段选择")

    def add_info_message(self, message: str, is_error: bool = False):
        """添加信息消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if is_error:
            formatted_message = f"[{timestamp}] ❌ {message}"
        else:
            formatted_message = f"[{timestamp}] ℹ️ {message}"

        self.info_text.appendPlainText(formatted_message)

        # 滚动到底部
        self.info_text.moveCursor(QTextCursor.End)
        self.info_text.ensureCursorVisible()  # 确保光标可见（自动滚动）

        # 发射信号给主窗口
        self.info_message.emit(message, is_error)

    def clear_info(self):
        """清除信息显示"""
        self.info_text.clear()
        self.info_text.setPlainText("信息已清除")

    def save_info_log(self):
        """保存信息日志"""
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "保存系统日志",
            f"system_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "文本文件 (*.txt)",
        )

        if file_name:
            try:
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(self.info_text.toPlainText())
                self.add_info_message(f"日志已保存到: {file_name}")
            except Exception as e:
                self.add_info_message(f"保存日志失败: {e}", is_error=True)

    @Slot()
    def on_query_clicked(self):
        """查询按钮点击"""
        self.add_info_message("开始执行数据查询...")
        query_params = self.get_query_params()
        self.query_requested.emit(query_params)

    @Slot()
    def on_field_filter_changed(self):
        """字段过滤变更"""
        field_filters = {
            field: checkbox.isChecked()
            for field, checkbox in self.field_checkboxes.items()
        }

        # 统计选中的字段数量
        selected_count = sum(1 for checked in field_filters.values() if checked)
        self.add_info_message(
            f"字段显示设置更新: {selected_count}/{len(field_filters)} 个字段显示"
        )

        self.field_filter_changed.emit(field_filters)
