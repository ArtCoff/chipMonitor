import logging
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QStatusBar,
    QFrame,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QIcon
from utils.path import QSS_DIR, ICON_DIR
from .components.MenuBar import MenuBar
from .analysis_window import HistoryDataWindow
from .components.StackControl import StackControlWidget
from .components.NetworkControlPanel import NetworkControlPanel
from .components.DatabaseControlPanel import DatabaseControlPanel
from .components.DataVisualizationWidget import DataVisualizationWidget

from core.data_bus import get_data_bus
from core.mqtt_client import get_mqtt_manager
from core.database_manager import get_db_manager
from core.device_manager import get_device_manager


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChipMonitor - 半导体工艺监控系统")
        self.setWindowIcon(QIcon(str(ICON_DIR / "icon_monitoring.png")))
        self.resize(1200, 600)

        self.logger = logging.getLogger("MainWindow")
        self.device_data_dict = {}

        # 窗口引用

        self.history_data_window = None
        self.NetworkControlPanel = None
        self.database_panel = None

        # 主要组件
        self.visualization_widget = None
        self.stack_control_widget = None

        self.persistence_status_timer = QTimer()
        self.persistence_status_timer.timeout.connect(self.update_persistence_status)
        self.persistence_status_timer.start(10000)  # 10秒检查一次持久化服务状态

        # device_manager.load_devices_from_db()
        # 当前可视化模式
        self.current_mode = "table"
        # 添加启动服务定时器
        self.startup_timer = QTimer()
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self.auto_start_services)
        self.data_bus = get_data_bus()
        self.mqtt_manager = get_mqtt_manager()
        self.db_manager = get_db_manager()
        self.device_manager = get_device_manager()
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
        self.menu_bar.setFixedHeight(80)  #  设置固定高度
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

        # 可视化模式指示器
        self.visualization_mode_label = QLabel("模式: 表格")

        # 添加到状态栏
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.visualization_mode_label)
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

        if hasattr(self.menu_bar, "settings_signal"):
            self.menu_bar.settings_signal.connect(self.open_settings_window)
        if hasattr(self.menu_bar, "history_signal"):
            self.menu_bar.history_signal.connect(self.open_history_window)
        if hasattr(self.menu_bar, "database_signal"):
            self.menu_bar.database_signal.connect(self.open_database_window)
        if hasattr(self.menu_bar, "exit_signal"):
            self.menu_bar.exit_signal.connect(self.close)
            # 连接信号到UI组件
        # StackControl信号连接
        if self.stack_control_widget:
            self.stack_control_widget.mode_changed.connect(self.on_mode_changed)

        # 可视化组件信号连接
        self.mqtt_manager.connection_changed.connect(
            self.on_mqtt_connection_changed, Qt.QueuedConnection
        )
        self.mqtt_manager.connection_status.connect(
            self.on_mqtt_connection_status, Qt.QueuedConnection
        )

        # 统计信息信号
        self.mqtt_manager.statistics_updated.connect(
            self.on_mqtt_statistics_updated, Qt.QueuedConnection
        )
        # 添加数据库持久化服务信号连接
        from services.database_persistence import database_persistence_service

        self.database_persistence_service = database_persistence_service

        self.database_persistence_service.service_started.connect(
            self.on_persistence_service_started, Qt.QueuedConnection
        )
        self.database_persistence_service.service_stopped.connect(
            self.on_persistence_service_stopped, Qt.QueuedConnection
        )
        self.database_persistence_service.stats_updated.connect(
            self.on_persistence_stats_updated, Qt.QueuedConnection
        )

    # ================== 模式切换事件处理 ==================
    @Slot(dict)
    def on_mqtt_statistics_updated(self, stats: dict):
        """更新MQTT统计信息到UI"""
        try:
            messages_received = stats.get("messages_received", 0)
            connection_duration = int(stats.get("connection_duration", 0))

            # 获取DataBus统计
            databus_stats = self.data_bus.get_stats()
            published = databus_stats.get("published", 0)
            delivered = databus_stats.get("delivered", 0)

            # 简化状态显示
            status_text = f"MQTT: 收{messages_received}条 | DataBus: 发布{published}条/投递{delivered}次"
            self.status_label.setText(status_text)

            # 更新设备计数
            if "known_devices_count" in stats:
                self.update_device_count(stats["known_devices_count"])

        except Exception as e:
            self.logger.error(f"更新统计失败: {e}")

    # 🔥 新增：数据库持久化服务信号处理
    @Slot()
    def on_persistence_service_started(self):
        """持久化服务启动"""
        self.status_label.setText("数据库持久化服务已启动")
        self.logger.info("数据库持久化服务已启动")

    @Slot()
    def on_persistence_service_stopped(self):
        """持久化服务停止"""
        self.status_label.setText("数据库持久化服务已停止")
        self.logger.warning("数据库持久化服务已停止")

    @Slot(dict)
    def on_persistence_stats_updated(self, stats: dict):
        """持久化服务统计更新"""
        try:
            messages_batched = stats.get("messages_batched", 0)
            messages_persisted = stats.get("messages_persisted", 0)

            if messages_batched > 0 or messages_persisted > 0:
                self.status_label.setText(
                    f"数据持久化: 队列{messages_batched}条/已存储{messages_persisted}条"
                )
        except Exception as e:
            self.logger.error(f"处理持久化统计失败: {e}")

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
    def open_settings_window(self):
        """打开设置窗口"""
        self.logger.info("打开设置窗口")

    @Slot()
    def open_history_window(self):
        try:
            if not self.history_data_window:
                self.history_data_window = HistoryDataWindow(self)

                # 连接信号
                self.history_data_window.data_selected.connect(
                    self.on_history_data_selected
                )

            self.history_data_window.show_window()
            self.logger.info("历史数据查询窗口已打开")

        except Exception as e:
            self.logger.error(f"打开历史数据查询窗口失败: {e}")

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

    # ================== 窗口事件处理 ==================

    @Slot(bool, str)
    def on_mqtt_connection_changed(self, connected: bool, message: str):
        """处理MQTT连接状态变化"""
        try:
            # self.update_connection_status(connected, message)

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

    @Slot(bool, str)
    def on_visualization_connection_changed(self, connected: bool, message: str):
        """处理可视化连接状态变化"""
        try:
            if connected:
                self.connection_indicator.setText("● 数据流")
                self.connection_indicator.setStyleSheet(
                    "color: #27AE60; font-weight: bold;"
                )

            else:
                self.connection_indicator.setText("● 无数据")
                self.connection_indicator.setStyleSheet(
                    "color: #F39C12; font-weight: bold;"
                )

            self.logger.info(f"可视化连接状态变化: {connected} - {message}")

        except Exception as e:
            self.logger.error(f"处理可视化连接状态变化失败: {e}")

    @Slot()
    def update_persistence_status(self):
        """定期检查持久化服务状态"""
        try:
            service_stats = self.database_persistence_service.get_service_stats()

            if service_stats.get("running"):
                # 服务正常运行
                total_queued = sum(service_stats.get("queue_sizes", {}).values())
                db_connected = service_stats.get("database_connected", False)

                if db_connected:
                    if total_queued > 0:
                        self.status_label.setText(
                            f"系统正常 | 数据库队列: {total_queued}条"
                        )
                    else:
                        self.status_label.setText("系统正常 | 数据库同步")
                else:
                    self.status_label.setText("系统运行 | 数据库离线")
            else:
                self.status_label.setText("系统运行 | 持久化服务离线")

        except Exception as e:
            self.logger.error(f"持久化服务状态检查失败: {e}")

    @Slot()
    def auto_start_services(self):
        """自动启动服务"""
        try:
            self.logger.info("开始自动启动服务...")
            self.status_label.setText("正在启动系统服务...")

            # 🔥 1. 启动数据库连接
            db_success = self.auto_start_database()

            # 🔥 2. 启动数据库持久化服务（依赖数据库连接）
            persistence_success = False
            if db_success:
                persistence_success = self.auto_start_persistence_service()

            # 🔥 3. 启动MQTT服务（独立于数据库）
            mqtt_success = self.auto_start_mqtt_service()

            # 🔥 4. 更新UI状态
            self.update_startup_status(db_success, persistence_success, mqtt_success)

            # 🔥 5. 刷新MenuBar状态显示
            # QTimer.singleShot(1000, self.refresh_all_status)

        except Exception as e:
            self.logger.error(f"自动启动服务失败: {e}")
            self.status_label.setText(f"服务启动失败: {e}")

    def auto_start_database(self) -> bool:
        """自动启动数据库连接"""
        try:
            self.status_label.setText("正在连接数据库...")

            if self.db_manager.is_connected():
                self.logger.info("数据库已连接，跳过启动")
                return True

            # 尝试连接数据库
            success = self.db_manager.connect()

            if success:
                self.logger.info("✅ 数据库自动连接成功")
                self.status_label.setText("数据库连接成功")
                return True
            else:
                self.logger.warning("❌ 数据库自动连接失败")
                self.status_label.setText("数据库连接失败")
                return False

        except Exception as e:
            self.logger.error(f"数据库自动连接异常: {e}")
            self.status_label.setText(f"数据库连接异常: {e}")
            return False

    def auto_start_persistence_service(self) -> bool:
        """自动启动数据库持久化服务"""
        try:
            self.status_label.setText("正在启动持久化服务...")

            # 检查服务状态
            stats = self.database_persistence_service.get_service_stats()
            if stats.get("running"):
                self.logger.info("持久化服务已运行，跳过启动")
                return True

            # 启动持久化服务
            success = self.database_persistence_service.start()

            if success:
                self.logger.info("✅ 持久化服务自动启动成功")
                self.status_label.setText("持久化服务启动成功")
                return True
            else:
                self.logger.warning("❌ 持久化服务自动启动失败")
                self.status_label.setText("持久化服务启动失败")
                return False

        except Exception as e:
            self.logger.error(f"持久化服务自动启动异常: {e}")
            self.status_label.setText(f"持久化服务启动异常: {e}")
            return False

    def auto_start_mqtt_service(self) -> bool:
        """自动启动MQTT服务"""
        try:
            self.status_label.setText("正在启动MQTT服务...")

            if self.mqtt_manager.is_connected():
                self.logger.info("MQTT已连接，跳过启动")
                return True

            # 🔥 从配置加载MQTT设置（可选）
            mqtt_config = self.load_mqtt_config()

            # 启动MQTT连接
            if mqtt_config:
                success = self.mqtt_manager.connect(**mqtt_config)
            else:
                success = self.mqtt_manager.connect()  # 使用默认配置

            if success:
                self.logger.info("✅ MQTT服务自动启动成功")

                # 🔥 自动订阅默认主题
                self.auto_subscribe_topics()
                return True
            else:
                self.logger.warning("❌ MQTT服务自动启动失败")
                self.status_label.setText("MQTT服务启动失败")
                return False

        except Exception as e:
            self.logger.error(f"MQTT服务自动启动异常: {e}")
            self.status_label.setText(f"MQTT服务启动异常: {e}")
            return False

    def load_mqtt_config(self) -> dict:
        """加载MQTT配置"""
        try:
            # 🔥 这里可以从配置文件加载，现在使用默认值
            return {"host": "localhost", "port": 1883, "username": "", "password": ""}
        except Exception as e:
            self.logger.debug(f"加载MQTT配置失败: {e}")
            return {}

    def auto_subscribe_topics(self):
        """自动订阅默认主题"""
        try:
            # 🔥 默认订阅的主题列表
            default_topics = [
                "factory/telemetry/+/+",  # 所有设备遥测数据
                "factory/telemetry/+/+/json",  # JSON格式遥测数据
                "factory/telemetry/+/+/msgpack",  # MessagePack格式
                "gateway/+/status",  # 网关状态
                "system/alerts",  # 系统告警
            ]

            for topic in default_topics:
                success = self.mqtt_manager.subscribe_topic(topic, qos=1)
                if success:
                    self.logger.info(f"自动订阅成功: {topic}")
                else:
                    self.logger.warning(f"自动订阅失败: {topic}")

        except Exception as e:
            self.logger.error(f"自动订阅主题失败: {e}")

    def update_startup_status(
        self, db_success: bool, persistence_success: bool, mqtt_success: bool
    ):
        """更新启动状态显示"""
        try:
            # 🔥 统计成功的服务数
            success_count = sum([db_success, persistence_success, mqtt_success])
            total_services = 3

            if success_count == total_services:
                self.status_label.setText("✅ 所有服务启动成功")
                self.logger.info("所有服务启动完成")
            elif success_count > 0:
                self.status_label.setText(
                    f"⚠️ 部分服务启动成功 ({success_count}/{total_services})"
                )
                self.logger.warning(
                    f"部分服务启动失败: DB={db_success}, 持久化={persistence_success}, MQTT={mqtt_success}"
                )
            else:
                self.status_label.setText("❌ 所有服务启动失败")
                self.logger.error("所有服务启动失败")

        except Exception as e:
            self.logger.error(f"更新启动状态失败: {e}")

    def closeEvent(self, event):
        """关闭事件处理"""
        try:
            self.logger.info("关闭主窗口...")

            # 关闭子窗口
            if hasattr(self, "history_data_window") and self.history_data_window:
                self.history_data_window.close()
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
        self.device_manager.load_devices_from_db()
        if not self.startup_timer.isActive():
            self.startup_timer.start(2000)
