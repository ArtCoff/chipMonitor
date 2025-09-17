import logging
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QStatusBar,
    QFrame,
    QPushButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QIcon
from typing import Any
from utils.path import QSS_DIR, ICON_DIR
from .components.DataVisualizationWidget import DataVisualizationWidget
from .components.MenuBar import MenuBar
from .components.StackControl import StackControlWidget
from .components.NetworkControlPanel import NetworkControlPanel
from .components.DatabaseControlPanel import DatabaseControlPanel
from core.mqtt_client import mqtt_manager
from core.thread_pool import thread_pool, TaskType, TaskPriority
from core.enhanced_data_bus import enhanced_data_bus


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChipMonitor - 半导体工艺监控系统")
        self.setWindowIcon(QIcon(str(ICON_DIR / "icon_monitoring.png")))
        self.resize(800, 600)

        self.logger = logging.getLogger("MainWindow")

        # 窗口引用
        self.history_window = None
        self.NetworkControlPanel = None
        self.database_panel = None

        # 主要组件
        self.visualization_widget = None
        self.stack_control_widget = None

        # 当前可视化模式
        self.current_mode = "table"
        self.redis_status_timer = QTimer()
        self.redis_status_timer.timeout.connect(self.update_redis_status)
        self.redis_status_timer.start(10000)  # 10秒检查一次Redis状态

        # 初始化UI和样式
        self.setup_ui()
        self.load_qss_style()
        self.setup_signal_connections()

    def setup_ui(self):
        """设置主界面布局"""
        # 设置中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局 - 垂直布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 1. 菜单栏
        self.menu_bar = MenuBar()
        self.menu_bar.setObjectName("menuBar")
        self.menu_bar.setFixedHeight(80)  # 🔥 设置固定高度
        main_layout.addWidget(self.menu_bar)

        # 2. 可视化区域（主要内容）
        visualization_area = self.create_visualization_area()
        main_layout.addWidget(visualization_area, 1)

        # 3. 状态栏
        self.setup_status_bar()

    def create_visualization_area(self):
        """创建可视化区域 - 包含控制器和可视化组件"""
        # 可视化容器
        viz_container = QFrame()
        viz_container.setObjectName("visualizationContainer")
        viz_container.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)

        # 主要布局 - 水平布局
        main_layout = QHBoxLayout(viz_container)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 左侧：StackControl控制器
        self.stack_control_widget = StackControlWidget()
        main_layout.addWidget(self.stack_control_widget)

        # 右侧：可视化组件区域
        viz_content = self.create_visualization_content()
        main_layout.addWidget(viz_content, 1)

        return viz_container

    def create_visualization_content(self):
        """创建可视化内容区域"""
        content_frame = QFrame()
        content_frame.setObjectName("visualizationContent")
        content_frame.setFrameStyle(QFrame.StyledPanel)

        layout = QVBoxLayout(content_frame)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        # 数据可视化组件
        self.visualization_widget = DataVisualizationWidget()
        layout.addWidget(self.visualization_widget, 1)

        return content_frame

    def setup_status_bar(self):
        """设置状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 状态信息
        self.status_label = QLabel("系统就绪")

        # 连接指示器
        self.connection_indicator = QLabel("● 未连接")
        self.connection_indicator.setStyleSheet("color: red; font-weight: bold;")

        # 设备和数据计数
        self.device_count_label = QLabel("设备: 0")
        self.data_count_label = QLabel("数据: 0")

        # 可视化模式指示器
        self.visualization_mode_label = QLabel("模式: 表格")

        # 添加到状态栏
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.visualization_mode_label)
        self.status_bar.addPermanentWidget(self.device_count_label)
        self.status_bar.addPermanentWidget(self.data_count_label)
        self.status_bar.addPermanentWidget(self.connection_indicator)

    def load_qss_style(self):
        """加载QSS样式表"""
        qss_file = QSS_DIR / "style.qss"

        if not qss_file.exists():
            self.logger.warning(f"样式文件未找到: {qss_file}")
            return

        try:
            with open(qss_file, "r", encoding="utf-8") as f:
                style_content = f.read()
                self.setStyleSheet(style_content)
            self.logger.info(f"成功加载样式表: {qss_file}")
        except Exception as e:
            self.logger.error(f"加载样式表失败: {e}")

    def setup_signal_connections(self):
        """设置信号连接"""
        # 菜单栏信号连接
        if hasattr(self.menu_bar, "network_debug_signal"):
            self.menu_bar.network_debug_signal.connect(self.open_network_debug_window)
        if hasattr(self.menu_bar, "system_debug_signal"):
            self.menu_bar.system_debug_signal.connect(self.open_system_debug_window)
        if hasattr(self.menu_bar, "etl_config_signal"):
            self.menu_bar.etl_config_signal.connect(self.open_etl_config_window)
        if hasattr(self.menu_bar, "settings_signal"):
            self.menu_bar.settings_signal.connect(self.open_settings_window)
        if hasattr(self.menu_bar, "redis_signal"):
            self.menu_bar.database_signal.connect(self.open_redis_window)
        if hasattr(self.menu_bar, "database_signal"):
            self.menu_bar.database_signal.connect(self.open_database_window)
        if hasattr(self.menu_bar, "exit_signal"):
            self.menu_bar.exit_signal.connect(self.close)

        # StackControl信号连接
        if self.stack_control_widget:
            self.stack_control_widget.mode_changed.connect(self.on_mode_changed)

        # 可视化组件信号连接
        if self.visualization_widget:
            self.visualization_widget.device_selected.connect(self.on_device_selected)
        mqtt_manager.connection_changed.connect(
            self.on_mqtt_connection_changed, Qt.QueuedConnection
        )
        mqtt_manager.connection_status.connect(
            self.on_mqtt_connection_status, Qt.QueuedConnection
        )

        # 设备发现信号
        mqtt_manager.device_discovered.connect(
            self.on_device_discovered, Qt.QueuedConnection
        )

        # 统计信息信号
        mqtt_manager.statistics_updated.connect(
            self.on_mqtt_statistics_updated, Qt.QueuedConnection
        )
        # DataBus系统信号
        enhanced_data_bus.message_published.connect(
            self.on_databus_message_published, Qt.QueuedConnection
        )
        enhanced_data_bus.message_delivered.connect(
            self.on_databus_message_delivered, Qt.QueuedConnection
        )

    # ================== 模式切换事件处理 ==================
    @Slot(dict)
    def on_mqtt_statistics_updated(self, stats: dict):
        """更新MQTT统计信息到UI"""
        try:
            self.status_label.setText(
                f"MQTT: 收{stats['messages_received']}条, 连接{int(stats['connection_duration'])}秒"
            )
            if "known_devices_count" in stats:
                self.update_device_count(stats["known_devices_count"])
        except Exception as e:
            self.logger.error(f"更新统计失败: {e}")

    @Slot(str)
    def on_mode_changed(self, mode):
        self.current_mode = mode

        # 通知可视化组件切换模式
        if self.visualization_widget:
            # mode_page_mapping = {"table": 0, "dashboard": 1, "chart": 2}
            self.visualization_widget.switch_to_view(mode)

        # 更新UI显示
        mode_names = {
            "table": "数据表格",
            "dashboard": "实时仪表盘",
            "chart": "趋势曲线",
        }
        mode_text = mode_names.get(mode, mode)

        # 更新状态栏和标题
        self.visualization_mode_label.setText(f"模式: {mode_text}")
        self.status_label.setText(f"切换到{mode_text}模式")

        self.logger.info(f"模式切换到: {mode}")

    # ================== 可视化组件事件处理 ==================

    @Slot(str)
    def on_device_selected(self, device_id):
        """设备选择事件处理 - 同步到控制器"""
        try:
            self.logger.info(f"选择设备: {device_id}")

            # 🔥 设置控制器的当前设备
            self.visualization_controller.set_current_device(device_id)

            # 更新UI显示
            self.status_label.setText(f"正在监控设备: {device_id}")
            self.visualization_status.setText(f"● 监控设备: {device_id}")

            # 获取设备信息显示更详细的状态
            device_data = self.visualization_controller.get_device_data(device_id)
            if device_data:
                device_type = device_data.get("device_type", "UNKNOWN")
                vendor = device_data.get("vendor", "UNKNOWN")
                self.status_label.setText(
                    f"监控设备: {device_id} [{vendor} {device_type}]"
                )

        except Exception as e:
            self.logger.error(f"处理设备选择失败: {e}")

    # ================== 调试窗口管理 ==================

    @Slot()
    def open_network_debug_window(self):
        """打开网络调试窗口"""
        if (
            not hasattr(self, "network_debug_window")
            or self.network_debug_window is None
        ):
            self.network_debug_window = NetworkControlPanel()

        self.network_debug_window.show()
        self.network_debug_window.raise_()
        self.network_debug_window.activateWindow()

    @Slot()
    def open_system_debug_window(self):
        """打开系统调试窗口"""
        self.logger.info("打开系统调试窗口")

    @Slot()
    def open_etl_config_window(self):
        """打开ETL配置窗口"""
        self.logger.info("打开ETL配置窗口")

    @Slot()
    def open_settings_window(self):
        """打开设置窗口"""
        self.logger.info("打开设置窗口")

    @Slot()
    def open_redis_window(self):
        self.logger.info("打开Redis管理窗口")

    @Slot()
    def open_database_window(self):
        """打开数据库管理窗口"""
        try:
            if self.database_panel is None:
                self.database_panel = DatabaseControlPanel(self)

                # 连接配置变更信号
                self.database_panel.config_changed.connect(
                    self.on_database_config_changed
                )

            self.database_panel.show()
            self.database_panel.raise_()
            self.database_panel.activateWindow()

            self.logger.info("数据库管理窗口已打开")

        except Exception as e:
            self.logger.error(f"打开数据库管理窗口失败: {e}")

    @Slot(object)
    def on_database_config_changed(self, config):
        """处理数据库配置变更"""
        try:
            self.logger.info(f"数据库配置已更新: {config.host}:{config.port}")
            self.status_label.setText("数据库配置已更新")
        except Exception as e:
            self.logger.error(f"处理数据库配置变更失败: {e}")

    # ================== 状态更新方法 ==================

    def update_connection_status(self, connected: bool, message: str = ""):
        """更新连接状态"""
        if connected:
            self.status_label.setText("已连接到服务")
            self.connection_indicator.setText("● 已连接")
            self.connection_indicator.setStyleSheet("color: green; font-weight: bold;")
            self.visualization_status.setText("● 数据流活跃")
            self.visualization_status.setStyleSheet(
                "color: #27AE60; font-weight: bold;"
            )
        else:
            self.status_label.setText("未连接到服务")
            self.connection_indicator.setText("● 未连接")
            self.connection_indicator.setStyleSheet("color: red; font-weight: bold;")
            self.visualization_status.setText("● 等待连接")
            self.visualization_status.setStyleSheet(
                "color: #E74C3C; font-weight: bold;"
            )

    def update_device_count(self, count: int):
        """更新设备计数"""
        self.device_count_label.setText(f"设备: {count}")
        if self.stack_control_widget:
            self.stack_control_widget.update_device_count(count)

    def update_data_count(self, count: int):
        """更新数据计数"""
        self.data_count_label.setText(f"数据: {count}")

    # ================== 窗口事件处理 ==================

    def closeEvent(self, event):
        """关闭事件处理"""
        try:
            self.logger.info("关闭主窗口...")

            # 🔥 停止可视化控制器
            if self.visualization_controller:
                self.visualization_controller.stop()

            # 关闭子窗口
            if hasattr(self, "history_window") and self.history_window:
                self.history_window.close()
            if hasattr(self, "network_debug_window") and self.network_debug_window:
                self.network_debug_window.close()

            # 停止可视化组件
            if self.visualization_widget and hasattr(
                self.visualization_widget, "cleanup"
            ):
                self.visualization_widget.cleanup()

            super().closeEvent(event)
            self.logger.info("主窗口已关闭")

        except Exception as e:
            self.logger.error(f"关闭窗口时发生错误: {e}")
            super().closeEvent(event)

    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        self.logger.info("主窗口已显示")
        self.status_label.setText("系统就绪 - 界面加载完成")

    @Slot(bool, str)
    def on_mqtt_connection_changed(self, connected: bool, message: str):
        """处理MQTT连接状态变化"""
        try:
            self.update_connection_status(connected, message)

            if connected:
                self.status_label.setText("MQTT连接成功")
            else:
                self.status_label.setText(f"MQTT连接断开: {message}")

        except Exception as e:
            self.logger.error(f"处理MQTT连接状态变化失败: {e}")

    @Slot(str)
    def on_mqtt_connection_status(self, status: str):
        """处理MQTT连接状态文本"""
        try:
            # 更新状态栏显示
            self.status_label.setText(f"MQTT: {status}")

        except Exception as e:
            self.logger.error(f"处理MQTT连接状态失败: {e}")

    @Slot(str, dict)
    def on_device_discovered(self, device_id: str, device_info: dict):
        """处理设备发现事件"""
        try:
            device_type = device_info.get("device_type", "UNKNOWN")
            vendor = device_info.get("vendor", "UNKNOWN")

            self.status_label.setText(f"发现新设备: {device_id} ({device_type})")
            self.logger.info(f"新设备发现: {device_id} - {vendor} {device_type}")

            # 可以在这里更新设备管理UI

        except Exception as e:
            self.logger.error(f"处理设备发现失败: {e}")

    # 🔥 8. DataBus系统信号处理

    @Slot(str, str)
    def on_databus_message_published(self, channel: str, source: str):
        """DataBus消息发布通知"""
        if channel != "telemetry_data":
            self.logger.debug(f"DataBus发布: {channel} <- {source}")

    @Slot(str, int)
    def on_databus_message_delivered(self, channel: str, count: int):
        """DataBus消息投递通知"""
        # 可用于性能监控
        if count > 0 and channel != "telemetry_data":
            self.logger.debug(f"DataBus投递: {channel} -> {count}个订阅者")

    @Slot(dict)
    def on_mqtt_statistics_updated(self, stats: dict):
        """更新MQTT统计信息到UI - 集成Redis统计"""
        try:
            # 获取增强数据总线统计
            enhanced_stats = enhanced_data_bus.get_buffer_stats()
            redis_stats = enhanced_stats.get("redis_buffer", {})

            # MQTT统计
            messages_received = stats.get("messages_received", 0)
            connection_duration = int(stats.get("connection_duration", 0))

            # Redis缓冲统计
            buffered_messages = redis_stats.get("buffered_messages", 0)
            redis_connected = redis_stats.get("redis_connected", False)

            # 综合状态显示
            redis_status = "✓" if redis_connected else "✗"
            status_text = f"MQTT: 收{messages_received}条 | Redis{redis_status}: 缓存{buffered_messages}条"

            # 更新设备计数
            if "known_devices_count" in stats:
                self.update_device_count(stats["known_devices_count"])

        except Exception as e:
            self.logger.error(f"更新增强统计失败: {e}")

    @Slot(list)
    def on_device_list_updated(self, device_list: list):
        """处理设备列表更新"""
        try:
            device_count = len(device_list)
            self.update_device_count(device_count)

            if device_count > 0:
                self.status_label.setText(f"活跃设备: {device_count}个")
                self.visualization_status.setText("● 数据流活跃")
                self.visualization_status.setStyleSheet(
                    "color: #27AE60; font-weight: bold;"
                )
            else:
                self.status_label.setText("暂无活跃设备")
                self.visualization_status.setText("● 等待设备数据")
                self.visualization_status.setStyleSheet(
                    "color: #F39C12; font-weight: bold;"
                )

            # 更新StackControl的设备信息
            if self.stack_control_widget:
                self.stack_control_widget.update_device_list(device_list)

            self.logger.debug(f"设备列表更新: {device_count}个设备")

        except Exception as e:
            self.logger.error(f"处理设备列表更新失败: {e}")

    @Slot(str, dict)
    def on_device_statistics_updated(self, device_id: str, stats: dict):
        """处理设备统计信息更新"""
        try:
            # 更新数据计数 - 使用所有设备的总记录数
            total_records = stats.get("total_records", 0)
            self.update_data_count(total_records)

            # 更新状态显示 - 显示当前设备的关键信息
            current_device = self.visualization_controller.current_device
            if device_id == current_device:
                avg_temp = stats.get("avg_temperature", 0)
                update_freq = stats.get("update_freq", 0)

                self.status_label.setText(
                    f"设备: {device_id} | 平均温度: {avg_temp:.1f}°C | 频率: {update_freq:.1f}Hz"
                )

            self.logger.debug(f"设备统计更新: {device_id} | 记录数: {total_records}")

        except Exception as e:
            self.logger.error(f"处理设备统计更新失败: {e}")

    @Slot(bool, str)
    def on_visualization_connection_changed(self, connected: bool, message: str):
        """处理可视化连接状态变化"""
        try:
            if connected:
                self.connection_indicator.setText("● 数据流")
                self.connection_indicator.setStyleSheet(
                    "color: #27AE60; font-weight: bold;"
                )

                self.visualization_status.setText("● 数据流活跃")
                self.visualization_status.setStyleSheet(
                    "color: #27AE60; font-weight: bold;"
                )
            else:
                self.connection_indicator.setText("● 无数据")
                self.connection_indicator.setStyleSheet(
                    "color: #F39C12; font-weight: bold;"
                )

                self.visualization_status.setText("● 等待数据")
                self.visualization_status.setStyleSheet(
                    "color: #F39C12; font-weight: bold;"
                )

            self.logger.info(f"可视化连接状态变化: {connected} - {message}")

        except Exception as e:
            self.logger.error(f"处理可视化连接状态变化失败: {e}")

    @Slot()
    def update_redis_status(self):
        """定期检查Redis状态"""
        try:
            stats = enhanced_data_bus.get_buffer_stats()
            redis_stats = stats.get("redis_buffer", {})
            buffer_counts = stats.get("buffer_counts", {})

            if redis_stats.get("redis_connected"):
                # Redis正常
                total_buffered = sum(buffer_counts.values())
                if total_buffered > 0:
                    self.status_label.setText(
                        f"系统正常 | Redis缓冲: {total_buffered}条消息"
                    )
            else:
                # Redis断连
                self.status_label.setText("系统运行 | Redis缓冲离线")

        except Exception as e:
            self.logger.error(f"Redis状态检查失败: {e}")
