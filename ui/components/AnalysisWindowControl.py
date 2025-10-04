import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

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
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon

from utils.path import ICON_DIR


class AnalysisWindowControl(QWidget):
    """分析窗口左侧控制面板"""

    # 信号定义
    query_requested = Signal(dict)  # 查询请求
    clear_requested = Signal()  # 清空请求
    export_requested = Signal()  # 导出请求
    chart_requested = Signal()  # 图表请求
    table_type_changed = Signal(str)  # 表类型变更
    field_filter_changed = Signal(dict)  # 字段过滤变更
    time_range_changed = Signal(datetime, datetime)  # 时间范围变更
    auto_refresh_toggled = Signal(bool)  # 自动刷新切换

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("AnalysisWindowControl")

        # 状态变量
        self.current_table_type = "telemetry_data"
        self.field_checkboxes = {}
        self.table_fields = {
            "telemetry_data": [
                "id",
                "device_id",
                "channel",
                "source",
                "temperature",
                "pressure",
                "rf_power",
                "endpoint",
                "humidity",
                "vibration",
                "data_timestamp",
                "created_at",
            ],
            "alerts": [
                "id",
                "device_id",
                "alert_type",
                "severity",
                "message",
                "data_timestamp",
                "created_at",
                "resolved_at",
            ],
            "device_events": [
                "id",
                "device_id",
                "event_type",
                "severity",
                "data_timestamp",
                "created_at",
            ],
            "error_logs": [
                "id",
                "device_id",
                "error_type",
                "error_code",
                "message",
                "severity",
                "data_timestamp",
                "created_at",
            ],
        }

        # 配置
        self.config = {"default_limit": 1000, "field_filter_height": 200}

        self.setup_ui()
        self.setup_connections()
        self.initialize_controls()

        self.logger.info("分析窗口控制面板初始化完成")

    def setup_ui(self):
        """设置UI界面"""
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        self.setObjectName("analysisWindowControl")

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动内容容器
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(12)

        # 添加控制组件
        scroll_layout.addWidget(self.create_query_control_group())
        scroll_layout.addWidget(self.create_time_preset_group())
        scroll_layout.addWidget(self.create_field_filter_group())
        scroll_layout.addWidget(self.create_advanced_options_group())
        scroll_layout.addWidget(self.create_action_buttons_group())

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def create_query_control_group(self) -> QGroupBox:
        """创建查询控制组"""
        group = QGroupBox("查询设置")
        group.setObjectName("queryControlGroup")

        layout = QFormLayout(group)
        layout.setSpacing(8)

        # 数据表选择
        self.table_type_combo = QComboBox()
        self.table_type_combo.addItems(
            ["telemetry_data", "alerts", "device_events", "error_logs"]
        )
        self.table_type_combo.setCurrentText(self.current_table_type)

        # 设备过滤
        self.device_filter_edit = QLineEdit()
        self.device_filter_edit.setPlaceholderText("设备ID过滤")

        # 时间范围
        self.start_time_edit = QDateTimeEdit()
        self.start_time_edit.setCalendarPopup(True)
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.start_time_edit.setDateTime(datetime.now() - timedelta(hours=24))

        self.end_time_edit = QDateTimeEdit()
        self.end_time_edit.setCalendarPopup(True)
        self.end_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.end_time_edit.setDateTime(datetime.now())

        # 记录限制
        self.limit_edit = QLineEdit()
        self.limit_edit.setText(str(self.config["default_limit"]))
        self.limit_edit.setPlaceholderText("记录数限制")

        # 添加到布局
        layout.addRow(QLabel("数据表:"), self.table_type_combo)
        layout.addRow(QLabel("设备过滤:"), self.device_filter_edit)
        layout.addRow(QLabel("开始时间:"), self.start_time_edit)
        layout.addRow(QLabel("结束时间:"), self.end_time_edit)
        layout.addRow(QLabel("记录限制:"), self.limit_edit)

        return group

    def create_time_preset_group(self) -> QGroupBox:
        """创建时间预设组"""
        group = QGroupBox("时间快捷")
        group.setObjectName("timePresetGroup")

        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(6)

        # 时间预设按钮网格
        preset_grid = QGridLayout()
        preset_grid.setSpacing(4)

        time_presets = [
            ("1小时", lambda: self.set_time_range(hours=1)),
            ("6小时", lambda: self.set_time_range(hours=6)),
            ("24小时", lambda: self.set_time_range(hours=24)),
            ("3天", lambda: self.set_time_range(days=3)),
            ("7天", lambda: self.set_time_range(days=7)),
            ("30天", lambda: self.set_time_range(days=30)),
        ]

        for i, (preset_name, preset_func) in enumerate(time_presets):
            btn = QPushButton(preset_name)
            btn.setObjectName("timePresetButton")
            btn.clicked.connect(preset_func)
            preset_grid.addWidget(btn, i // 2, i % 2)

        layout.addLayout(preset_grid)
        return group

    def create_field_filter_group(self) -> QGroupBox:
        """创建字段过滤组"""
        group = QGroupBox("字段过滤")
        group.setObjectName("fieldFilterGroup")

        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)

        # 字段过滤滚动区域
        self.field_scroll_area = QScrollArea()
        self.field_scroll_area.setWidgetResizable(True)
        self.field_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.field_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.field_scroll_area.setFixedHeight(self.config["field_filter_height"])

        # 字段容器
        self.field_container = QWidget()
        self.field_filter_layout = QVBoxLayout(self.field_container)
        self.field_filter_layout.setContentsMargins(0, 0, 0, 0)
        self.field_filter_layout.setSpacing(2)

        self.field_scroll_area.setWidget(self.field_container)
        layout.addWidget(self.field_scroll_area)

        # 快速操作按钮
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)

        select_all_btn = QPushButton("全选")
        select_all_btn.setObjectName("fieldControlButton")
        select_all_btn.setFixedHeight(24)
        select_all_btn.clicked.connect(self.select_all_fields)

        clear_all_btn = QPushButton("清空")
        clear_all_btn.setObjectName("fieldControlButton")
        clear_all_btn.setFixedHeight(24)
        clear_all_btn.clicked.connect(self.clear_all_fields)

        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(clear_all_btn)
        layout.addLayout(button_layout)

        return group

    def create_advanced_options_group(self) -> QGroupBox:
        """创建高级选项组"""
        group = QGroupBox("高级选项")
        group.setObjectName("advancedOptionsGroup")

        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self.order_desc_checkbox = QCheckBox("降序排列")
        self.order_desc_checkbox.setChecked(True)
        layout.addWidget(self.order_desc_checkbox)

        self.auto_refresh_checkbox = QCheckBox("自动刷新(30s)")
        layout.addWidget(self.auto_refresh_checkbox)

        self.enable_comparison_checkbox = QCheckBox("启用数据对比")
        layout.addWidget(self.enable_comparison_checkbox)

        return group

    def create_action_buttons_group(self) -> QGroupBox:
        """创建操作按钮组"""
        group = QGroupBox("操作")
        group.setObjectName("actionButtonsGroup")

        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)

        # 主要操作按钮
        main_btn_layout = QHBoxLayout()

        self.query_button = QPushButton("🔍 执行查询")
        self.query_button.setObjectName("primaryActionButton")

        self.clear_button = QPushButton("🗑️ 清空数据")
        self.clear_button.setObjectName("secondaryActionButton")

        main_btn_layout.addWidget(self.query_button)
        main_btn_layout.addWidget(self.clear_button)
        layout.addLayout(main_btn_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # 数据处理按钮
        data_btn_layout = QHBoxLayout()

        self.export_button = QPushButton("📤 导出数据")
        self.export_button.setEnabled(False)

        self.chart_button = QPushButton("📊 生成图表")
        self.chart_button.setEnabled(False)

        data_btn_layout.addWidget(self.export_button)
        data_btn_layout.addWidget(self.chart_button)
        layout.addLayout(data_btn_layout)

        return group

    def setup_connections(self):
        """设置信号连接"""
        # 控件信号连接
        self.query_button.clicked.connect(self.on_query_clicked)
        self.clear_button.clicked.connect(self.on_clear_clicked)
        self.export_button.clicked.connect(self.on_export_clicked)
        self.chart_button.clicked.connect(self.on_chart_clicked)

        # 表格类型变化
        self.table_type_combo.currentTextChanged.connect(self.on_table_type_changed)

        # 时间范围变化
        self.start_time_edit.dateTimeChanged.connect(self.on_time_range_changed)
        self.end_time_edit.dateTimeChanged.connect(self.on_time_range_changed)

        # 高级选项
        self.auto_refresh_checkbox.toggled.connect(self.on_auto_refresh_toggled)

    def initialize_controls(self):
        """初始化控件"""
        self.update_field_list(self.current_table_type)

    def update_field_list(self, table_type: str):
        """更新字段列表"""
        # 清空现有字段复选框
        for checkbox in self.field_checkboxes.values():
            checkbox.deleteLater()
        self.field_checkboxes.clear()

        # 获取字段列表
        fields = self.table_fields.get(table_type, [])

        # 添加字段复选框
        for field in fields:
            checkbox = QCheckBox(field)
            checkbox.setChecked(True)  # 默认全部选中
            checkbox.toggled.connect(self.on_field_filter_changed)

            self.field_filter_layout.addWidget(checkbox)
            self.field_checkboxes[field] = checkbox

    def get_query_params(self) -> dict:
        """获取查询参数"""
        return {
            "table_type": self.table_type_combo.currentText(),
            "device_filter": self.device_filter_edit.text().strip() or None,
            "start_time": self.start_time_edit.dateTime().toPython(),
            "end_time": self.end_time_edit.dateTime().toPython(),
            "limit": int(self.limit_edit.text() or self.config["default_limit"]),
            "order_desc": self.order_desc_checkbox.isChecked(),
            "enable_comparison": self.enable_comparison_checkbox.isChecked(),
        }

    def get_field_filters(self) -> dict:
        """获取字段过滤器状态"""
        return {
            field: checkbox.isChecked()
            for field, checkbox in self.field_checkboxes.items()
        }

    def set_buttons_enabled(
        self, query_enabled: bool = True, data_buttons_enabled: bool = False
    ):
        """设置按钮启用状态"""
        self.query_button.setEnabled(query_enabled)
        self.export_button.setEnabled(data_buttons_enabled)
        self.chart_button.setEnabled(data_buttons_enabled)

    def set_time_range(self, hours: int = None, days: int = None):
        """设置时间范围"""
        now = datetime.now()
        if hours:
            start_time = now - timedelta(hours=hours)
        elif days:
            start_time = now - timedelta(days=days)
        else:
            return

        self.start_time_edit.setDateTime(start_time)
        self.end_time_edit.setDateTime(now)

        # 发送时间范围变更信号
        self.time_range_changed.emit(start_time, now)

    def select_all_fields(self):
        """全选字段"""
        for checkbox in self.field_checkboxes.values():
            checkbox.setChecked(True)

    def clear_all_fields(self):
        """清空字段选择"""
        for checkbox in self.field_checkboxes.values():
            checkbox.setChecked(False)

    # === 槽函数 ===

    @Slot()
    def on_query_clicked(self):
        """查询按钮点击"""
        query_params = self.get_query_params()
        self.query_requested.emit(query_params)

    @Slot()
    def on_clear_clicked(self):
        """清空按钮点击"""
        self.clear_requested.emit()

    @Slot()
    def on_export_clicked(self):
        """导出按钮点击"""
        self.export_requested.emit()

    @Slot()
    def on_chart_clicked(self):
        """图表按钮点击"""
        self.chart_requested.emit()

    @Slot(str)
    def on_table_type_changed(self, table_type: str):
        """表格类型变更"""
        self.current_table_type = table_type
        self.update_field_list(table_type)
        self.table_type_changed.emit(table_type)

    @Slot()
    def on_field_filter_changed(self):
        """字段过滤变更"""
        field_filters = self.get_field_filters()
        self.field_filter_changed.emit(field_filters)

    @Slot()
    def on_time_range_changed(self):
        """时间范围变更"""
        start_time = self.start_time_edit.dateTime().toPython()
        end_time = self.end_time_edit.dateTime().toPython()
        self.time_range_changed.emit(start_time, end_time)

    @Slot(bool)
    def on_auto_refresh_toggled(self, enabled: bool):
        """自动刷新切换"""
        self.auto_refresh_toggled.emit(enabled)
