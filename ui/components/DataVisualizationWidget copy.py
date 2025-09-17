import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QComboBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QStackedWidget,
    QGridLayout,
    QHeaderView,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QColor
import pyqtgraph as pg
import numpy as np
from collections import deque, defaultdict
import time
from datetime import datetime

from core.visualization_controller import VisualizationController
from .DeviceControlPanel import DeviceControlPanel
from .DeviceOverviewTable import DeviceOverviewTable
from .DeviceChartsWidget import DeviceChartsWidget


class DataVisualizationWidget(QWidget):
    device_selected = Signal(str)  # 设备选择信号
    visualization_mode_changed = Signal(str)  # 可视化模式变更信号

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DataVisualizationWidget")

        # 数据缓存 - 按设备ID组织
        self.device_data = defaultdict(
            lambda: {
                "temperature": deque(maxlen=300),
                "pressure": deque(maxlen=300),
                "rf_power": deque(maxlen=300),
                "endpoint": deque(maxlen=300),
                "humidity": deque(maxlen=300),
                "vibration": deque(maxlen=300),
                "focus_error": deque(maxlen=300),
                "timestamps": deque(maxlen=300),
                "last_update": None,
                "device_type": "UNKNOWN",
                "recipe": "",
                "step": "",
                "lot_id": "",
                "wafer_id": "",
            }
        )

        # 创建可视化控制器
        self.controller = controller or VisualizationController()
        self.current_device = None

        self.setup_ui()
        self.connect_signals()
        self.setup_timers()

        self.logger.info("数据可视化组件初始化完成")

    def setup_ui(self):
        """重构后的用户界面 - 左右分栏布局"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 🔥 左侧：数据可视化区域 (75%)
        self.visualization_area = self.create_visualization_area()
        main_layout.addWidget(self.visualization_area, 3)

        # 🔥 右侧：设备选择和状态面板 (25%)
        self.control_panel = self.create_right_control_panel()
        main_layout.addWidget(self.control_panel, 1)

    def create_visualization_area(self) -> QWidget:
        """创建左侧数据可视化区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 顶部设备信息条
        self.device_info_bar = self.create_device_info_bar()
        layout.addWidget(self.device_info_bar)

        # 可视化内容区 - 使用StackedWidget支持多种视图
        self.stacked_widget = QStackedWidget()

        # 页面0：表格视图
        self.table_page = self.create_table_page()
        self.stacked_widget.addWidget(self.table_page)

        # 页面1：仪表盘视图 - 暂时置空
        self.dashboard_page = self.create_dashboard_page()
        self.stacked_widget.addWidget(self.dashboard_page)

        # 页面2：趋势图视图
        self.chart_page = self.create_chart_page()
        self.stacked_widget.addWidget(self.chart_page)

        layout.addWidget(self.stacked_widget)

        # 默认显示表格
        self.stacked_widget.setCurrentIndex(0)

        return widget

    def create_device_info_bar(self) -> QWidget:
        """创建设备信息条 - 显示当前选中设备的基本信息"""
        bar = QFrame()
        bar.setFrameStyle(QFrame.StyledPanel)
        bar.setMaximumHeight(65)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 10, 15, 10)

        # 设备标识图标
        device_icon = QLabel("🏭")
        device_icon.setFont(QFont("Arial", 18))
        layout.addWidget(device_icon)

        # 当前设备名称
        self.current_device_label = QLabel("未选择设备")
        self.current_device_label.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(self.current_device_label)

        # 分隔符
        separator1 = QLabel("|")
        layout.addWidget(separator1)

        # 设备类型
        self.device_type_label = QLabel("--")
        self.device_type_label.setFont(QFont("Arial", 12))
        layout.addWidget(self.device_type_label)

        # 分隔符
        separator2 = QLabel("|")
        layout.addWidget(separator2)

        # 当前工艺
        recipe_icon = QLabel("⚙️")
        recipe_icon.setFont(QFont("Arial", 14))
        layout.addWidget(recipe_icon)

        self.current_recipe_label = QLabel("--")
        self.current_recipe_label.setFont(QFont("Arial", 11))
        layout.addWidget(self.current_recipe_label)

        layout.addStretch()

        # 连接状态指示
        self.connection_status_label = QLabel("⚫ 离线")
        self.connection_status_label.setFont(QFont("Arial", 11, QFont.Bold))
        layout.addWidget(self.connection_status_label)

        return bar

    def create_right_control_panel(self) -> QWidget:
        """创建右侧控制面板 - 设备选择和状态信息"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.StyledPanel)
        panel.setMaximumWidth(280)
        panel.setMinimumWidth(260)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 🔥 设备选择区域
        device_group = self.create_device_selection_group()
        layout.addWidget(device_group)

        # 🔥 实时状态区域
        status_group = self.create_status_group()
        layout.addWidget(status_group)

        # 🔥 设备详细信息
        device_info_group = self.create_device_info_group()
        layout.addWidget(device_info_group)

        # 🔥 数据统计
        stats_group = self.create_stats_group()
        layout.addWidget(stats_group)

        layout.addStretch()

        # 🔥 底部操作按钮
        actions_group = self.create_actions_group()
        layout.addWidget(actions_group)

        return panel

    def create_device_selection_group(self) -> QWidget:
        """设备选择组"""
        group = QGroupBox("设备选择")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QVBoxLayout(group)

        # 设备下拉框
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(35)
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        layout.addWidget(self.device_combo)

        # 设备数量统计
        self.device_count_label = QLabel("设备数: 0")
        self.device_count_label.setFont(QFont("Arial", 9))
        layout.addWidget(self.device_count_label)

        return group

    def create_status_group(self) -> QWidget:
        """实时状态组"""
        group = QGroupBox("连接状态")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QVBoxLayout(group)

        # 状态指示器
        status_layout = QHBoxLayout()

        self.status_indicator = QLabel("⚫")
        self.status_indicator.setFont(QFont("Arial", 16))
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel("离线")
        self.status_text.setFont(QFont("Arial", 11, QFont.Bold))
        status_layout.addWidget(self.status_text)

        status_layout.addStretch()
        layout.addLayout(status_layout)

        # 最后更新时间
        self.last_update_label = QLabel("最后更新: --")
        self.last_update_label.setFont(QFont("Arial", 9))
        layout.addWidget(self.last_update_label)

        # 数据接收率
        self.data_rate_label = QLabel("数据率: 0 Hz")
        self.data_rate_label.setFont(QFont("Arial", 9))
        layout.addWidget(self.data_rate_label)

        return group

    def create_device_info_group(self) -> QWidget:
        """设备详细信息组"""
        group = QGroupBox("设备信息")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QVBoxLayout(group)

        # 设备信息标签
        self.device_info_labels = {}

        info_items = [
            ("设备类型", "device_type"),
            ("当前工艺", "recipe"),
            ("工艺步骤", "step"),
            ("批次号", "lot_id"),
            ("晶圆号", "wafer_id"),
        ]

        for label_text, key in info_items:
            item_layout = QHBoxLayout()

            label = QLabel(f"{label_text}:")
            label.setFont(QFont("Arial", 9))
            label.setMinimumWidth(60)
            item_layout.addWidget(label)

            value = QLabel("--")
            value.setFont(QFont("Arial", 9, QFont.Bold))
            item_layout.addWidget(value)

            layout.addLayout(item_layout)
            self.device_info_labels[key] = value

        return group

    def update_device_overview_table(self):
        """更新设备概览表格 - 显示所有设备状态"""
        try:
            # 获取所有设备数据
            all_devices = list(self.device_data.keys())

            # 清空表格
            self.device_overview_table.setRowCount(0)

            if not all_devices:
                # 更新底部统计
                self.total_devices_label.setText("总设备数: 0")
                self.online_devices_label.setText("在线: 0")
                self.offline_devices_label.setText("离线: 0")
                return

            # 🔥 设置表格行数
            self.device_overview_table.setRowCount(len(all_devices))

            online_count = 0
            offline_count = 0

            for row, device_id in enumerate(sorted(all_devices)):
                device_data = self.device_data[device_id]

                # 🔥 判断设备在线状态
                is_online = (
                    device_data.get("last_update")
                    and (time.time() - device_data["last_update"])
                    < 30  # 30秒内认为在线
                )

                if is_online:
                    online_count += 1
                else:
                    offline_count += 1

                # 🔥 填充表格数据
                # 设备ID
                device_item = QTableWidgetItem(device_id)
                device_item.setFont(QFont("Arial", 9, QFont.Bold))
                self.device_overview_table.setItem(row, 0, device_item)

                # 设备类型
                device_type_item = QTableWidgetItem(
                    device_data.get("device_type", "UNKNOWN")
                )
                self.device_overview_table.setItem(row, 1, device_type_item)

                # 连接状态
                status_text = "🟢 在线" if is_online else "⚫ 离线"
                status_item = QTableWidgetItem(status_text)
                if is_online:
                    status_item.setForeground(QColor("#28a745"))
                else:
                    status_item.setForeground(QColor("#dc3545"))
                status_item.setFont(QFont("Arial", 9, QFont.Bold))
                self.device_overview_table.setItem(row, 2, status_item)

                # 当前工艺
                recipe_item = QTableWidgetItem(device_data.get("recipe", "--"))
                self.device_overview_table.setItem(row, 3, recipe_item)

                # 工艺步骤
                step_item = QTableWidgetItem(device_data.get("step", "--"))
                self.device_overview_table.setItem(row, 4, step_item)

                # 批次号
                lot_item = QTableWidgetItem(device_data.get("lot_id", "--"))
                self.device_overview_table.setItem(row, 5, lot_item)

                # 晶圆号
                wafer_item = QTableWidgetItem(device_data.get("wafer_id", "--"))
                self.device_overview_table.setItem(row, 6, wafer_item)

                # 🔥 传感器数据 - 显示最新值
                # 温度
                temp_val = "--"
                if (
                    device_data.get("temperature")
                    and len(device_data["temperature"]) > 0
                ):
                    temp_val = f"{device_data['temperature'][-1]:.1f}"
                temp_item = QTableWidgetItem(temp_val)
                self.device_overview_table.setItem(row, 7, temp_item)

                # 压力
                pressure_val = "--"
                if device_data.get("pressure") and len(device_data["pressure"]) > 0:
                    pressure_val = f"{device_data['pressure'][-1]:.2f}"
                pressure_item = QTableWidgetItem(pressure_val)
                self.device_overview_table.setItem(row, 8, pressure_item)

                # 功率
                power_val = "--"
                if device_data.get("rf_power") and len(device_data["rf_power"]) > 0:
                    power_val = f"{device_data['rf_power'][-1]:.0f}"
                power_item = QTableWidgetItem(power_val)
                self.device_overview_table.setItem(row, 9, power_item)

                # 端点信号
                endpoint_val = "--"
                if device_data.get("endpoint") and len(device_data["endpoint"]) > 0:
                    endpoint_val = f"{device_data['endpoint'][-1]:.3f}"
                endpoint_item = QTableWidgetItem(endpoint_val)
                self.device_overview_table.setItem(row, 10, endpoint_item)

                # 最后更新时间
                update_time = "--"
                if device_data.get("last_update"):
                    update_time = datetime.fromtimestamp(
                        device_data["last_update"]
                    ).strftime("%H:%M:%S")
                update_item = QTableWidgetItem(update_time)
                self.device_overview_table.setItem(row, 11, update_item)

                # 数据点数
                data_count = len(device_data.get("timestamps", []))
                count_item = QTableWidgetItem(str(data_count))
                self.device_overview_table.setItem(row, 12, count_item)

                # 运行时长
                runtime_text = "--"
                if device_data.get("timestamps") and len(device_data["timestamps"]) > 0:
                    first_time = device_data["timestamps"][0]
                    last_time = device_data.get("last_update", first_time)
                    runtime_seconds = last_time - first_time

                    if runtime_seconds > 3600:  # 超过1小时
                        hours = int(runtime_seconds // 3600)
                        minutes = int((runtime_seconds % 3600) // 60)
                        runtime_text = f"{hours}h{minutes}m"
                    elif runtime_seconds > 60:  # 超过1分钟
                        minutes = int(runtime_seconds // 60)
                        seconds = int(runtime_seconds % 60)
                        runtime_text = f"{minutes}m{seconds}s"
                    else:
                        runtime_text = f"{runtime_seconds:.0f}s"

                runtime_item = QTableWidgetItem(runtime_text)
                self.device_overview_table.setItem(row, 13, runtime_item)

            # 🔥 更新底部统计信息
            self.total_devices_label.setText(f"总设备数: {len(all_devices)}")
            self.online_devices_label.setText(f"在线: {online_count}")
            self.offline_devices_label.setText(f"离线: {offline_count}")

            self.logger.debug(
                f"设备概览表格更新完成: {len(all_devices)}个设备, {online_count}在线, {offline_count}离线"
            )

        except Exception as e:
            self.logger.error(f"设备概览表格更新失败: {e}")

    @Slot()
    def refresh_device_table(self):
        """手动刷新设备表格"""
        try:
            self.update_device_overview_table()
            self.logger.info("设备概览表格手动刷新完成")
        except Exception as e:
            self.logger.error(f"设备表格刷新失败: {e}")

    @Slot()
    def on_device_table_double_click(self, item):
        """双击表格行选择设备"""
        try:
            if item is None:
                return

            row = item.row()
            device_id_item = self.device_overview_table.item(row, 0)  # 第0列是设备ID

            if device_id_item:
                device_id = device_id_item.text()

                # 🔥 更新右侧面板的设备选择
                self.device_combo.setCurrentText(device_id)

                # 🔥 切换到图表视图显示详细数据
                self.stacked_widget.setCurrentIndex(2)  # 切换到chart页面

                self.logger.info(f"从表格选择设备: {device_id}, 切换到图表视图")

        except Exception as e:
            self.logger.error(f"表格双击处理失败: {e}")

    def create_stats_group(self) -> QWidget:
        """数据统计组"""
        group = QGroupBox("数据统计")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QVBoxLayout(group)

        # 统计信息标签
        self.stats_labels = {}

        stats_items = [
            ("数据点数", "data_points"),
            ("平均温度", "avg_temp"),
            ("平均压力", "avg_pressure"),
            ("运行时长", "runtime"),
        ]

        for label_text, key in stats_items:
            item_layout = QHBoxLayout()

            label = QLabel(f"{label_text}:")
            label.setFont(QFont("Arial", 9))
            label.setMinimumWidth(60)
            item_layout.addWidget(label)

            value = QLabel("--")
            value.setFont(QFont("Arial", 9, QFont.Bold))
            item_layout.addWidget(value)

            layout.addLayout(item_layout)
            self.stats_labels[key] = value

        return group

    def create_actions_group(self) -> QWidget:
        """操作按钮组"""
        group = QGroupBox("操作")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QVBoxLayout(group)

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新数据")
        refresh_btn.clicked.connect(self.refresh_data)
        refresh_btn.setMinimumHeight(32)
        layout.addWidget(refresh_btn)

        # 清空数据按钮
        clear_btn = QPushButton("🗑️ 清空数据")
        clear_btn.clicked.connect(self.clear_data)
        clear_btn.setMinimumHeight(32)
        layout.addWidget(clear_btn)

        return group

    def create_table_page(self) -> QWidget:
        """创建设备概览表格页面 - 显示所有设备信息与状态"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # 🔥 顶部工具栏
        toolbar_layout = QHBoxLayout()

        # 标题
        title_label = QLabel("🏭 设备状态概览")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addStretch()

        # 刷新按钮
        refresh_table_btn = QPushButton("🔄 刷新")
        refresh_table_btn.clicked.connect(self.refresh_device_table)
        toolbar_layout.addWidget(refresh_table_btn)

        layout.addLayout(toolbar_layout)

        # 🔥 设备概览表格
        self.device_overview_table = QTableWidget()
        self.device_overview_table.setAlternatingRowColors(True)
        self.device_overview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.device_overview_table.setSelectionMode(QTableWidget.SingleSelection)

        # 🔥 设置表格列 - 设备概览信息
        columns = [
            "设备ID",
            "设备类型",
            "连接状态",
            "当前工艺",
            "工艺步骤",
            "批次号",
            "晶圆号",
            "温度(°C)",
            "压力(Torr)",
            "功率(W)",
            "端点信号",
            "最后更新",
            "数据点数",
            "运行时长",
        ]
        self.device_overview_table.setColumnCount(len(columns))
        self.device_overview_table.setHorizontalHeaderLabels(columns)

        # 🔥 设置表格样式
        header = self.device_overview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # 🔥 双击选择设备
        self.device_overview_table.itemDoubleClicked.connect(
            self.on_device_table_double_click
        )

        layout.addWidget(self.device_overview_table)

        # 🔥 底部状态栏
        status_layout = QHBoxLayout()

        self.total_devices_label = QLabel("总设备数: 0")
        self.total_devices_label.setFont(QFont("Arial", 10))
        status_layout.addWidget(self.total_devices_label)

        status_layout.addStretch()

        self.online_devices_label = QLabel("在线: 0")
        self.online_devices_label.setFont(QFont("Arial", 10))
        status_layout.addWidget(self.online_devices_label)

        self.offline_devices_label = QLabel("离线: 0")
        self.offline_devices_label.setFont(QFont("Arial", 10))
        status_layout.addWidget(self.offline_devices_label)

        layout.addLayout(status_layout)

        return widget

    def create_dashboard_page(self) -> QWidget:
        """创建仪表盘页面 - 暂时置空"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 🔥 暂时显示占位信息
        placeholder_label = QLabel("仪表盘视图\n\n功能开发中...")
        placeholder_label.setAlignment(Qt.AlignCenter)
        placeholder_label.setFont(QFont("Arial", 16))
        layout.addWidget(placeholder_label)

        return widget

    def create_chart_page(self) -> QWidget:
        """创建曲线监控页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # 配置PyQtGraph样式
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")

        # 图表网格
        charts_layout = QGridLayout()
        charts_layout.setSpacing(10)

        # 创建趋势图表
        self.charts = {}

        # 温度趋势
        self.charts["temperature"] = self.create_trend_chart(
            "温度趋势", "温度 (°C)", "#FF5722"
        )
        charts_layout.addWidget(self.charts["temperature"], 0, 0)

        # 压力趋势
        self.charts["pressure"] = self.create_trend_chart(
            "压力趋势", "压力 (Torr)", "#2196F3"
        )
        charts_layout.addWidget(self.charts["pressure"], 0, 1)

        # 功率趋势
        self.charts["rf_power"] = self.create_trend_chart(
            "功率趋势", "功率 (W)", "#FF9800"
        )
        charts_layout.addWidget(self.charts["rf_power"], 1, 0)

        # 端点信号趋势
        self.charts["endpoint"] = self.create_trend_chart(
            "端点信号趋势", "端点信号", "#4CAF50"
        )
        charts_layout.addWidget(self.charts["endpoint"], 1, 1)

        layout.addLayout(charts_layout)
        return widget

    def create_trend_chart(self, title, ylabel, color):
        """创建趋势图表"""
        group = QGroupBox(title)
        group.setFont(QFont("Arial", 10, QFont.Bold))

        layout = QVBoxLayout(group)

        # 创建图表
        plot_widget = pg.PlotWidget()
        plot_widget.setLabel("left", ylabel)
        plot_widget.setLabel("bottom", "时间 (秒)")
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.setMouseEnabled(x=True, y=False)

        # 创建曲线
        curve = plot_widget.plot([], [], pen=pg.mkPen(color, width=2), name=title)

        layout.addWidget(plot_widget)

        # 存储引用
        group.plot_widget = plot_widget
        group.curve = curve

        return group

    # 🔥 公共接口方法 - 供主窗口调用

    def switch_to_view(self, view_name: str):
        """切换视图 - 由主窗口控制调用"""
        view_mapping = {"table": 0, "dashboard": 1, "chart": 2}

        if view_name in view_mapping:
            self.stacked_widget.setCurrentIndex(view_mapping[view_name])
            self.logger.info(f"切换到{view_name}视图")

    def get_current_device(self) -> str:
        """获取当前选择的设备ID"""
        return self.current_device

    def set_current_device(self, device_id: str):
        """设置当前设备 - 由主窗口调用"""
        if device_id != self.current_device:
            self.current_device = device_id
            if device_id in [
                self.device_combo.itemText(i) for i in range(self.device_combo.count())
            ]:
                self.device_combo.setCurrentText(device_id)
            self.update_device_info_bar()

    # === 信号连接和事件处理 ===

    def connect_signals(self):
        """连接信号-槽"""
        try:
            # 连接控制器信号
            if self.controller:
                self.controller.device_data_updated.connect(self.on_device_data_updated)
                self.controller.device_list_updated.connect(self.on_device_list_updated)
                self.controller.statistics_updated.connect(self.on_statistics_updated)

            self.logger.info("信号连接完成")
        except Exception as e:
            self.logger.error(f"信号连接失败: {e}")

    def setup_timers(self):
        """设置定时器"""
        # UI更新定时器
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.update_ui_displays)
        self.ui_update_timer.start(100)  # 10Hz更新

        # 设备列表更新定时器
        self.device_update_timer = QTimer()
        self.device_update_timer.timeout.connect(self.update_device_list)
        self.device_update_timer.start(2000)  # 2秒更新

    @Slot(str)
    def on_device_changed(self, device_id: str):
        """设备选择变更处理"""
        if device_id and device_id != self.current_device:
            self.current_device = device_id

            # 通知控制器
            if self.controller:
                self.controller.set_current_device(device_id)

            # 更新设备信息条
            self.update_device_info_bar()

            # 发出信号
            self.device_selected.emit(device_id)
            self.logger.info(f"选择设备: {device_id}")

    @Slot(str, dict)
    def on_device_data_updated(self, device_id: str, device_data: dict):
        """处理设备数据更新"""
        try:
            # 🔥 更新本地数据缓存
            if device_id not in self.device_data:
                self.device_data[device_id] = {
                    "temperature": deque(maxlen=300),
                    "pressure": deque(maxlen=300),
                    "rf_power": deque(maxlen=300),
                    "endpoint": deque(maxlen=300),
                    "humidity": deque(maxlen=300),
                    "vibration": deque(maxlen=300),
                    "focus_error": deque(maxlen=300),
                    "timestamps": deque(maxlen=300),
                    "last_update": None,
                    "device_type": "UNKNOWN",
                    "recipe": "",
                    "step": "",
                    "lot_id": "",
                    "wafer_id": "",
                }

            # 更新设备数据
            for key, value in device_data.items():
                if key in self.device_data[device_id]:
                    if isinstance(self.device_data[device_id][key], deque):
                        if isinstance(value, (list, deque)):
                            self.device_data[device_id][key].extend(value)
                        else:
                            self.device_data[device_id][key].append(value)
                    else:
                        self.device_data[device_id][key] = value

            # 如果是当前选中设备，更新详细显示
            if device_id == self.current_device:
                self.update_ui_with_device_data(device_data)

        except Exception as e:
            self.logger.error(f"设备数据更新处理失败: {e}")

    @Slot(list)
    def on_device_list_updated(self, active_devices):
        """处理设备列表更新"""
        try:
            current_text = self.device_combo.currentText()
            self.device_combo.clear()

            if active_devices:
                self.device_combo.addItems(sorted(active_devices))

                # 恢复之前的选择
                if current_text in active_devices:
                    self.device_combo.setCurrentText(current_text)

            # 更新设备数量显示
            self.device_count_label.setText(f"设备数: {len(active_devices)}")

        except Exception as e:
            self.logger.error(f"设备列表更新失败: {e}")

    @Slot(str, dict)
    def on_statistics_updated(self, device_id: str, stats: dict):
        """处理统计信息更新"""
        try:
            if device_id == self.current_device:
                self.update_statistics_display(stats)
        except Exception as e:
            self.logger.error(f"统计信息更新失败: {e}")

    # === UI更新方法 ===

    def update_device_list(self):
        """更新设备列表"""
        try:
            if self.controller:
                active_devices = self.controller.get_active_devices()
                self.on_device_list_updated(active_devices)
        except Exception as e:
            self.logger.error(f"设备列表更新失败: {e}")

    def update_ui_displays(self):
        """定时更新UI显示"""
        try:
            # 🔥 始终更新设备概览表格（如果当前在表格页面）
            current_index = self.stacked_widget.currentIndex()
            if current_index == 0:  # 设备概览表格页面
                self.update_device_overview_table()

            # 如果有选中设备，更新其详细信息
            if self.current_device:
                if self.controller:
                    device_data = self.controller.get_device_data(self.current_device)
                    if device_data:
                        # 只更新右侧面板和当前页面（非表格页面）
                        self.update_right_panel_status(device_data)

                        if current_index == 2:  # 图表页面
                            self.update_chart_display(device_data)

        except Exception as e:
            self.logger.error(f"UI更新失败: {e}")

    def update_device_info_bar(self):
        """更新设备信息条"""
        try:
            if not self.current_device:
                self.current_device_label.setText("未选择设备")
                self.device_type_label.setText("--")
                self.current_recipe_label.setText("--")
                self.connection_status_label.setText("⚫ 离线")
                return

            self.current_device_label.setText(self.current_device)

            # 从数据缓存获取设备信息
            device_data = self.device_data[self.current_device]
            self.device_type_label.setText(device_data["device_type"])

            recipe = device_data["recipe"]
            step = device_data["step"]
            if step:
                recipe_text = f"{recipe} (步骤: {step})"
            else:
                recipe_text = recipe or "--"
            self.current_recipe_label.setText(recipe_text)

            # 连接状态
            if (
                device_data["last_update"]
                and (time.time() - device_data["last_update"]) < 10
            ):
                self.connection_status_label.setText("🟢 在线")
            else:
                self.connection_status_label.setText("⚫ 离线")

        except Exception as e:
            self.logger.error(f"设备信息条更新失败: {e}")

    def update_ui_with_device_data(self, device_data: dict):
        """使用设备数据更新UI"""
        try:
            # 更新右侧状态面板
            self.update_right_panel_status(device_data)

            # 根据当前页面更新对应显示
            current_index = self.stacked_widget.currentIndex()
            if current_index == 0:  # 🔥 设备概览表格页面
                self.update_device_overview_table()
            elif current_index == 2:  # 图表页面
                self.update_chart_display(device_data)
            # dashboard_page (索引1) 暂时不做任何更新

        except Exception as e:
            self.logger.error(f"UI数据更新失败: {e}")

    def update_right_panel_status(self, device_data: dict):
        """更新右侧面板状态"""
        try:
            # 连接状态指示器
            if (
                device_data.get("last_update")
                and (time.time() - device_data["last_update"]) < 10
            ):
                self.status_indicator.setText("🟢")
                self.status_text.setText("在线")
            else:
                self.status_indicator.setText("⚫")
                self.status_text.setText("离线")

            # 最后更新时间
            if device_data.get("last_update"):
                update_time = datetime.fromtimestamp(
                    device_data["last_update"]
                ).strftime("%H:%M:%S")
                self.last_update_label.setText(f"最后更新: {update_time}")

            # 设备信息
            self.device_info_labels["device_type"].setText(
                device_data.get("device_type", "--")
            )
            self.device_info_labels["recipe"].setText(device_data.get("recipe", "--"))
            self.device_info_labels["step"].setText(device_data.get("step", "--"))
            self.device_info_labels["lot_id"].setText(device_data.get("lot_id", "--"))
            self.device_info_labels["wafer_id"].setText(
                device_data.get("wafer_id", "--")
            )

            # 统计信息
            if device_data.get("timestamps"):
                data_count = len(device_data["timestamps"])
                self.stats_labels["data_points"].setText(str(data_count))

                if (
                    device_data.get("temperature")
                    and len(device_data["temperature"]) > 0
                ):
                    temps = list(device_data["temperature"])
                    avg_temp = sum(temps) / len(temps)
                    self.stats_labels["avg_temp"].setText(f"{avg_temp:.1f}°C")

                if device_data.get("pressure") and len(device_data["pressure"]) > 0:
                    pressures = list(device_data["pressure"])
                    avg_pressure = sum(pressures) / len(pressures)
                    self.stats_labels["avg_pressure"].setText(f"{avg_pressure:.2f}Torr")

                # 运行时长
                if device_data.get("last_update"):
                    first_timestamp = (
                        device_data["timestamps"][0]
                        if device_data["timestamps"]
                        else device_data["last_update"]
                    )
                    runtime = device_data["last_update"] - first_timestamp
                    self.stats_labels["runtime"].setText(f"{runtime:.0f}s")

        except Exception as e:
            self.logger.error(f"右侧面板状态更新失败: {e}")

    def update_chart_display(self, device_data: dict):
        """更新图表显示"""
        try:
            timestamps = list(device_data.get("timestamps", []))
            if len(timestamps) < 2:
                return

            base_time = timestamps[0]
            relative_times = [(t - base_time) for t in timestamps]

            for key, chart in self.charts.items():
                if device_data.get(key) and len(device_data[key]) > 0:
                    values = list(device_data[key])
                    if len(values) == len(relative_times):
                        chart.curve.setData(relative_times, values)

        except Exception as e:
            self.logger.error(f"图表更新失败: {e}")

    def update_statistics_display(self, stats: dict):
        """更新统计显示"""
        try:
            # 更新统计标签
            for key, value in stats.items():
                if key in self.stats_labels:
                    self.stats_labels[key].setText(str(value))
        except Exception as e:
            self.logger.error(f"统计显示更新失败: {e}")

    # === 操作方法 ===

    @Slot()
    def refresh_data(self):
        """刷新数据"""
        try:
            if self.controller and self.current_device:
                self.controller.refresh_device_data(self.current_device)
            self.logger.info("数据刷新请求已发送")
        except Exception as e:
            self.logger.error(f"数据刷新失败: {e}")

    @Slot()
    def clear_data(self):
        """清空当前设备数据"""
        try:
            if self.current_device and self.current_device in self.device_data:
                # 清空数据缓存
                for key in self.device_data[self.current_device]:
                    if isinstance(self.device_data[self.current_device][key], deque):
                        self.device_data[self.current_device][key].clear()

                # 通知控制器
                if self.controller:
                    self.controller.clear_device_data(self.current_device)

                self.logger.info(f"设备 {self.current_device} 数据已清空")
        except Exception as e:
            self.logger.error(f"数据清空失败: {e}")
