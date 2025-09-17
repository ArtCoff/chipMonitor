import logging
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QToolButton,
    QFrame,
    QMenu,
)
from PySide6.QtCore import Qt, Slot, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from utils.path import ICON_DIR
from .ThemeManager import theme_manager


class MenuBar(QWidget):
    # 统一信号定义
    network_debug_signal = Signal()
    database_signal = Signal()
    concurrent_control_signal = Signal()
    system_debug_signal = Signal()
    etl_config_signal = Signal()
    settings_signal = Signal()
    exit_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        # layout.setSpacing(8)

        # 功能按钮组
        function_buttons = self.create_function_buttons()
        layout.addWidget(function_buttons)
        layout.addStretch()

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
                "Redis缓存",
                self.concurrent_control_signal,
                "Redis缓存管理",
                f"{ICON_DIR}/icon_redis.png",
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
