import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from collections import defaultdict, deque
import time
from datetime import datetime

from core.enhanced_data_bus import enhanced_data_bus
from core.data_bus import DataChannel, DataMessage
from .DeviceControlPanel import DeviceControlPanel
from .DeviceOverviewTable import DeviceOverviewTable
from .DeviceChartsWidget import DeviceChartsWidget


class DataVisualizationWidget(QWidget):
    device_selected = Signal(str)  # 设备选择信号
    visualization_mode_changed = Signal(str)  # 可视化模式变更信号
    device_count_changed = Signal(int)  # 设备数量变化
    connection_status_changed = Signal(bool, str)  # 连接状态变化
    statistics_updated = Signal(dict)  # 统计信息更新

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

        # 核心状态
        self.active_devices = set()
        self.current_device = None

        # 子组件引用
        self.control_panel = None
        self.table_widget = None
        self.charts_widget = None
        self.stacked_widget = None

        self.setup_ui()
        self.setup_databus_subscriptions()
        self.connect_signals()
        self.setup_timers()

        self.logger.info("数据可视化组件初始化完成")

    def setup_ui(self):
        """设置用户界面 - 左右分栏布局"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # 🔥 左侧：数据可视化区域 (75%)
        self.visualization_area = self.create_visualization_area()
        main_layout.addWidget(self.visualization_area, 3)

        # 🔥 右侧：设备控制面板 (25%) - 使用独立组件
        self.control_panel = DeviceControlPanel()
        main_layout.addWidget(self.control_panel, 1)

    def create_visualization_area(self) -> QWidget:
        """创建左侧数据可视化区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)
        # 可视化内容区 - 使用StackedWidget支持多种视图
        self.stacked_widget = QStackedWidget()

        # 🔥 页面0：表格视图 - 使用独立组件
        self.table_widget = DeviceOverviewTable()
        self.stacked_widget.addWidget(self.table_widget)

        # 页面1：仪表盘视图 - 占位页面
        self.dashboard_widget = self.create_dashboard_page()
        self.stacked_widget.addWidget(self.dashboard_widget)

        # 🔥 页面2：趋势图视图 - 使用独立组件
        self.charts_widget = DeviceChartsWidget()
        self.stacked_widget.addWidget(self.charts_widget)

        layout.addWidget(self.stacked_widget)

        # 默认显示表格
        self.stacked_widget.setCurrentIndex(0)

        return widget

    def create_dashboard_page(self) -> QWidget:
        """创建仪表盘占位页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        placeholder_frame = QFrame()
        placeholder_frame.setObjectName("dashboardPlaceholder")
        placeholder_frame.setFrameStyle(QFrame.StyledPanel)

        placeholder_layout = QVBoxLayout(placeholder_frame)
        placeholder_layout.setAlignment(Qt.AlignCenter)

        # 标题
        title_label = QLabel("仪表盘视图")
        title_label.setObjectName("dashboardTitle")
        title_label.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(title_label)

        # 描述
        desc_label = QLabel(
            "实时监控仪表盘正在开发中\n\n请使用表格视图或趋势图表查看数据"
        )
        desc_label.setObjectName("dashboardDesc")
        desc_label.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(desc_label)

        layout.addWidget(placeholder_frame)
        return widget

    def setup_databus_subscriptions(self):
        """设置增强数据总线订阅 - 完整版本"""
        try:
            # 订阅遥测数据
            enhanced_data_bus.subscribe(
                DataChannel.TELEMETRY_DATA, self.on_enhanced_telemetry_data
            )

            # 订阅设备事件
            enhanced_data_bus.subscribe(
                DataChannel.DEVICE_EVENTS, self.on_enhanced_device_events
            )

            # 订阅告警信息
            enhanced_data_bus.subscribe(DataChannel.ALERTS, self.on_enhanced_alerts)

            self.logger.info("Enhanced DataBus订阅设置完成")

        except Exception as e:
            self.logger.error(f"Enhanced DataBus订阅失败: {e}")

    @Slot()
    def on_enhanced_telemetry_data(self, message: DataMessage):
        """处理增强数据总线遥测数据"""
        try:
            device_id = message.device_id
            if not device_id:
                return

            data = message.data

            # 🔥 更新本地缓存
            self.update_local_cache(device_id, data)

            # 🔥 更新活跃设备集合
            if device_id not in self.active_devices:
                self.active_devices.add(device_id)
                self.device_count_changed.emit(len(self.active_devices))
                self.connection_status_changed.emit(
                    True, f"活跃设备: {len(self.active_devices)}个"
                )

            # 🔥 如果是当前设备，立即同步
            if device_id == self.current_device:
                self.sync_current_device_data()

            # 🔥 定期发射统计信息
            self.emit_statistics_update()

        except Exception as e:
            self.logger.error(f"Enhanced遥测数据处理失败: {e}")

    @Slot()
    def on_enhanced_device_events(self, message: DataMessage):
        """处理增强数据总线设备事件"""
        try:
            device_id = message.device_id
            event_data = message.data

            if isinstance(event_data, dict) and device_id:
                event_type = event_data.get("event_type", "unknown")

                if event_type == "device_discovered":
                    # 新设备发现
                    if device_id not in self.active_devices:
                        self.active_devices.add(device_id)

                        # 初始化设备数据
                        self.device_data[device_id].update(
                            {
                                "device_type": event_data.get("device_type", "UNKNOWN"),
                                "vendor": event_data.get("vendor", "UNKNOWN"),
                            }
                        )

                        # 通知主窗口
                        self.device_count_changed.emit(len(self.active_devices))

                elif event_type == "connection_change":
                    # 连接状态变化
                    connected = event_data.get("connected", False)
                    if not connected and device_id in self.active_devices:
                        self.active_devices.remove(device_id)
                        self.device_count_changed.emit(len(self.active_devices))

        except Exception as e:
            self.logger.error(f"Enhanced设备事件处理失败: {e}")

    @Slot()
    def on_enhanced_alerts(self, message: DataMessage):
        """处理增强数据总线告警"""
        try:
            device_id = message.device_id or "SYSTEM"
            alert_data = message.data

            # 通知控制面板显示告警
            if self.control_panel:
                self.control_panel.show_alert(device_id, alert_data)

            # 通知主窗口连接状态变化（告警状态）
            self.connection_status_changed.emit(True, f"告警: {device_id}")

        except Exception as e:
            self.logger.error(f"Enhanced告警处理失败: {e}")

    def emit_statistics_update(self):
        """发射统计信息更新"""
        try:
            # 计算总体统计
            total_records = sum(
                len(device_data.get("timestamps", []))
                for device_data in self.device_data.values()
            )

            # 获取Redis缓冲统计
            enhanced_stats = enhanced_data_bus.get_buffer_stats()

            combined_stats = {
                "active_devices": len(self.active_devices),
                "total_records": total_records,
                "current_device": self.current_device,
                "redis_stats": enhanced_stats.get("redis_buffer", {}),
                "buffer_counts": enhanced_stats.get("buffer_counts", {}),
            }

            self.statistics_updated.emit(combined_stats)

        except Exception as e:
            self.logger.error(f"统计信息发射失败: {e}")

    def update_local_cache(self, device_id: str, new_data: dict):
        """更新本地数据缓存 - 增强版本"""
        try:
            current_time = time.time()
            device = self.device_data[device_id]

            # 更新基本信息
            device["device_type"] = new_data.get(
                "device_type", device.get("device_type", "UNKNOWN")
            )
            device["recipe"] = new_data.get("recipe", device.get("recipe", ""))
            device["step"] = new_data.get("step", device.get("step", ""))
            device["lot_id"] = new_data.get("lot_id", device.get("lot_id", ""))
            device["wafer_id"] = new_data.get("wafer_id", device.get("wafer_id", ""))
            device["last_update"] = current_time

            # 添加传感器数据
            sensor_keys = [
                "temperature",
                "pressure",
                "rf_power",
                "endpoint",
                "humidity",
                "vibration",
                "focus_error",
            ]
            device["timestamps"].append(current_time)

            for key in sensor_keys:
                if key in new_data:
                    device[key].append(float(new_data[key]))
                else:
                    device[key].append(0.0)

        except Exception as e:
            self.logger.error(f"本地缓存更新失败: {e}")

    def setup_timers(self):
        """设置定时器 - 简化版本"""
        # UI数据同步定时器
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_components_data)
        self.sync_timer.start(1000)  # 1秒同步一次

        # 🔥 统计信息发射定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.emit_statistics_update)
        self.stats_timer.start(5000)  # 5秒发射一次统计

        # 🔥 离线设备清理定时器
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_offline_devices)
        self.cleanup_timer.start(30000)  # 30秒清理一次离线设备

    def cleanup_offline_devices(self):
        """清理离线设备"""
        try:
            current_time = time.time()
            offline_threshold = 60  # 60秒无数据认为离线

            offline_devices = []
            for device_id in list(self.active_devices):
                device_data = self.device_data[device_id]
                last_update = device_data.get("last_update")

                if last_update and (current_time - last_update) > offline_threshold:
                    offline_devices.append(device_id)

            # 移除离线设备
            for device_id in offline_devices:
                self.active_devices.discard(device_id)

            if offline_devices:
                self.device_count_changed.emit(len(self.active_devices))
                self.logger.info(f"清理离线设备: {offline_devices}")

        except Exception as e:
            self.logger.error(f"清理离线设备失败: {e}")

    def connect_signals(self):
        """连接子组件信号 - 移除controller相关"""
        try:
            # 🔥 控制面板信号连接
            self.control_panel.device_selected.connect(
                self.on_device_selected_from_panel
            )
            self.control_panel.refresh_requested.connect(self.on_refresh_requested)
            self.control_panel.clear_requested.connect(self.on_clear_requested)

            # 🔥 表格组件信号连接
            self.table_widget.device_selected.connect(
                self.on_device_selected_from_table
            )
            self.table_widget.refresh_requested.connect(self.on_refresh_requested)

            self.logger.info("信号连接完成")
        except Exception as e:
            self.logger.error(f"信号连接失败: {e}")

    @Slot()
    def on_refresh_requested(self):
        """处理刷新请求 - 直接操作enhanced_data_bus"""
        try:
            # 🔥 强制刷新Redis缓冲区
            if enhanced_data_bus.redis_buffer_enabled:
                flush_results = enhanced_data_bus.force_flush_buffers()
                self.logger.info(f"强制刷新缓冲区: {flush_results}")

            # 立即同步数据
            self.sync_components_data()
            self.emit_statistics_update()

            self.logger.info("数据刷新请求已处理")
        except Exception as e:
            self.logger.error(f"刷新请求处理失败: {e}")

    @Slot()
    def on_clear_requested(self):
        """处理清空请求 - 直接操作enhanced_data_bus"""
        try:
            if self.current_device:
                # 清空本地缓存
                if self.current_device in self.device_data:
                    for key in self.device_data[self.current_device]:
                        if isinstance(
                            self.device_data[self.current_device][key], deque
                        ):
                            self.device_data[self.current_device][key].clear()

                # 🔥 清空Redis缓冲（可选）
                if enhanced_data_bus.redis_buffer_enabled:
                    enhanced_data_bus.clear_all_buffers()

                # 清空图表显示
                if self.charts_widget:
                    self.charts_widget.clear_charts()

                self.logger.info(f"设备 {self.current_device} 数据已清空")

        except Exception as e:
            self.logger.error(f"清空请求处理失败: {e}")

    def cleanup(self):
        """组件清理"""
        try:
            # 停止定时器
            if hasattr(self, "sync_timer"):
                self.sync_timer.stop()
            if hasattr(self, "stats_timer"):
                self.stats_timer.stop()
            if hasattr(self, "cleanup_timer"):
                self.cleanup_timer.stop()

            self.logger.info("DataVisualizationWidget清理完成")
        except Exception as e:
            self.logger.error(f"组件清理失败: {e}")

    def sync_components_data(self):
        """同步组件数据 - 将本地缓存数据同步到各个子组件"""
        try:
            # 🔥 同步表格组件数据
            if self.table_widget:
                # 准备设备列表数据
                devices_data = []
                for device_id in self.active_devices:
                    device_info = self.device_data[device_id]

                    # 获取最新数据
                    latest_data = {}
                    if len(device_info["timestamps"]) > 0:
                        latest_idx = -1  # 最新数据
                        latest_data = {
                            "temperature": (
                                device_info["temperature"][latest_idx]
                                if device_info["temperature"]
                                else 0.0
                            ),
                            "pressure": (
                                device_info["pressure"][latest_idx]
                                if device_info["pressure"]
                                else 0.0
                            ),
                            "rf_power": (
                                device_info["rf_power"][latest_idx]
                                if device_info["rf_power"]
                                else 0.0
                            ),
                            "endpoint": (
                                device_info["endpoint"][latest_idx]
                                if device_info["endpoint"]
                                else 0.0
                            ),
                            "humidity": (
                                device_info["humidity"][latest_idx]
                                if device_info["humidity"]
                                else 0.0
                            ),
                            "vibration": (
                                device_info["vibration"][latest_idx]
                                if device_info["vibration"]
                                else 0.0
                            ),
                            "timestamp": (
                                device_info["timestamps"][latest_idx]
                                if device_info["timestamps"]
                                else time.time()
                            ),
                        }

                    devices_data.append(
                        {
                            "device_id": device_id,
                            "device_type": device_info.get("device_type", "UNKNOWN"),
                            "recipe": device_info.get("recipe", ""),
                            "step": device_info.get("step", ""),
                            "lot_id": device_info.get("lot_id", ""),
                            "wafer_id": device_info.get("wafer_id", ""),
                            "last_update": device_info.get("last_update"),
                            "total_records": len(device_info["timestamps"]),
                            **latest_data,
                        }
                    )

                # 更新表格数据
                self.table_widget.update_devices_data(devices_data)

            # 🔥 同步控制面板数据
            if self.control_panel:
                # 更新设备列表
                active_devices_list = sorted(list(self.active_devices))
                self.control_panel.update_device_list(active_devices_list)

                # 更新当前设备状态
                if self.current_device and self.current_device in self.device_data:
                    device_info = self.device_data[self.current_device]
                    self.control_panel.update_device_status(
                        self.current_device, device_info
                    )

            # 🔥 同步图表组件数据
            if self.charts_widget and self.current_device:
                current_device_data = self.device_data.get(self.current_device)
                if current_device_data:
                    # 转换为图表组件需要的格式
                    chart_data = {
                        "device_id": self.current_device,
                        "timestamps": list(current_device_data["timestamps"]),
                        "temperature": list(current_device_data["temperature"]),
                        "pressure": list(current_device_data["pressure"]),
                        "rf_power": list(current_device_data["rf_power"]),
                        "endpoint": list(current_device_data["endpoint"]),
                        "humidity": list(current_device_data["humidity"]),
                        "vibration": list(current_device_data["vibration"]),
                        "focus_error": list(current_device_data["focus_error"]),
                    }
                    self.charts_widget.update_device_data(chart_data)

            # 🔥 获取并显示Redis缓冲统计（如果启用）
            try:
                if (
                    hasattr(enhanced_data_bus, "redis_buffer_enabled")
                    and enhanced_data_bus.redis_buffer_enabled
                ):
                    buffer_stats = enhanced_data_bus.get_buffer_stats()

                    # 更新控制面板Redis状态显示
                    if self.control_panel and hasattr(
                        self.control_panel, "update_redis_status"
                    ):
                        redis_stats = buffer_stats.get("redis_buffer", {})
                        buffer_counts = buffer_stats.get("buffer_counts", {})
                        self.control_panel.update_redis_status(
                            redis_stats, buffer_counts
                        )
            except Exception as e:
                self.logger.debug(f"Redis统计获取失败: {e}")

            self.logger.debug("组件数据同步完成")

        except Exception as e:
            self.logger.error(f"组件数据同步失败: {e}")

    def sync_current_device_data(self):
        """同步当前设备数据 - 立即更新当前设备相关的UI"""
        try:
            if not self.current_device or self.current_device not in self.device_data:
                return

            device_info = self.device_data[self.current_device]

            # 🔥 更新控制面板当前设备状态
            if self.control_panel:
                self.control_panel.update_device_status(
                    self.current_device, device_info
                )

            # 🔥 如果当前是图表视图，立即更新图表
            current_view_index = self.stacked_widget.currentIndex()
            if current_view_index == 2 and self.charts_widget:  # 图表视图
                # 添加最新数据点到图表
                if len(device_info["timestamps"]) > 0:
                    latest_data = {
                        "timestamp": device_info["timestamps"][-1],
                        "temperature": (
                            device_info["temperature"][-1]
                            if device_info["temperature"]
                            else 0.0
                        ),
                        "pressure": (
                            device_info["pressure"][-1]
                            if device_info["pressure"]
                            else 0.0
                        ),
                        "rf_power": (
                            device_info["rf_power"][-1]
                            if device_info["rf_power"]
                            else 0.0
                        ),
                        "endpoint": (
                            device_info["endpoint"][-1]
                            if device_info["endpoint"]
                            else 0.0
                        ),
                        "humidity": (
                            device_info["humidity"][-1]
                            if device_info["humidity"]
                            else 0.0
                        ),
                        "vibration": (
                            device_info["vibration"][-1]
                            if device_info["vibration"]
                            else 0.0
                        ),
                    }

                    # 假设图表组件有添加数据点的方法
                    if hasattr(self.charts_widget, "add_data_point"):
                        self.charts_widget.add_data_point(
                            self.current_device, latest_data
                        )

            # 🔥 如果当前是表格视图，更新该设备的行
            elif current_view_index == 0 and self.table_widget:  # 表格视图
                if hasattr(self.table_widget, "update_device_row"):
                    self.table_widget.update_device_row(
                        self.current_device, device_info
                    )

            self.logger.debug(f"当前设备 {self.current_device} 数据同步完成")

        except Exception as e:
            self.logger.error(f"当前设备数据同步失败: {e}")

    @Slot(str)
    def on_device_selected_from_panel(self, device_id: str):
        """处理控制面板设备选择"""
        try:
            if device_id != self.current_device:
                self.current_device = device_id

                # 同步表格选择
                if self.table_widget and hasattr(
                    self.table_widget, "set_selected_device"
                ):
                    self.table_widget.set_selected_device(device_id)

                # 立即同步当前设备数据
                self.sync_current_device_data()

                # 发射设备选择信号
                self.device_selected.emit(device_id)

                self.logger.info(f"从控制面板选择设备: {device_id}")

        except Exception as e:
            self.logger.error(f"控制面板设备选择处理失败: {e}")

    @Slot(str)
    def on_device_selected_from_table(self, device_id: str):
        """处理表格设备选择"""
        try:
            if device_id != self.current_device:
                self.current_device = device_id

                # 同步控制面板选择
                if self.control_panel and hasattr(
                    self.control_panel, "set_current_device"
                ):
                    self.control_panel.set_current_device(device_id)

                # 自动切换到图表视图显示详细数据
                self.stacked_widget.setCurrentIndex(2)
                self.visualization_mode_changed.emit("chart")

                # 立即同步当前设备数据
                self.sync_current_device_data()

                # 发射设备选择信号
                self.device_selected.emit(device_id)

                self.logger.info(f"从表格选择设备: {device_id}")

        except Exception as e:
            self.logger.error(f"表格设备选择处理失败: {e}")

    def switch_to_view(self, view_name: str):
        """切换视图"""
        try:
            view_mapping = {"table": 0, "dashboard": 1, "chart": 2}

            if view_name in view_mapping:
                self.stacked_widget.setCurrentIndex(view_mapping[view_name])
                self.visualization_mode_changed.emit(view_name)

                # 切换后立即同步数据
                self.sync_components_data()

                self.logger.info(f"切换到 {view_name} 视图")
            else:
                self.logger.warning(f"未知视图类型: {view_name}")

        except Exception as e:
            self.logger.error(f"视图切换失败: {e}")

    def get_current_status(self) -> dict:
        """获取当前状态信息"""
        try:
            return {
                "active_devices": len(self.active_devices),
                "current_device": self.current_device,
                "current_view": self.stacked_widget.currentIndex(),
                "total_records": sum(
                    len(device_data.get("timestamps", []))
                    for device_data in self.device_data.values()
                ),
                "devices_list": sorted(list(self.active_devices)),
            }
        except Exception as e:
            self.logger.error(f"获取状态信息失败: {e}")
            return {}

    def get_device_data(self, device_id: str) -> dict:
        """获取指定设备的数据"""
        return dict(self.device_data.get(device_id, {}))

    def clear_device_data(self, device_id: str = None):
        """清空设备数据"""
        try:
            if device_id:
                # 清空指定设备
                if device_id in self.device_data:
                    for key, value in self.device_data[device_id].items():
                        if isinstance(value, deque):
                            value.clear()
                    self.logger.info(f"设备 {device_id} 数据已清空")
            else:
                # 清空所有设备
                for device_id in self.device_data:
                    for key, value in self.device_data[device_id].items():
                        if isinstance(value, deque):
                            value.clear()
                self.device_data.clear()
                self.active_devices.clear()
                self.current_device = None
                self.logger.info("所有设备数据已清空")

            # 刷新UI
            self.sync_components_data()

        except Exception as e:
            self.logger.error(f"清空设备数据失败: {e}")
