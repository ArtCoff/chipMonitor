import time
import time
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QGroupBox,
    QFrame,
    QSplitter,
    QScrollArea,
    QTabWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QSpinBox,
    QProgressBar,
    QSlider,
    QCheckBox,
    QRadioButton,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QLCDNumber,
    QDateTimeEdit,
    QTimeEdit,
    QButtonGroup,
    QSpacerItem,
    QSizePolicy,
    QMessageBox,
    QToolButton,
    QMenu,
)
from PySide6.QtCore import (
    Qt,
    QTimer,
    QDateTime,
    QThread,
    QObject,
    Signal,
    Slot,
    QSize,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
)
from PySide6.QtGui import (
    QFont,
    QColor,
    QPalette,
    QPixmap,
    QIcon,
    QPainter,
    QLinearGradient,
    QBrush,
    QPen,
    QMovie,
    QAction,
)
from ..ETL.mqttETL import MqttEtlWorker
from ..threads.sysmonitoring import SystemMonitorWorker


class DeviceStatusWidget(QWidget):
    """设备状态显示组件"""

    device_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices = {}  # 设备状态数据
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # 标题
        title_label = QLabel("在线设备")
        title_label.setObjectName("deviceTitle")
        title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 设备列表
        self.device_list = QListWidget()
        self.device_list.setObjectName("deviceList")
        self.device_list.setMaximumHeight(200)
        self.device_list.itemClicked.connect(self.on_device_selected)
        layout.addWidget(self.device_list)

        # 设备详情
        self.device_detail = QTextEdit()
        self.device_detail.setObjectName("deviceDetail")
        self.device_detail.setMaximumHeight(150)
        self.device_detail.setReadOnly(True)
        self.device_detail.setFont(QFont("Consolas", 9))
        layout.addWidget(QLabel("设备详情:"))
        layout.addWidget(self.device_detail)

        # 统计信息
        stats_group = QGroupBox("设备统计")
        stats_layout = QFormLayout(stats_group)

        self.total_devices_label = QLabel("0")
        self.online_devices_label = QLabel("0")
        self.offline_devices_label = QLabel("0")

        # 设置对象名用于样式
        self.total_devices_label.setObjectName("statsLabel")
        self.online_devices_label.setObjectName("statsLabel")
        self.offline_devices_label.setObjectName("statsLabel")

        stats_layout.addRow("总设备数:", self.total_devices_label)
        stats_layout.addRow("在线设备:", self.online_devices_label)
        stats_layout.addRow("离线设备:", self.offline_devices_label)

        layout.addWidget(stats_group)
        layout.addStretch()

    def update_device_status(self, device_stats: Dict):
        """更新设备状态"""
        self.devices = device_stats
        self.device_list.clear()

        online_count = 0
        offline_count = 0

        for device_key, stats in device_stats.items():
            item = QListWidgetItem()

            # 检查设备是否在线（最后更新时间在30秒内）
            last_seen = stats.get("last_seen")
            is_online = False
            if last_seen:
                time_diff = (datetime.now() - last_seen).total_seconds()
                is_online = time_diff < 30

            if is_online:
                online_count += 1
                item.setText(f"🟢 {device_key}")
                item.setBackground(QColor("#e8f5e8"))
            else:
                offline_count += 1
                item.setText(f"🔴 {device_key}")
                item.setBackground(QColor("#ffeaea"))

            item.setData(Qt.UserRole, device_key)
            self.device_list.addItem(item)

        # 更新统计
        self.total_devices_label.setText(str(len(device_stats)))
        self.online_devices_label.setText(str(online_count))
        self.offline_devices_label.setText(str(offline_count))

    def on_device_selected(self, item):
        """设备选择事件"""
        device_key = item.data(Qt.UserRole)
        if device_key in self.devices:
            stats = self.devices[device_key]

            # 格式化设备详情
            detail_text = f"""设备ID: {device_key}
                            设备类型: {stats.get('device_type', 'Unknown')}
                            消息数量: {stats.get('message_count', 0)}
                            数据记录: {stats.get('record_count', 0)}
                            批次数量: {stats.get('batch_count', 0)}
                            平均批次大小: {stats.get('avg_batch_size', 0):.1f}
                            数据总量: {self.format_bytes(stats.get('data_size', 0))}
                            最后更新: {stats.get('last_seen', 'Unknown')}
                            """
            self.device_detail.setPlainText(detail_text)
            self.device_selected.emit(device_key)

    def format_bytes(self, bytes_count):
        """格式化字节数"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} TB"


class ConnectionControlWidget(QWidget):
    """连接控制组件"""

    connection_requested = Signal(dict)
    disconnection_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_connected = False
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 连接配置组
        config_group = QGroupBox("连接配置")
        config_layout = QFormLayout(config_group)

        # MQTT服务器配置
        self.broker_input = QLineEdit("localhost")
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1, 65535)
        self.port_spinbox.setValue(1883)

        config_layout.addRow("MQTT服务器:", self.broker_input)
        config_layout.addRow("端口:", self.port_spinbox)

        # 认证配置
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)

        config_layout.addRow("用户名:", self.username_input)
        config_layout.addRow("密码:", self.password_input)

        # 订阅主题
        self.topic_input = QLineEdit("factory/telemetry/#")
        config_layout.addRow("订阅主题:", self.topic_input)

        layout.addWidget(config_group)

        # 连接控制按钮
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("连接")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.clicked.connect(self.on_connect_clicked)

        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.setObjectName("disconnectBtn")
        self.disconnect_btn.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_btn.setEnabled(False)

        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.disconnect_btn)

        layout.addLayout(button_layout)

        # 连接状态显示
        status_group = QGroupBox("连接状态")
        status_layout = QFormLayout(status_group)

        self.status_label = QLabel("未连接")
        self.status_label.setObjectName("statusDisconnected")

        self.uptime_label = QLabel("00:00:00")
        self.message_count_label = QLabel("0")

        status_layout.addRow("状态:", self.status_label)
        status_layout.addRow("运行时间:", self.uptime_label)
        status_layout.addRow("消息数:", self.message_count_label)

        layout.addWidget(status_group)

    def on_connect_clicked(self):
        """连接按钮点击"""
        config = {
            "broker": self.broker_input.text().strip(),
            "port": self.port_spinbox.value(),
            "username": self.username_input.text().strip() or None,
            "password": self.password_input.text().strip() or None,
            "topic": self.topic_input.text().strip(),
        }

        if not config["broker"]:
            QMessageBox.warning(self, "错误", "请输入MQTT服务器地址")
            return

        self.connection_requested.emit(config)

    def on_disconnect_clicked(self):
        """断开按钮点击"""
        self.disconnection_requested.emit()

    def update_connection_status(self, connected: bool, message: str = ""):
        """更新连接状态"""
        self.is_connected = connected

        if connected:
            self.status_label.setText("已连接")
            self.status_label.setObjectName("statusConnected")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
        else:
            self.status_label.setText("未连接")
            self.status_label.setObjectName("statusDisconnected")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)

        # 重新应用样式
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def update_statistics(self, stats: Dict):
        """更新统计信息"""
        if "elapsed_time" in stats:
            elapsed = stats["elapsed_time"]
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        if "total_messages" in stats:
            self.message_count_label.setText(str(stats["total_messages"]))


class SystemResourceWidget(QWidget):
    """系统资源监控组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cpu_history = deque(maxlen=60)  # 保存60秒历史
        self.memory_history = deque(maxlen=60)
        self.network_history = deque(maxlen=60)
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # CPU监控
        cpu_group = QGroupBox("CPU使用率")
        cpu_layout = QVBoxLayout(cpu_group)

        self.cpu_progress = QProgressBar()
        self.cpu_progress.setObjectName("cpuProgress")
        self.cpu_progress.setRange(0, 100)

        self.cpu_label = QLabel("0% (0 cores)")
        self.cpu_label.setObjectName("cpuLabel")
        self.cpu_label.setAlignment(Qt.AlignCenter)

        cpu_layout.addWidget(self.cpu_progress)
        cpu_layout.addWidget(self.cpu_label)

        layout.addWidget(cpu_group)

        # 内存监控
        memory_group = QGroupBox("内存使用")
        memory_layout = QVBoxLayout(memory_group)

        self.memory_progress = QProgressBar()
        self.memory_progress.setObjectName("memoryProgress")
        self.memory_progress.setRange(0, 100)

        self.memory_label = QLabel("0 MB / 0 MB")
        self.memory_label.setObjectName("memoryLabel")
        self.memory_label.setAlignment(Qt.AlignCenter)

        memory_layout.addWidget(self.memory_progress)
        memory_layout.addWidget(self.memory_label)

        layout.addWidget(memory_group)

        # 磁盘监控
        disk_group = QGroupBox("磁盘使用")
        disk_layout = QVBoxLayout(disk_group)

        self.disk_progress = QProgressBar()
        self.disk_progress.setObjectName("diskProgress")
        self.disk_progress.setRange(0, 100)

        self.disk_label = QLabel("0 GB / 0 GB")
        self.disk_label.setObjectName("diskLabel")
        self.disk_label.setAlignment(Qt.AlignCenter)

        disk_layout.addWidget(self.disk_progress)
        disk_layout.addWidget(self.disk_label)

        layout.addWidget(disk_group)

        # 网络监控
        network_group = QGroupBox("网络流量")
        network_layout = QFormLayout(network_group)

        self.network_sent_label = QLabel("0 MB")
        self.network_recv_label = QLabel("0 MB")
        self.network_speed_label = QLabel("0 KB/s")

        network_layout.addRow("发送:", self.network_sent_label)
        network_layout.addRow("接收:", self.network_recv_label)
        network_layout.addRow("速度:", self.network_speed_label)

        layout.addWidget(network_group)
        layout.addStretch()

    def update_system_stats(self, stats: Dict):
        """更新系统统计"""
        # CPU
        cpu_percent = stats.get("cpu_percent", 0)
        cpu_count = stats.get("cpu_count", 0)
        self.cpu_progress.setValue(int(cpu_percent))
        self.cpu_label.setText(f"{cpu_percent:.1f}% ({cpu_count} cores)")

        # 内存
        memory_used = stats.get("memory_used", 0)
        memory_total = stats.get("memory_total", 1)
        memory_percent = stats.get("memory_percent", 0)

        self.memory_progress.setValue(int(memory_percent))
        self.memory_label.setText(
            f"{self.format_bytes(memory_used)} / {self.format_bytes(memory_total)}"
        )

        # 磁盘
        disk_used = stats.get("disk_used", 0)
        disk_total = stats.get("disk_total", 1)
        disk_percent = stats.get("disk_percent", 0)

        self.disk_progress.setValue(int(disk_percent))
        self.disk_label.setText(
            f"{self.format_bytes(disk_used)} / {self.format_bytes(disk_total)}"
        )

        # 保存历史数据
        self.cpu_history.append(cpu_percent)
        self.memory_history.append(memory_percent)

    def update_network_stats(self, stats: Dict):
        """更新网络统计"""
        bytes_sent = stats.get("bytes_sent", 0)
        bytes_recv = stats.get("bytes_recv", 0)

        self.network_sent_label.setText(self.format_bytes(bytes_sent))
        self.network_recv_label.setText(self.format_bytes(bytes_recv))

        # 计算网络速度（简单实现）
        current_time = time.time()
        if hasattr(self, "_last_network_time"):
            time_diff = current_time - self._last_network_time
            if time_diff > 0:
                sent_diff = bytes_sent - getattr(self, "_last_bytes_sent", 0)
                speed = sent_diff / time_diff
                self.network_speed_label.setText(f"{self.format_bytes(speed)}/s")

        self._last_network_time = current_time
        self._last_bytes_sent = bytes_sent

    def format_bytes(self, bytes_count):
        """格式化字节数"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} TB"


class EtlConfigWidget(QWidget):
    """ETL配置组件"""

    etl_start_requested = Signal(dict)
    etl_stop_requested = Signal()
    etl_reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 数据处理配置
        processing_group = QGroupBox("数据处理配置")
        processing_layout = QFormLayout(processing_group)

        self.batch_size_spinbox = QSpinBox()
        self.batch_size_spinbox.setRange(1, 10000)
        self.batch_size_spinbox.setValue(100)

        self.processing_interval_spinbox = QSpinBox()
        self.processing_interval_spinbox.setRange(1, 3600)
        self.processing_interval_spinbox.setValue(5)
        self.processing_interval_spinbox.setSuffix(" 秒")

        self.enable_filtering_check = QCheckBox("启用数据过滤")
        self.enable_aggregation_check = QCheckBox("启用数据聚合")

        processing_layout.addRow("批处理大小:", self.batch_size_spinbox)
        processing_layout.addRow("处理间隔:", self.processing_interval_spinbox)
        processing_layout.addRow(self.enable_filtering_check)
        processing_layout.addRow(self.enable_aggregation_check)

        layout.addWidget(processing_group)

        # 数据存储配置
        storage_group = QGroupBox("数据存储配置")
        storage_layout = QFormLayout(storage_group)

        self.storage_type_combo = QComboBox()
        self.storage_type_combo.addItems(
            ["SQLite", "PostgreSQL", "InfluxDB", "文件存储"]
        )

        self.storage_path_input = QLineEdit()
        self.storage_path_input.setPlaceholderText("数据库连接字符串或文件路径")

        self.retention_days_spinbox = QSpinBox()
        self.retention_days_spinbox.setRange(1, 3650)
        self.retention_days_spinbox.setValue(30)
        self.retention_days_spinbox.setSuffix(" 天")

        storage_layout.addRow("存储类型:", self.storage_type_combo)
        storage_layout.addRow("存储路径:", self.storage_path_input)
        storage_layout.addRow("数据保留期:", self.retention_days_spinbox)

        layout.addWidget(storage_group)

        # ETL状态监控
        status_group = QGroupBox("ETL状态")
        status_layout = QFormLayout(status_group)

        self.etl_status_label = QLabel("停止")
        self.etl_status_label.setObjectName("etlStatusStopped")

        self.processed_records_label = QLabel("0")
        self.error_count_label = QLabel("0")
        self.last_process_time_label = QLabel("从未")

        status_layout.addRow("处理状态:", self.etl_status_label)
        status_layout.addRow("已处理记录:", self.processed_records_label)
        status_layout.addRow("错误次数:", self.error_count_label)
        status_layout.addRow("最后处理:", self.last_process_time_label)

        layout.addWidget(status_group)

        # 控制按钮
        button_layout = QHBoxLayout()

        self.start_etl_btn = QPushButton("启动ETL")
        self.start_etl_btn.setObjectName("startEtlBtn")
        self.start_etl_btn.clicked.connect(self.on_start_etl)

        self.stop_etl_btn = QPushButton("停止ETL")
        self.stop_etl_btn.setObjectName("stopEtlBtn")
        self.stop_etl_btn.clicked.connect(self.on_stop_etl)
        self.stop_etl_btn.setEnabled(False)

        self.reset_etl_btn = QPushButton("重置")
        self.reset_etl_btn.clicked.connect(self.on_reset_etl)

        button_layout.addWidget(self.start_etl_btn)
        button_layout.addWidget(self.stop_etl_btn)
        button_layout.addWidget(self.reset_etl_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

    def on_start_etl(self):
        """启动ETL"""
        config = {
            "batch_size": self.batch_size_spinbox.value(),
            "interval": self.processing_interval_spinbox.value(),
            "enable_filtering": self.enable_filtering_check.isChecked(),
            "enable_aggregation": self.enable_aggregation_check.isChecked(),
            "storage_type": self.storage_type_combo.currentText(),
            "storage_path": self.storage_path_input.text().strip(),
            "retention_days": self.retention_days_spinbox.value(),
        }
        self.etl_start_requested.emit(config)

    def on_stop_etl(self):
        """停止ETL"""
        self.etl_stop_requested.emit()

    def on_reset_etl(self):
        """重置ETL"""
        self.etl_reset_requested.emit()

    def update_etl_status(self, running: bool, stats: Dict = None):
        """更新ETL状态"""
        if running:
            self.etl_status_label.setText("运行中")
            self.etl_status_label.setObjectName("etlStatusRunning")
            self.start_etl_btn.setEnabled(False)
            self.stop_etl_btn.setEnabled(True)
        else:
            self.etl_status_label.setText("停止")
            self.etl_status_label.setObjectName("etlStatusStopped")
            self.start_etl_btn.setEnabled(True)
            self.stop_etl_btn.setEnabled(False)

        # 重新应用样式
        self.etl_status_label.style().unpolish(self.etl_status_label)
        self.etl_status_label.style().polish(self.etl_status_label)

        if stats:
            self.processed_records_label.setText(str(stats.get("processed_records", 0)))
            self.error_count_label.setText(str(stats.get("error_count", 0)))
            last_process = stats.get("last_process_time")
            if last_process:
                self.last_process_time_label.setText(last_process.strftime("%H:%M:%S"))


class EtlControlPanel(QWidget):
    """数据ETL控制面板主组件"""

    # 信号定义
    connection_requested = Signal(dict)
    disconnection_requested = Signal()
    device_selected = Signal(str)
    etl_config_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_workers()

        # 数据存储
        self.device_stats = {}
        self.mqtt_stats = {}

    def setup_ui(self):
        """设置用户界面"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 左侧设备面板（竖向布局）
        device_frame = QFrame()
        device_frame.setObjectName("deviceFrame")
        device_frame.setFrameStyle(QFrame.StyledPanel)
        device_frame.setMaximumWidth(300)
        device_frame.setMinimumWidth(280)

        device_layout = QVBoxLayout(device_frame)

        # 设备状态组件
        self.device_widget = DeviceStatusWidget()
        self.device_widget.device_selected.connect(self.device_selected.emit)
        device_layout.addWidget(self.device_widget)

        main_layout.addWidget(device_frame)

        # 右侧控制面板
        control_frame = QFrame()
        control_frame.setObjectName("controlFrame")
        control_frame.setFrameStyle(QFrame.StyledPanel)

        control_layout = QVBoxLayout(control_frame)

        # 创建标签页
        tab_widget = QTabWidget()
        tab_widget.setObjectName("mainTabWidget")

        # 连接控制标签页
        self.connection_widget = ConnectionControlWidget()
        self.connection_widget.connection_requested.connect(
            self.connection_requested.emit
        )
        self.connection_widget.disconnection_requested.connect(
            self.disconnection_requested.emit
        )
        tab_widget.addTab(self.connection_widget, "连接控制")

        # 系统资源标签页
        self.resource_widget = SystemResourceWidget()
        tab_widget.addTab(self.resource_widget, "系统资源")

        # 网络配置标签页
        network_config_widget = self.create_network_config_widget()
        tab_widget.addTab(network_config_widget, "网络配置")

        # ETL配置标签页
        self.etl_widget = EtlConfigWidget()
        self.etl_widget.etl_start_requested.connect(self.on_etl_start_requested)
        self.etl_widget.etl_stop_requested.connect(self.on_etl_stop_requested)
        self.etl_widget.etl_reset_requested.connect(self.on_etl_reset_requested)
        tab_widget.addTab(self.etl_widget, "ETL配置")

        control_layout.addWidget(tab_widget)

        main_layout.addWidget(control_frame)

        # 设置主布局比例
        main_layout.setStretchFactor(0, 1)  # 设备面板
        main_layout.setStretchFactor(1, 2)  # 控制面板

    def create_network_config_widget(self):
        """创建网络配置组件"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 网络接口信息
        interface_group = QGroupBox("网络接口信息")
        interface_layout = QFormLayout(interface_group)

        self.interface_name_label = QLabel("未知")
        self.ip_address_label = QLabel("未知")
        self.mac_address_label = QLabel("未知")
        self.network_status_label = QLabel("未知")

        interface_layout.addRow("接口名称:", self.interface_name_label)
        interface_layout.addRow("IP地址:", self.ip_address_label)
        interface_layout.addRow("MAC地址:", self.mac_address_label)
        interface_layout.addRow("连接状态:", self.network_status_label)

        layout.addWidget(interface_group)

        # 网络质量监控
        quality_group = QGroupBox("网络质量")
        quality_layout = QFormLayout(quality_group)

        self.ping_label = QLabel("-- ms")
        self.packet_loss_label = QLabel("-- %")
        self.bandwidth_label = QLabel("-- Mbps")

        quality_layout.addRow("延迟:", self.ping_label)
        quality_layout.addRow("丢包率:", self.packet_loss_label)
        quality_layout.addRow("带宽:", self.bandwidth_label)

        layout.addWidget(quality_group)

        # 网络测试
        test_group = QGroupBox("网络测试")
        test_layout = QVBoxLayout(test_group)

        test_button_layout = QHBoxLayout()
        ping_test_btn = QPushButton("Ping测试")
        speed_test_btn = QPushButton("速度测试")

        test_button_layout.addWidget(ping_test_btn)
        test_button_layout.addWidget(speed_test_btn)

        self.test_result_text = QTextEdit()
        self.test_result_text.setMaximumHeight(100)
        self.test_result_text.setReadOnly(True)

        test_layout.addLayout(test_button_layout)
        test_layout.addWidget(self.test_result_text)

        layout.addWidget(test_group)
        layout.addStretch()

        return widget

    def setup_workers(self):
        """设置工作线程"""
        # 系统监控工作线程
        self.monitor_thread = QThread()
        self.monitor_worker = SystemMonitorWorker()
        self.monitor_worker.moveToThread(self.monitor_thread)

        # 连接系统监控信号
        self.monitor_worker.system_stats_updated.connect(
            self.resource_widget.update_system_stats
        )
        self.monitor_worker.network_stats_updated.connect(
            self.resource_widget.update_network_stats
        )

        # 启动系统监控
        self.monitor_thread.started.connect(self.monitor_worker.start_monitoring)
        self.monitor_thread.start()

        # MQTT ETL工作线程
        self.etl_thread = QThread()
        self.etl_worker = MqttEtlWorker()
        self.etl_worker.moveToThread(self.etl_thread)

        # 连接ETL信号
        self.etl_worker.device_stats_updated.connect(self.update_device_stats)
        self.etl_worker.connection_status_changed.connect(self.update_connection_status)
        self.etl_worker.mqtt_stats_updated.connect(self.update_mqtt_stats)
        self.etl_worker.etl_status_changed.connect(self.etl_widget.update_etl_status)

        # 启动ETL线程
        self.etl_thread.start()

    def on_etl_start_requested(self, config: dict):
        """ETL启动请求"""
        if self.etl_worker:
            self.etl_worker.start_etl_processing(config)

    def on_etl_stop_requested(self):
        """ETL停止请求"""
        if self.etl_worker:
            self.etl_worker.stop_etl_processing()

    def on_etl_reset_requested(self):
        """ETL重置请求"""
        if self.etl_worker:
            self.etl_worker.reset_etl_stats()

    def update_device_stats(self, device_stats: Dict):
        """更新设备统计"""
        self.device_stats = device_stats
        self.device_widget.update_device_status(device_stats)

    def update_connection_status(self, connected: bool, message: str = ""):
        """更新连接状态"""
        self.connection_widget.update_connection_status(connected, message)

    def update_mqtt_stats(self, stats: Dict):
        """更新MQTT统计"""
        self.mqtt_stats = stats
        self.connection_widget.update_statistics(stats)

    def start_mqtt_connection(self, config: dict):
        """启动MQTT连接"""
        if self.etl_worker:
            self.etl_worker.start_mqtt_connection(config)

    def stop_mqtt_connection(self):
        """停止MQTT连接"""
        if self.etl_worker:
            self.etl_worker.stop_mqtt_connection()

    def closeEvent(self, event):
        """关闭事件"""
        # 停止系统监控
        if hasattr(self, "monitor_thread"):
            self.monitor_worker.stop_monitoring()
            self.monitor_thread.quit()
            self.monitor_thread.wait(2000)

        # 停止ETL处理
        if hasattr(self, "etl_thread"):
            self.etl_worker.stop_all()
            self.etl_thread.quit()
            self.etl_thread.wait(3000)

        event.accept()


# 导出主要组件
__all__ = [
    "EtlControlPanel",
    "DeviceStatusWidget",
    "ConnectionControlWidget",
    "SystemResourceWidget",
    "EtlConfigWidget",
]
