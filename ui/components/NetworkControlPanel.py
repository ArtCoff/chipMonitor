import logging
from datetime import datetime
from typing import Any
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QTextEdit,
    QGridLayout,
    QFormLayout,
    QSplitter,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QIcon

from config.mqtt_config import get_current_config, save_config, MqttConfig
from core.mqtt_client import get_mqtt_manager
from core.device_manager import get_device_manager
from utils.path import ICON_DIR


class NetworkControlPanel(QDialog):
    config_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.mqtt_manager = get_mqtt_manager()
        self.device_manager = get_device_manager()

        # 窗口配置
        self.setWindowTitle("网络调试")
        self.setWindowIcon(QIcon(str(ICON_DIR / "icon_network.png")))
        self.setFixedSize(600, 500)
        self.setModal(False)

        # 配置和状态
        self.current_config = get_current_config()
        self._config_modified = False

        # 简化统计
        self.stats = {
            "messages": 0,
            "devices": 0,
            "connected_time": None,
        }
        self.online_devices = set()

        # 初始化
        self.setup_ui()
        self.load_config()
        self.setup_connections()

        # 状态更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(2000)  # 2秒更新一次

    def setup_ui(self):
        """设置UI"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([400, 600])

        # 连接配置组
        left_panel = QFrame()
        left_layout = QVBoxLayout()
        config_group = self.create_config_group()
        left_layout.addWidget(config_group)

        # 连接状态组
        status_group = self.create_status_group()
        left_layout.addWidget(status_group)
        buttons = self.create_buttons()
        left_layout.addLayout(buttons)
        left_panel.setLayout(left_layout)
        splitter.addWidget(left_panel)

        # 日志组
        log_group = self.create_log_group()
        splitter.addWidget(log_group)
        main_layout.addWidget(splitter)

    def create_config_group(self):
        """创建配置组"""
        group = QGroupBox("MQTT连接配置")
        layout = QFormLayout(group)

        # 服务器地址
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("localhost")
        self.host_edit.textChanged.connect(self.mark_modified)
        layout.addRow("服务器:", self.host_edit)

        # 端口
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1, 65535)
        self.port_spinbox.setValue(1883)
        self.port_spinbox.valueChanged.connect(self.mark_modified)
        layout.addRow("端口:", self.port_spinbox)

        # 用户名和密码
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("可选")
        self.username_edit.textChanged.connect(self.mark_modified)
        layout.addRow("用户名:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("可选")
        self.password_edit.textChanged.connect(self.mark_modified)
        layout.addRow("密码:", self.password_edit)

        # 增加主题订阅设置
        # 设备主题前缀
        self.device_topic_edit = QLineEdit()
        self.device_topic_edit.setPlaceholderText("factory/telemetry/+/+/msgpack")
        self.device_topic_edit.textChanged.connect(self.mark_modified)
        layout.addRow("设备主题:", self.device_topic_edit)

        # 网关主题前缀
        self.gateway_topic_edit = QLineEdit()
        self.gateway_topic_edit.setPlaceholderText("gateway/+/+")
        self.gateway_topic_edit.textChanged.connect(self.mark_modified)
        layout.addRow("网关主题:", self.gateway_topic_edit)

        return group

    def create_status_group(self):
        """创建状态组"""
        group = QGroupBox("连接状态")
        layout = QGridLayout(group)

        # 连接状态
        layout.addWidget(QLabel("连接状态:"), 0, 0)
        self.status_label = QLabel("未连接")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.status_label, 0, 1)

        # 服务器信息
        layout.addWidget(QLabel("服务器:"), 1, 0)
        self.server_label = QLabel("--")
        layout.addWidget(self.server_label, 1, 1)

        # 接收消息数
        layout.addWidget(QLabel("接收消息:"), 2, 0)
        self.messages_label = QLabel("0")
        self.messages_label.setStyleSheet("font-weight: bold; color: #2E86AB;")
        layout.addWidget(self.messages_label, 2, 1)

        # 在线设备数
        layout.addWidget(QLabel("在线设备:"), 3, 0)
        self.devices_label = QLabel("0")
        self.devices_label.setStyleSheet("font-weight: bold; color: #27AE60;")
        layout.addWidget(self.devices_label, 3, 1)

        # 连接时长
        layout.addWidget(QLabel("连接时长:"), 4, 0)
        self.duration_label = QLabel("--")
        layout.addWidget(self.duration_label, 4, 1)

        return group

    def create_log_group(self):
        """创建日志组"""
        group = QGroupBox("连接日志")
        layout = QVBoxLayout(group)

        # 日志控制
        log_controls = QHBoxLayout()

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear_log)
        clear_btn.setMaximumWidth(60)
        log_controls.addWidget(clear_btn)
        log_controls.addStretch()

        layout.addLayout(log_controls)

        # 日志显示
        self.log_display = QTextEdit()
        self.log_display.setFont(QFont("Consolas", 9))
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)

        return group

    def create_buttons(self):
        """创建按钮"""
        layout = QHBoxLayout()

        # 连接/断开按钮
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.connect_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #27AE60; color: white; 
                font-weight: bold; padding: 8px 16px;
                border-radius: 4px; border: none;
            }
            QPushButton:hover { background-color: #229954; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """
        )

        # 保存配置按钮
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)

        layout.addWidget(self.connect_btn)
        layout.addStretch()
        layout.addWidget(self.save_btn)
        layout.addWidget(close_btn)

        return layout

    def setup_connections(self):
        """设置MQTT连接监听"""
        try:
            # MQTT管理器信号
            self.mqtt_manager.connection_changed.connect(
                self.on_connection_changed, Qt.QueuedConnection
            )
            self.mqtt_manager.statistics_updated.connect(
                self.on_statistics_updated, Qt.QueuedConnection
            )
            # mqtt_manager.device_discovered.connect(
            #     self.on_device_discovered, Qt.QueuedConnection
            # )

            # DataBus监听
            try:
                from core.data_bus import data_bus, DataChannel

                # 添加直接的调试监听器
                def debug_telemetry_handler(message):
                    try:
                        from core.data_bus import DataMessage

                        if isinstance(message, DataMessage):
                            device_id = message.device_id
                            data = message.data
                            self.add_log(f"🔍 直接收到遥测数据: {device_id}")
                            self.add_log(
                                f"  数据类型: {data.get('device_type', 'UNKNOWN')}"
                            )
                            self.add_log(f"  批次大小: {data.get('batch_size', 1)}")
                    except Exception as e:
                        self.add_log(f"处理调试数据失败: {e}")

                def debug_error_handler(message):
                    try:
                        from core.data_bus import DataMessage

                        if isinstance(message, DataMessage):
                            error_data = message.data
                            device_id = message.device_id or "unknown"
                            error_msg = error_data.get("error", "未知错误")
                            self.add_log(f"🚨 直接收到错误: {device_id} | {error_msg}")
                    except Exception as e:
                        self.add_log(f"处理调试错误失败: {e}")

                data_bus.subscribe(DataChannel.TELEMETRY_DATA, debug_telemetry_handler)
                data_bus.subscribe(DataChannel.ERRORS, debug_error_handler)
            except Exception as e:
                self.logger.warning(f"DataBus连接失败: {e}")

            self.add_log("监听连接已设置")

        except Exception as e:
            self.logger.error(f"设置连接监听失败: {e}")

    def load_config(self):
        """加载配置"""
        config = self.current_config
        self.host_edit.setText(config.host)
        self.port_spinbox.setValue(config.port)
        self.username_edit.setText(config.username)
        self.password_edit.setText(config.password)
        self.server_label.setText(f"{config.host}:{config.port}")

        topics = getattr(
            config, "subscribe_topics", ["factory/telemetry/+/+/msgpack", "gateway/+/+"]
        )
        # 分离设备主题和网关主题
        device_topics = [t for t in topics if t.startswith("factory/telemetry")]
        gateway_topics = [t for t in topics if t.startswith("gateway")]

        self.device_topic_edit.setText(
            device_topics[0] if device_topics else "factory/telemetry/+/+"
        )
        self.gateway_topic_edit.setText(
            gateway_topics[0] if gateway_topics else "gateway/+/+"
        )

        self._config_modified = False

    def get_config(self) -> MqttConfig:
        """获取当前配置"""
        subscribe_topics = []

        # 设备主题
        device_topic = self.device_topic_edit.text().strip()
        if device_topic:
            subscribe_topics.append(device_topic)

        # 网关主题
        gateway_topic = self.gateway_topic_edit.text().strip()
        if gateway_topic:
            subscribe_topics.append(gateway_topic)

        # 如果都为空，使用默认主题
        if not subscribe_topics:
            subscribe_topics = ["factory/telemetry/+/+/msgpack", "gateway/+/+"]
        return MqttConfig(
            host=self.host_edit.text().strip() or "localhost",
            port=self.port_spinbox.value(),
            username=self.username_edit.text().strip(),
            password=self.password_edit.text().strip(),
            client_id=f"chipmonitor_{datetime.now().strftime('%H%M%S')}",
            keepalive=60,
            timeout=30,
            subscribe_topics=subscribe_topics,
        )

    @Slot()
    def toggle_connection(self):
        """切换连接状态"""
        try:
            if not self.mqtt_manager.connected:
                # 连接
                config = self.get_config()
                self.add_log(f"正在连接: {config.host}:{config.port}")
                self.connect_btn.setEnabled(False)

                success = self.mqtt_manager.connect(
                    host=config.host,
                    port=config.port,
                    username=config.username,
                    password=config.password,
                )

                if not success:
                    self.add_log("连接请求失败")
                    self.connect_btn.setEnabled(True)
            else:
                # 断开
                self.mqtt_manager.disconnect()
                self.add_log("断开连接")

        except Exception as e:
            self.add_log(f"连接操作失败: {e}")
            self.connect_btn.setEnabled(True)

    @Slot()
    def save_config(self):
        """保存配置"""
        try:
            config = self.get_config()
            success = save_config(config)

            if success:
                self.current_config = config
                self._config_modified = False
                self.save_btn.setText("保存配置")
                self.save_btn.setStyleSheet("")
                self.add_log("✅ 配置已保存")
                self.config_changed.emit(config.__dict__)
            else:
                self.add_log("❌ 配置保存失败")

        except Exception as e:
            self.add_log(f"保存配置失败: {e}")

    @Slot()
    def clear_log(self):
        """清空日志"""
        self.log_display.clear()

    def mark_modified(self):
        """标记配置已修改"""
        if not self._config_modified:
            self._config_modified = True
            self.save_btn.setText("保存配置*")
            self.save_btn.setStyleSheet("background-color: #F39C12; color: white;")

    def update_status(self):
        """更新状态显示"""
        try:
            # 更新统计数字
            self.messages_label.setText(str(self.stats["messages"]))
            self.devices_label.setText(str(len(self.online_devices)))

            # 更新连接时长
            if self.stats["connected_time"]:
                duration = datetime.now() - self.stats["connected_time"]
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                self.duration_label.setText(f"{hours:02d}:{minutes:02d}")
            else:
                self.duration_label.setText("--")

        except Exception as e:
            self.logger.error(f"更新状态失败: {e}")

    # === MQTT信号处理 ===

    @Slot(bool, str)
    def on_connection_changed(self, connected, message):
        """连接状态变化"""
        if connected:
            self.status_label.setText("已连接")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("断开")
            self.connect_btn.setEnabled(True)
            self.stats["connected_time"] = datetime.now()

            # 订阅主题
            config = self.get_config()
            subscription_success = []
            for topic in config.subscribe_topics:
                success = self.mqtt_manager.subscribe_topic(topic)
                subscription_success.append((topic, success))
                if success:
                    self.add_log(f"✅ 订阅成功: {topic}")
                else:
                    self.add_log(f"❌ 订阅失败: {topic}")
            # 统计订阅结果
            total_topics = len(config.subscribe_topics)
            successful_topics = sum(1 for _, success in subscription_success if success)
            self.add_log(f"主题订阅完成: {successful_topics}/{total_topics}")
        else:
            self.status_label.setText("未连接")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setText("连接")
            self.connect_btn.setEnabled(True)
            self.stats["connected_time"] = None

        self.add_log(f"连接: {message}")

    @Slot(dict)
    def on_statistics_updated(self, stats):
        """统计信息更新"""
        self.stats["messages"] = stats.get("messages_received", 0)

    @Slot(str, dict)
    def on_device_discovered(self, device_id, device_info):
        """设备发现"""
        self.online_devices.add(device_id)
        device_type = device_info.get("device_type", "")
        self.add_log(f"🔍 发现设备: {device_id} [{device_type}]")

    # === DataBus处理 ===

    def on_data_received(self, message):
        """处理遥测数据"""
        try:
            from core.data_bus import DataMessage

            if isinstance(message, DataMessage):
                device_id = message.device_id
                if device_id:
                    self.online_devices.add(device_id)

                data = message.data
                batch_size = data.get("batch_size", 1)
                self.stats["messages"] += batch_size

        except Exception as e:
            self.logger.error(f"处理数据失败: {e}")

    def on_error_received(self, message):
        """处理错误信息"""
        try:
            from core.data_bus import DataMessage

            if isinstance(message, DataMessage):
                error_data = message.data
                device_id = message.device_id or "unknown"
                error_msg = error_data.get("error", "未知错误")

                # 过滤网关消息错误
                if "未知content_type" in error_msg and "gateway" in device_id.lower():
                    return  # 忽略网关消息的格式"错误"

                self.add_log(f"❌ 错误: {device_id} | {error_msg}")

        except Exception as e:
            self.logger.error(f"处理错误失败: {e}")

    def on_device_events(self, message):
        """处理设备事件"""
        try:
            from core.data_bus import DataMessage

            if isinstance(message, DataMessage):
                event_data = message.data
                event_type = event_data.get(
                    "message_type", event_data.get("event_type")
                )

                if event_type == "gateway_message":
                    gateway_id = message.device_id
                    function = event_data.get("function", "")
                    self.add_log(f"🌐 网关: {gateway_id}/{function}")

        except Exception as e:
            self.logger.error(f"处理设备事件失败: {e}")

    def add_log(self, message):
        """添加日志"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_line = f"[{timestamp}] {message}"
            self.log_display.append(log_line)

            # 保持日志行数限制
            if self.log_display.document().blockCount() > 50:
                cursor = self.log_display.textCursor()
                cursor.movePosition(cursor.Start)
                cursor.select(cursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()  # 删除换行符

        except Exception as e:
            self.logger.error(f"添加日志失败: {e}")

    def closeEvent(self, event):
        """关闭事件"""
        try:
            self.update_timer.stop()
            self.logger.info("网络控制面板已关闭")
        except Exception as e:
            self.logger.error(f"关闭失败: {e}")
        finally:
            event.accept()
