import logging
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QToolButton,
    QFrame,
    QMenu,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from PySide6.QtCore import Qt, Slot, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap
from utils.path import ICON_DIR
from .ThemeManager import theme_manager


class MenuBar(QWidget):
    # 统一信号定义
    network_debug_signal = Signal()
    database_signal = Signal()
    history_signal = Signal()
    concurrent_control_signal = Signal()
    system_debug_signal = Signal()
    etl_config_signal = Signal()
    settings_signal = Signal()
    exit_signal = Signal()
    #
    status_refresh_requested = Signal()  # 状态刷新请求

    def __init__(self, parent=None):
        super().__init__(parent)
        # 🔥 状态追踪
        self.mqtt_connected = False
        self.persistence_running = False
        self.db_connected = False

        self.setup_ui()
        self.setup_status_timer()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        # 功能按钮组
        function_buttons = self.create_function_buttons()
        layout.addWidget(function_buttons, 0)
        layout.addStretch(1)
        status_widget = self.create_status_widget()
        layout.addWidget(status_widget, 0)

    def create_function_buttons(self):
        """创建功能按钮组"""
        group = QWidget()
        layout = QHBoxLayout(group)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # 按钮配置：文本、信号、提示
        buttons_config = [
            (
                "网络调试",
                self.network_debug_signal,
                "网络调试工具",
                f"{ICON_DIR}/icon_network.png",
            ),
            (
                "数据库",
                self.database_signal,
                "数据库管理",
                f"{ICON_DIR}/icon_database.png",
            ),
            (
                "数据查询",
                self.history_signal,
                "数据查询与分析",
                f"{ICON_DIR}/icon_table.png",
            ),
            (
                "ETL配置",
                self.etl_config_signal,
                "ETL配置管理",
                f"{ICON_DIR}/icon_analysis.png",
            ),
            ("主题", self.show_theme_menu, "切换主题", f"{ICON_DIR}/icon_theme.png"),
            ("设置", self.settings_signal, "系统设置", f"{ICON_DIR}/icon_setting.png"),
            ("退出", self.exit_signal, "安全退出", f"{ICON_DIR}/icon_close.png"),
        ]

        for text, signal, tooltip, icon_path in buttons_config:
            btn = self.create_menu_button(text, tooltip, icon_path)
            btn.clicked.connect(signal)
            layout.addWidget(btn)

        return group

    def create_menu_button(self, text, tooltip, icon_path=None):
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setFixedSize(80, 80)
        button.setText(text)

        if icon_path:
            icon = QIcon(icon_path)
            button.setIcon(icon)
            button.setIconSize(QSize(32, 32))

        return button

    def create_status_widget(self):
        """创建状态指示和控制组件"""
        widget = QFrame()
        widget.setObjectName("statusControlWidget")
        widget.setFrameStyle(QFrame.NoFrame)
        widget.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # MQTT状态和控制
        mqtt_group = self.create_mqtt_control()
        layout.addWidget(mqtt_group)

        # 数据库持久化状态和控制
        persistence_group = self.create_persistence_control()
        layout.addWidget(persistence_group)

        # 系统状态指示
        system_status = self.create_system_status()
        layout.addWidget(system_status)
        return widget

    def create_mqtt_control(self):
        """创建MQTT控制组件"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # MQTT状态指示灯
        self.mqtt_indicator = QLabel("●")
        self.mqtt_indicator.setFixedSize(12, 12)
        self.update_mqtt_indicator(False)
        layout.addWidget(self.mqtt_indicator)

        # MQTT标签
        mqtt_label = QLabel("MQTT")
        mqtt_label.setFont(self.font())
        layout.addWidget(mqtt_label)
        return widget

    def create_persistence_control(self):
        """创建持久化控制组件"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 持久化状态指示灯
        self.persistence_indicator = QLabel("●")
        self.persistence_indicator.setFixedSize(12, 12)
        self.update_persistence_indicator(False)
        layout.addWidget(self.persistence_indicator)

        # 持久化标签
        persistence_label = QLabel("持久化")
        persistence_label.setFont(self.font())
        layout.addWidget(persistence_label)
        return widget

    def create_system_status(self):
        """创建系统状态指示"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 数据库状态指示灯
        self.db_indicator = QLabel("●")
        self.db_indicator.setFixedSize(12, 12)
        self.update_db_indicator(False)
        layout.addWidget(self.db_indicator)

        # 数据库标签
        db_label = QLabel("数据库")
        db_label.setFont(self.font())
        layout.addWidget(db_label)

        return widget

    def setup_status_timer(self):
        """设置状态更新定时器"""
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.status_refresh_requested.emit)
        self.status_timer.start(10000)  # 10秒自动刷新

    # 🔥 状态更新方法 - 供MainWindow调用
    @Slot(bool)
    def update_mqtt_status(self, connected: bool):
        """更新MQTT状态"""
        self.mqtt_connected = connected
        self.update_mqtt_indicator(connected)

    @Slot(bool)
    def update_persistence_status(self, running: bool):
        """更新持久化服务状态"""
        self.persistence_running = running
        self.update_persistence_indicator(running)

    @Slot(bool)
    def update_database_status(self, connected: bool):
        """更新数据库状态"""
        self.db_connected = connected
        self.update_db_indicator(connected)

    def update_mqtt_indicator(self, connected: bool):
        """更新MQTT指示灯"""
        if connected:
            self.mqtt_indicator.setStyleSheet(
                "color: #10b981; font-weight: bold;"
            )  # 绿色
            self.mqtt_indicator.setToolTip("MQTT已连接")
        else:
            self.mqtt_indicator.setStyleSheet(
                "color: #ef4444; font-weight: bold;"
            )  # 红色
            self.mqtt_indicator.setToolTip("MQTT未连接")

    def update_persistence_indicator(self, running: bool):
        """更新持久化指示灯"""
        if running:
            self.persistence_indicator.setStyleSheet(
                "color: #10b981; font-weight: bold;"
            )  # 蓝色
            self.persistence_indicator.setToolTip("持久化服务运行中")
        else:
            self.persistence_indicator.setStyleSheet(
                "color: #ef4444; font-weight: bold;"
            )  # 灰色
            self.persistence_indicator.setToolTip("持久化服务已停止")

    def update_db_indicator(self, connected: bool):
        """更新数据库指示灯"""
        if connected:
            self.db_indicator.setStyleSheet(
                "color: #10b981; font-weight: bold;"
            )  # 紫色
            self.db_indicator.setToolTip("数据库已连接")
        else:
            self.db_indicator.setStyleSheet(
                "color: #ef4444; font-weight: bold;"
            )  # 黄色
            self.db_indicator.setToolTip("数据库未连接")

    # 🔥 便捷方法 - 批量更新状态
    def update_all_status(
        self, mqtt_connected: bool, persistence_running: bool, db_connected: bool
    ):
        """批量更新所有状态"""
        self.update_mqtt_status(mqtt_connected)
        self.update_persistence_status(persistence_running)
        self.update_database_status(db_connected)

    @Slot()
    def show_theme_menu(self):
        """显示主题切换菜单"""
        menu = QMenu(self)

        # 获取当前主题
        current_theme = theme_manager.get_current_theme()

        # 添加主题选项
        for theme_key in theme_manager.get_available_themes():
            theme_name = theme_manager.get_theme_name(theme_key)
            action = menu.addAction(theme_name)
            action.setData(theme_key)
            action.setCheckable(True)

            # 标记当前主题
            if theme_key == current_theme:
                action.setChecked(True)

        # 连接菜单点击事件
        menu.triggered.connect(self.on_theme_menu_triggered)

        # 显示菜单
        button = self.sender()
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    @Slot()
    def on_theme_menu_triggered(self, action):
        """主题菜单项被触发"""
        theme_key = action.data()
        if theme_key and theme_key != theme_manager.get_current_theme():
            try:
                theme_manager.set_theme(theme_key)
                logging.info(f"主题已切换为: {theme_manager.get_theme_name(theme_key)}")
            except Exception as e:
                logging.error(f"主题切换失败: {e}")
