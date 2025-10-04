import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from collections import defaultdict, deque

from core.data_bus import data_bus, DataChannel, DataMessage
from core.device_manager import device_manager
from .DeviceControlPanel import DeviceControlPanel
from .DeviceOverviewTable import DeviceOverviewTable
from .DeviceChartsWidget import DeviceChartsWidget
from .DataDashboardWidget import DashboardWidget


class DataVisualizationWidget(QWidget):
    device_selected = Signal(str)
    visualization_mode_changed = Signal(str)
    connection_status_changed = Signal(bool, str)
    statistics_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DataVisualizationWidget")
        device_manager.device_list_updated.connect(self.on_device_list_updated)
        # 🔥 简化数据存储 - 只保留必要字段
        self.device_data = defaultdict(
            lambda: {
                "latest": {},  # 最新数据点
                "history": deque(maxlen=300),  # 历史数据
                "info": {},  # 设备信息
                "last_update": 0,
            }
        )

        self.current_device = None

        self.setup_ui()
        self.setup_databus()
        self.setup_timer()

    def setup_ui(self):
        """简化UI设置"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 左侧：可视化区域
        self.stacked_widget = QStackedWidget()

        # 添加三个视图组件
        self.table_widget = DeviceOverviewTable()
        self.charts_widget = DeviceChartsWidget()
        self.dashboard_widget = DashboardWidget()
        self.dashboard_widget.device_selected.connect(self.set_current_device)
        self.stacked_widget.addWidget(self.table_widget)  # 0: 表格
        self.stacked_widget.addWidget(self.dashboard_widget)  # 1: 仪表盘
        self.stacked_widget.addWidget(self.charts_widget)  # 2: 图表

        layout.addWidget(self.stacked_widget, 3)

        # 右侧：控制面板
        self.control_panel = DeviceControlPanel()
        layout.addWidget(self.control_panel, 1)

        # 连接信号
        self.connect_signals()

    def create_dashboard_placeholder(self):
        """创建仪表盘占位页面"""
        widget = QFrame()
        widget.setObjectName("dashboardPlaceholder")
        return widget

    @Slot(list)
    def on_device_list_updated(self, device_ids):
        logging.debug(f"DataVisualizationWidget: 设备列表更新 - {device_ids}")
        # 获取所有设备详细信息
        all_devices = []
        for did in device_ids:
            info = device_manager.get_device_info(did)
            if info is not None:
                all_devices.append(info)

        # 1. 更新DeviceOverviewTable（显示所有设备）
        self.table_widget.update_devices_data(all_devices)

        # 2. 只筛选在线设备，更新DeviceControlPanel
        online_devices = [d["device_id"] for d in all_devices if d.get("online", False)]
        self.control_panel.update_device_list(online_devices)

    def setup_databus(self):
        """数据总线订阅"""
        data_bus.subscribe(DataChannel.TELEMETRY_DATA, self.on_telemetry_data)
        data_bus.subscribe(DataChannel.ALERTS, self.on_alerts)

    def setup_timer(self):
        """单一定时器同步"""
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_data)
        self.sync_timer.start(1000)  # 1秒同步

    def connect_signals(self):
        """连接组件信号"""
        # 控制面板信号
        self.control_panel.device_selected.connect(self.set_current_device)
        self.control_panel.refresh_requested.connect(self.refresh_data)
        self.control_panel.clear_requested.connect(self.clear_data)

        # 表格信号
        self.table_widget.device_selected.connect(self.on_table_device_selected)

    @Slot()
    def on_alerts(self, message: DataMessage):
        """处理告警消息"""
        device_id = message.device_id
        if device_id:
            # 可以在UI中显示告警状态
            alert_data = message.data
            self.logger.info(f"设备告警: {device_id} - {alert_data}")

    #
    @Slot()
    def on_telemetry_data(self, message: DataMessage):
        """处理遥测数据"""
        device_id = message.device_id
        if not device_id:
            return
        raw_data = message.data
        sample = raw_data.get("sample_record", {})
        normalized = {
            "device_id": device_id,
            "device_type": raw_data.get("device_type", "UNKNOWN"),
            "recipe": sample.get("recipe", "--"),
            "step": sample.get("step", "--"),
            "lot_number": sample.get("lot_number", "--"),
            "wafer_id": sample.get("wafer_id", "--"),
            "temperature": sample.get("temperature"),
            "pressure": sample.get("pressure"),
            "rf_power": sample.get("rf_power"),
            "endpoint": sample.get("endpoint"),
            "channel": sample.get("channel"),
            "gas": {k[4:]: v for k, v in sample.items() if k.startswith("gas_")},
            "last_update": message.timestamp,
        }
        # 直接更新设备数据
        device = self.device_data[device_id]
        device["latest"] = normalized
        device["last_update"] = message.timestamp
        device["history"].append({"timestamp": message.timestamp, **normalized})

    # 简化同步逻辑
    def sync_data(self):
        """统一数据同步 - 替代多个定时器"""
        # 更新表格数据
        if self.stacked_widget.currentIndex() == 0:
            self.sync_table_data()
        elif self.stacked_widget.currentIndex() == 1 and self.current_device:
            self.sync_dashboard_data()
        elif self.stacked_widget.currentIndex() == 2 and self.current_device:
            self.sync_chart_data()

    def sync_table_data(self):
        """同步表格数据"""
        devices_data = []
        for device_id in self.active_devices:
            device = self.device_data[device_id]
            latest = device.get("latest", {})
            info = device.get("info", {})

            devices_data.append(
                {
                    "device_id": device_id,
                    "device_type": info.get("device_type", "UNKNOWN"),
                    "last_update": device.get("last_update", 0),
                    **latest,  # 展开最新数据
                }
            )

        self.table_widget.update_devices_data(devices_data)

    def sync_chart_data(self):
        """同步图表数据"""
        if not self.current_device:
            return

        device = self.device_data[self.current_device]
        history = list(device["history"])
        if not history:
            # 如果没有数据，清空图表
            self.charts_widget.clear_charts()
            return

        try:
            self.charts_widget.update_from_history_data(self.current_device, history)

        except Exception as e:
            self.logger.error(f"图表数据同步失败: {e}")

    def sync_dashboard_data(self):
        """同步仪表盘数据"""
        if not self.current_device:
            return

        # 确保仪表盘显示当前设备
        dashboard = self.dashboard_widget
        if dashboard.get_current_device() != self.current_device:
            dashboard.set_device(self.current_device)

        # 更新设备数据
        device = self.device_data[self.current_device]
        history = list(device["history"])

        if history:
            dashboard.update_device_data(
                {"device_id": self.current_device, "data_points": history}
            )

    # 简化用户交互
    @Slot(str)
    def set_current_device(self, device_id: str):
        """设置当前设备 - 统一入口"""
        if device_id == self.current_device:
            return

        self.current_device = device_id
        self.device_selected.emit(device_id)

        # 立即同步当前设备数据
        if self.stacked_widget.currentIndex() == 2:
            self.sync_chart_data()

    @Slot(str)
    def on_table_device_selected(self, device_id: str):
        """表格设备选择 - 自动切换到图表"""
        self.set_current_device(device_id)
        self.switch_to_view("chart")

    def switch_to_view(self, view_name: str):
        """切换视图"""
        view_mapping = {"table": 0, "dashboard": 1, "chart": 2}

        if view_name in view_mapping:
            self.stacked_widget.setCurrentIndex(view_mapping[view_name])
            self.visualization_mode_changed.emit(view_name)

    # 简化操作方法
    @Slot()
    def refresh_data(self):
        """刷新数据"""
        self.sync_data()

    @Slot()
    def clear_data(self):
        """清空数据"""
        if self.current_device:
            device = self.device_data[self.current_device]
            device["history"].clear()
            device["latest"] = {}

            # 清空图表
            if self.stacked_widget.currentIndex() == 2:
                self.charts_widget.clear_charts()

    def get_current_status(self) -> dict:
        """获取当前状态"""
        return {
            # "active_devices": len(self.active_devices),
            "current_device": self.current_device,
            "current_view": self.stacked_widget.currentIndex(),
            # "devices_list": sorted(list(self.active_devices)),
        }

    def cleanup(self):
        """组件清理"""
        if hasattr(self, "sync_timer"):
            self.sync_timer.stop()
