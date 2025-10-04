import logging
import random
import time
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QStackedWidget,
    QFrame,
)
from PySide6.QtCore import QTimer, Signal, Slot
from collections import defaultdict, deque

from core.data_bus import get_data_bus, DataChannel, DataMessage
from core.device_manager import get_device_manager
from .DeviceControlPanel import DeviceControlPanel
from .DeviceOverviewTable import DeviceOverviewTable
from .DeviceChartsWidget import DeviceChartsWidget


class DataVisualizationWidget(QWidget):
    device_selected = Signal(str)
    visualization_mode_changed = Signal(str)
    connection_status_changed = Signal(bool, str)
    statistics_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DataVisualizationWidget")
        self.device_manager = get_device_manager()
        self.data_bus = get_data_bus()
        # 历史数据缓存 - 每设备独立队列
        self.device_history = defaultdict(lambda: deque(maxlen=1000))
        # 统计信息缓存
        self.device_stats = defaultdict(dict)
        self.current_device = None
        self.device_sensors_count = {}
        self.device_data_rate = {}

        self.setup_ui()
        self.setup_databus()
        self.setup_timer()
        self.connect_device_manager()

    def connect_device_manager(self):
        """连接设备管理器信号"""
        self.device_manager.device_list_updated.connect(self.on_device_list_updated)
        self.device_manager.device_discovered.connect(self.on_device_discovered)

    def _build_overview_map(self, device_ids: list | None = None) -> dict:
        """返回 {device_id: device_info_for_overview}"""
        result = {}
        # 选取来源：若未指定，则使用 DeviceManager 的全量设备列表
        device_ids = device_ids or self.device_manager.get_all_devices()

        for did in device_ids:
            info = self.device_manager.get_device_info(did) or {}
            last_update = info.get("last_update", 0) or 0
            first_seen = info.get("first_seen", 0) or 0

            # 传感器数量（演示随机一次并缓存）
            if did not in self.device_sensors_count:
                self.device_sensors_count[did] = random.randint(3, 8)
            sensor_count = self.device_sensors_count[did]

            # 数据频率：基于历史数据粗算（点数/时长）
            history = list(getattr(self, "device_history", {}).get(did, []))
            if len(history) > 1:
                ts = [p.get("timestamp") for p in history if p.get("timestamp")]
                ts = [t for t in ts if isinstance(t, (int, float))]
                if len(ts) > 1:
                    duration = max(ts) - min(ts)
                    rate = (len(ts) / duration) if duration > 0 else 0.0
                    self.device_data_rate[did] = f"{rate:.2f}/s"
            data_rate = self.device_data_rate.get(did, "--")

            # 展示字段：最后在线时间/运行时长
            if last_update:
                last_online_str = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(last_update)
                )
            else:
                last_online_str = "--"

            if first_seen and last_update and last_update > first_seen:
                runtime_sec = int(last_update - first_seen)
                if runtime_sec > 3600:
                    runtime_str = f"{runtime_sec//3600}h{(runtime_sec%3600)//60}m"
                elif runtime_sec > 60:
                    runtime_str = f"{runtime_sec//60}m{runtime_sec%60}s"
                else:
                    runtime_str = f"{runtime_sec}s"
            else:
                runtime_str = "--"

            # 统一的行结构（DeviceOverviewTable 只消费这一致格式）
            result[did] = {
                "device_id": did,
                "device_type": info.get("device_type", "UNKNOWN"),
                "vendor": info.get("vendor", "UNKNOWN"),
                "online": info.get("online", False),
                "sensor_count": sensor_count,
                "data_rate": data_rate,
                "last_online": last_online_str,
                "runtime": runtime_str,
            }
        return result

    def _build_panel_data(self, device_id: str) -> dict:
        """构建右侧控制面板需要的数据"""
        info = self.device_manager.get_device_info(device_id) or {}
        stats = self.device_stats.get(device_id, {}) or {}
        last_update = stats.get("last_update") or info.get("last_update", 0) or 0
        first_seen = info.get("first_seen", 0) or 0
        online = info.get("online", False)

        # 最新样本（用于显示工艺信息）
        latest = {}
        hist = self.device_history.get(device_id)
        if hist and len(hist) > 0:
            latest = hist[-1]

        # 运行时长（若未提供，按 first_seen/last_update 计算）
        if first_seen and last_update and last_update > first_seen:
            runtime_sec = int(last_update - first_seen)
            if runtime_sec > 3600:
                runtime_str = f"{runtime_sec//3600}h{(runtime_sec%3600)//60}m"
            elif runtime_sec > 60:
                runtime_str = f"{runtime_sec//60}m{runtime_sec%60}s"
            else:
                runtime_str = f"{runtime_sec}s"
        else:
            runtime_str = "--"

        # 数据率
        data_rate = self.device_data_rate.get(device_id, "--")

        panel = {
            "device_id": device_id,
            "device_type": info.get("device_type", "UNKNOWN"),
            "online": online,
            "last_update": last_update,
            "first_seen": first_seen,
            "runtime": runtime_str,
            "data_points": stats.get("data_points", 0),
            "avg_temp": stats.get("avg_temp"),
            "avg_pressure": stats.get("avg_pressure"),
            "data_rate": data_rate,
            # 最新样本中的工艺信息（如无则 "--"）
            "recipe": latest.get("recipe", "--"),
            "step": latest.get("step", "--"),
            "lot_number": latest.get("lot_number", "--"),
            "wafer_id": latest.get("wafer_id", "--"),
            # 也可按需透传更多字段
        }
        return panel

    @Slot(str, dict)
    def on_device_discovered(self, device_id: str, device_info: dict):
        """处理新设备发现"""
        self.logger.info(f"发现新设备: {device_id}")
        # 自动添加到控制面板
        all_devices = self.device_manager.get_all_devices()
        online_devices = [
            did
            for did in all_devices
            if self.device_manager.get_device_info(did).get("online", False)
        ]
        self.control_panel.update_device_list(online_devices)

    @Slot(list)
    def on_device_list_updated(self, device_ids):
        """来自 DeviceManager 的设备列表更新 -> 统一映射后喂给表格"""
        overview_map = self._build_overview_map(device_ids)
        self.table_widget.update_table_data(overview_map)

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
        self.stacked_widget.addWidget(self.table_widget)  # 0: 表格
        self.stacked_widget.addWidget(self.charts_widget)  # 1: 图表

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

    def setup_databus(self):
        """数据总线订阅"""
        self.data_bus.subscribe(DataChannel.TELEMETRY_DATA, self.on_telemetry_data)
        self.data_bus.subscribe(DataChannel.ALERTS, self.on_alerts)

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
        data_point = {
            "timestamp": message.timestamp,
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
            # "gas": {k[4:]: v for k, v in sample.items() if k.startswith("gas_")},
        }
        # 🔥 处理气体数据
        for key, value in sample.items():
            if key.startswith("gas_"):
                data_point[key] = value

        self.device_history[device_id].append(data_point)
        self.update_device_statistics(device_id)
        if self.current_device == device_id:
            self.control_panel.update_device_status(
                device_id, self._build_panel_data(device_id)
            )

    def update_device_statistics(self, device_id: str):
        """更新设备统计信息"""
        history = list(self.device_history[device_id])
        if not history:
            return

        # 计算统计值
        temps = [p["temperature"] for p in history if p.get("temperature") is not None]
        pressures = [p["pressure"] for p in history if p.get("pressure") is not None]

        stats = {
            "data_points": len(history),
            "avg_temp": sum(temps) / len(temps) if temps else 0,
            "avg_pressure": sum(pressures) / len(pressures) if pressures else 0,
            "last_update": history[-1]["timestamp"],
        }

        self.device_stats[device_id] = stats
        self.statistics_updated.emit(stats)

    def sync_data(self):
        """统一数据同步"""
        index = self.stacked_widget.currentIndex()
        if index == 0:
            self.sync_table_data()
        elif index == 1 and self.current_device:
            self.sync_chart_data()
        elif index == 2 and self.current_device:
            self.sync_chart_data()

    def sync_table_data(self):
        """在定时/视图切换时刷新表格 -> 同样走统一映射"""
        # 使用 DeviceManager 全量设备，保证无历史数据的设备也能展示
        overview_map = self._build_overview_map()
        self.table_widget.update_table_data(overview_map)

    def sync_chart_data(self):
        """同步图表数据 - 优化版"""
        if not self.current_device:
            return

        history = list(self.device_history[self.current_device])
        if history:
            self.charts_widget.update_from_history_data(self.current_device, history)

    # 简化用户交互
    @Slot(str)
    def set_current_device(self, device_id: str):
        """设置当前设备 - 统一入口"""
        if device_id == self.current_device:
            return

        self.current_device = device_id
        self.logger.info(f"切换到设备: {device_id}")
        self.device_selected.emit(device_id)
        current_view = self.stacked_widget.currentIndex()
        # 立即同步当前设备数据
        if current_view == 1:  # 仪表盘
            self.charts_widget.set_current_device(device_id)
            self.sync_chart_data()
        elif current_view == 2:  # 图表
            self.charts_widget.set_current_device(device_id)
            self.sync_chart_data()
        self.control_panel.update_device_status(
            device_id, self._build_panel_data(device_id)
        )

        self.device_selected.emit(device_id)

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
            self.device_history[self.current_device].clear()
            self.device_stats[self.current_device] = {}

        # 清空UI
        self.charts_widget.clear_charts()
        # self.dashboard_widget.clear_data()

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
