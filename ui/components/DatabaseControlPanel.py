import logging
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGridLayout,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QLabel,
    QGroupBox,
    QTabWidget,
    QWidget,
    QTextEdit,
    QProgressBar,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QPixmap, QIcon, QTextCursor
from config.database_config import database_config, DatabaseConfig, DatabaseStats
from core.database_manager import get_db_manager
from utils.path import ICON_DIR


class DatabaseControlPanel(QDialog):
    """数据库控制面板 - 修复版本"""

    # 信号定义
    config_changed = Signal(object)  # 配置变更信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DatabaseControlPanel")
        self.db_manager = get_db_manager()

        # 窗口设置
        self.setWindowTitle("数据库管理")
        self.setWindowIcon(QIcon(f"{ICON_DIR}/icon_database.png"))
        self.resize(600, 500)
        self.setModal(False)

        # 当前配置
        self.current_config = DatabaseConfig.from_dict(database_config.to_dict())

        # 统计数据
        self.current_stats = DatabaseStats()

        # 初始化UI
        self.setup_ui()
        self.load_current_config()
        self.setup_connections()

        # 定时更新统计
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(5000)  # 5秒更新一次

    def setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 创建标签页
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 1. 连接配置标签页
        self.setup_connection_tab()

        # 2. 统计信息标签页
        self.setup_statistics_tab()

        # 底部按钮
        self.setup_buttons()

    def setup_connection_tab(self):
        """设置连接配置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 🔥 连接配置组
        config_group = QGroupBox("数据库连接配置")
        config_layout = QFormLayout(config_group)

        # 主机地址
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("localhost")
        config_layout.addRow("主机地址:", self.host_edit)

        # 端口
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(5435)
        config_layout.addRow("端口:", self.port_spin)

        # 数据库名
        self.database_edit = QLineEdit()
        self.database_edit.setPlaceholderText("semiconductor_db")
        config_layout.addRow("数据库名:", self.database_edit)

        # 用户名
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("app_user")
        config_layout.addRow("用户名:", self.username_edit)

        # 密码
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("app_pass")
        config_layout.addRow("密码:", self.password_edit)

        layout.addWidget(config_group)

        # 🔥 高级配置组
        advanced_group = QGroupBox("高级配置")
        advanced_layout = QFormLayout(advanced_group)

        # 连接超时
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 60)
        self.timeout_spin.setValue(10)
        self.timeout_spin.setSuffix(" 秒")
        advanced_layout.addRow("连接超时:", self.timeout_spin)

        # 最大连接数
        self.max_conn_spin = QSpinBox()
        self.max_conn_spin.setRange(5, 100)
        self.max_conn_spin.setValue(20)
        advanced_layout.addRow("最大连接数:", self.max_conn_spin)

        # 批量大小
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(100, 2000)
        self.batch_size_spin.setValue(500)
        advanced_layout.addRow("批量大小:", self.batch_size_spin)

        layout.addWidget(advanced_group)

        # 🔥 连接状态组
        status_group = QGroupBox("连接状态")
        status_layout = QVBoxLayout(status_group)

        # 状态显示
        self.connection_status = QLabel("● 未连接")
        self.connection_status.setStyleSheet(
            "color: red; font-weight: bold; font-size: 14px;"
        )
        status_layout.addWidget(self.connection_status)

        # 连接信息
        self.connection_info = QLabel("等待连接...")
        self.connection_info.setWordWrap(True)
        status_layout.addWidget(self.connection_info)

        # 操作按钮
        button_layout = QHBoxLayout()

        self.test_button = QPushButton("测试连接")
        self.test_button.setIcon(QIcon(":/icons/test.png"))
        button_layout.addWidget(self.test_button)

        self.connect_button = QPushButton("连接")
        self.connect_button.setIcon(QIcon(":/icons/connect.png"))
        button_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.setIcon(QIcon(":/icons/disconnect.png"))
        self.disconnect_button.setEnabled(False)
        button_layout.addWidget(self.disconnect_button)

        status_layout.addLayout(button_layout)
        layout.addWidget(status_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "连接配置")

    def setup_statistics_tab(self):
        """设置统计信息标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 🔥 数据统计组
        stats_group = QGroupBox("数据统计")
        stats_layout = QGridLayout(stats_group)

        # 统计标签
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)

        self.telemetry_label = QLabel("遥测数据: 0 条")
        self.telemetry_label.setFont(font)
        self.telemetry_label.setStyleSheet("color: #3498DB;")
        stats_layout.addWidget(self.telemetry_label, 0, 0)

        self.alerts_label = QLabel("告警数据: 0 条")
        self.alerts_label.setFont(font)
        self.alerts_label.setStyleSheet("color: #E74C3C;")
        stats_layout.addWidget(self.alerts_label, 0, 1)

        self.events_label = QLabel("事件数据: 0 条")
        self.events_label.setFont(font)
        self.events_label.setStyleSheet("color: #F39C12;")
        stats_layout.addWidget(self.events_label, 1, 0)

        self.total_label = QLabel("总记录数: 0 条")
        self.total_label.setFont(font)
        self.total_label.setStyleSheet("color: #27AE60;")
        stats_layout.addWidget(self.total_label, 1, 1)

        # 数据库大小
        self.size_label = QLabel("数据库大小: 0 MB")
        self.size_label.setFont(font)
        self.size_label.setStyleSheet("color: #9B59B6;")
        stats_layout.addWidget(self.size_label, 2, 0, 1, 2)

        layout.addWidget(stats_group)

        # 🔥 操作组
        operations_group = QGroupBox("数据库操作")
        operations_layout = QVBoxLayout(operations_group)

        # 操作按钮
        op_button_layout = QHBoxLayout()

        self.refresh_stats_button = QPushButton("刷新统计")
        self.refresh_stats_button.setIcon(QIcon(":/icons/refresh.png"))
        op_button_layout.addWidget(self.refresh_stats_button)

        self.export_data_button = QPushButton("导出数据")
        self.export_data_button.setIcon(QIcon(":/icons/export.png"))
        op_button_layout.addWidget(self.export_data_button)

        self.clear_data_button = QPushButton("清空数据")
        self.clear_data_button.setIcon(QIcon(":/icons/clear.png"))
        self.clear_data_button.setStyleSheet("color: red;")
        op_button_layout.addWidget(self.clear_data_button)

        operations_layout.addLayout(op_button_layout)

        # 操作日志
        self.operation_log = QTextEdit()
        self.operation_log.setMaximumHeight(150)
        self.operation_log.setPlaceholderText("操作日志将显示在这里...")
        operations_layout.addWidget(QLabel("操作日志:"))
        operations_layout.addWidget(self.operation_log)

        layout.addWidget(operations_group)

        layout.addStretch()
        self.tab_widget.addTab(tab, "数据统计")

    def setup_buttons(self):
        """设置底部按钮"""
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("保存配置")
        self.save_button.setIcon(QIcon(":/icons/save.png"))
        button_layout.addWidget(self.save_button)

        self.load_button = QPushButton("重载配置")
        self.load_button.setIcon(QIcon(":/icons/reload.png"))
        button_layout.addWidget(self.load_button)

        button_layout.addStretch()

        self.close_button = QPushButton("关闭")
        self.close_button.setIcon(QIcon(":/icons/close.png"))
        button_layout.addWidget(self.close_button)

        self.layout().addLayout(button_layout)

    def setup_connections(self):
        """设置信号连接"""
        # 按钮连接
        self.test_button.clicked.connect(self.test_connection)
        self.connect_button.clicked.connect(self.connect_database)
        self.disconnect_button.clicked.connect(self.disconnect_database)

        self.refresh_stats_button.clicked.connect(self.update_stats)
        self.export_data_button.clicked.connect(self.export_data)
        self.clear_data_button.clicked.connect(self.clear_data)

        self.save_button.clicked.connect(self.save_config)
        self.load_button.clicked.connect(self.load_current_config)
        self.close_button.clicked.connect(self.close)

        # 数据库管理器信号
        self.db_manager.connection_changed.connect(self.on_connection_changed)
        self.db_manager.stats_updated.connect(self.on_stats_updated)

    def load_current_config(self):
        """加载当前配置 - 修复版本"""
        try:
            config = database_config

            self.host_edit.setText(config.host)
            self.port_spin.setValue(config.port)
            self.database_edit.setText(config.database)
            self.username_edit.setText(config.username)
            self.password_edit.setText(config.password)
            self.timeout_spin.setValue(config.connection_timeout)
            self.max_conn_spin.setValue(config.max_connections)
            self.batch_size_spin.setValue(config.batch_size)

            self.log_message("配置加载完成")

        except Exception as e:
            self.log_message(f"加载配置失败: {e}", "error")

    def get_current_config(self) -> DatabaseConfig:
        """获取当前界面配置 - 修复版本"""
        return DatabaseConfig(
            host=self.host_edit.text().strip() or "localhost",
            port=self.port_spin.value(),
            database=self.database_edit.text().strip() or "semiconductor_db",
            username=self.username_edit.text().strip() or "app_user",
            password=self.password_edit.text().strip() or "app_pass",
            connection_timeout=self.timeout_spin.value(),
            max_connections=self.max_conn_spin.value(),
            batch_size=self.batch_size_spin.value(),
        )

    @Slot(object)
    def on_stats_updated(self, stats: DatabaseStats):
        """处理统计信息更新"""
        try:
            self.current_stats = stats

            # 更新显示
            self.telemetry_label.setText(f"遥测数据: {stats.telemetry_count:,} 条")
            self.alerts_label.setText(f"告警数据: {stats.alerts_count:,} 条")
            self.events_label.setText(f"事件数据: {stats.events_count:,} 条")
            self.total_label.setText(f"总记录数: {stats.total_records:,} 条")
            self.size_label.setText(f"数据库大小: {stats.database_size_mb:.2f} MB")

            self.log_message("统计信息自动更新")

        except Exception as e:
            self.log_message(f"处理统计更新失败: {e}", "error")

    @Slot()
    def test_connection(self):
        """测试数据库连接"""
        try:
            self.test_button.setEnabled(False)
            self.test_button.setText("测试中...")

            config = self.get_current_config()
            success, message = self.db_manager.test_connection(config)

            if success:
                self.log_message(f"✅ 连接测试成功: {message}")
                self.connection_info.setText(message)
                self.connection_info.setStyleSheet("color: green;")
            else:
                self.log_message(f"❌ 连接测试失败: {message}")
                self.connection_info.setText(message)
                self.connection_info.setStyleSheet("color: red;")

        except Exception as e:
            self.log_message(f"连接测试异常: {e}", "error")
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("测试连接")

    @Slot()
    def connect_database(self):
        """连接数据库"""
        try:
            config = self.get_current_config()
            success = self.db_manager.connect(config)

            if success:
                self.log_message("✅ 数据库连接成功")
            else:
                self.log_message("❌ 数据库连接失败")

        except Exception as e:
            self.log_message(f"连接数据库异常: {e}", "error")

    @Slot()
    def disconnect_database(self):
        """断开数据库连接"""
        try:
            self.db_manager.disconnect()
            self.log_message("数据库连接已断开")
        except Exception as e:
            self.log_message(f"断开连接异常: {e}", "error")

    @Slot()
    def update_stats(self):
        """更新统计信息 - 修复版本"""
        try:
            stats = self.db_manager.get_stats()
            self.current_stats = stats

            # 更新显示
            self.telemetry_label.setText(f"遥测数据: {stats.telemetry_count:,} 条")
            self.alerts_label.setText(f"告警数据: {stats.alerts_count:,} 条")
            self.events_label.setText(f"事件数据: {stats.events_count:,} 条")
            self.total_label.setText(f"总记录数: {stats.total_records:,} 条")
            self.size_label.setText(f"数据库大小: {stats.database_size_mb:.2f} MB")

            if stats.connected:
                self.log_message("统计信息已更新")
            else:
                self.log_message("数据库未连接，无法获取统计信息")

        except Exception as e:
            self.log_message(f"更新统计失败: {e}", "error")

    @Slot()
    def save_config(self):
        """保存配置 - 修复版本"""
        try:
            config = self.get_current_config()
            config.save_to_file()

            # 🔥 更新全局配置
            global database_config
            database_config.__dict__.update(config.__dict__)

            self.config_changed.emit(config)
            self.log_message("✅ 配置保存成功")

        except Exception as e:
            self.log_message(f"保存配置失败: {e}", "error")

    @Slot()
    def export_data(self):
        """导出数据（占位符）"""
        self.log_message("数据导出功能开发中...")

    @Slot()
    def clear_data(self):
        """清空数据（占位符）"""
        self.log_message("数据清空功能开发中...")

    @Slot(bool, str)
    def on_connection_changed(self, connected: bool, message: str):
        """处理连接状态变化"""
        if connected:
            self.connection_status.setText("● 已连接")
            self.connection_status.setStyleSheet(
                "color: green; font-weight: bold; font-size: 14px;"
            )
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.connection_info.setText(message)
            self.connection_info.setStyleSheet("color: green;")
        else:
            self.connection_status.setText("● 未连接")
            self.connection_status.setStyleSheet(
                "color: red; font-weight: bold; font-size: 14px;"
            )
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.connection_info.setText(message)
            self.connection_info.setStyleSheet("color: red;")

    def log_message(self, message: str, level: str = "info"):
        """记录日志消息"""
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if level == "error":
            formatted_msg = f"[{timestamp}] ❌ {message}"
            self.logger.error(message)
        else:
            formatted_msg = f"[{timestamp}] ℹ️ {message}"
            self.logger.info(message)

        self.operation_log.append(formatted_msg)

        # 自动滚动到底部
        cursor = self.operation_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.operation_log.setTextCursor(cursor)

    def closeEvent(self, event):
        """关闭事件"""
        self.stats_timer.stop()
        super().closeEvent(event)
