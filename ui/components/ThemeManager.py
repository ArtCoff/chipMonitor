from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QGroupBox,
    QVBoxLayout,
)
from PySide6.QtCore import Signal, Slot
import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from utils.path import QSS_DIR


class ThemeSelector(QWidget):
    """主题选择器组件"""

    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 主题选择组
        theme_group = QGroupBox("主题设置")
        theme_layout = QHBoxLayout(theme_group)

        # 主题选择下拉框
        theme_layout.addWidget(QLabel("选择主题:"))

        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(120)

        # 填充主题选项
        for theme_key in theme_manager.get_available_themes():
            theme_name = theme_manager.get_theme_name(theme_key)
            self.theme_combo.addItem(theme_name, theme_key)

        # 设置当前主题
        current_theme = theme_manager.get_current_theme()
        current_index = self.theme_combo.findData(current_theme)
        if current_index >= 0:
            self.theme_combo.setCurrentIndex(current_index)

        theme_layout.addWidget(self.theme_combo)

        # 应用按钮
        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self.apply_theme)
        theme_layout.addWidget(self.apply_btn)

        theme_layout.addStretch()

        layout.addWidget(theme_group)
        layout.addStretch()

    def connect_signals(self):
        """连接信号"""
        self.theme_combo.currentTextChanged.connect(self.on_theme_selection_changed)

    @Slot()
    def on_theme_selection_changed(self):
        """主题选择改变"""
        self.apply_btn.setEnabled(True)

    @Slot()
    def apply_theme(self):
        """应用选中的主题"""
        selected_theme = self.theme_combo.currentData()
        if selected_theme:
            theme_manager.set_theme(selected_theme)
            self.theme_changed.emit(selected_theme)
            self.apply_btn.setEnabled(False)


class ThemeManager(QObject):
    """主题管理器"""

    theme_changed = Signal(str)  # 主题改变信号

    # 定义三种主题配色方案
    THEMES = {
        "blue": {
            "name": "深蓝主题",
            "primary": "#1e40af",
            "secondary": "#3b82f6",
            "background": "#f8fafc",
            "text": "#1e293b",
            "border": "#e2e8f0",
            "file": "theme_blue.qss",
        },
        "dark": {
            "name": "暗黑主题",
            "primary": "#1f2937",
            "secondary": "#374151",
            "background": "#111827",
            "text": "#f9fafb",
            "border": "#374151",
            "file": "theme_dark.qss",
        },
        "green": {
            "name": "绿色主题",
            "primary": "#059669",
            "secondary": "#10b981",
            "background": "#f0fdf4",
            "text": "#1e293b",
            "border": "#dcfce7",
            "file": "theme_green.qss",
        },
    }

    def __init__(self):
        super().__init__()
        self.current_theme = "blue"  # 默认主题

    def get_available_themes(self):
        """获取可用主题列表"""
        return list(self.THEMES.keys())

    def get_theme_name(self, theme_key):
        """获取主题显示名称"""
        return self.THEMES.get(theme_key, {}).get("name", theme_key)

    def get_current_theme(self):
        """获取当前主题"""
        return self.current_theme

    def set_theme(self, theme_key):
        """设置主题"""
        if theme_key not in self.THEMES:
            raise ValueError(f"未知主题: {theme_key}")

        self.current_theme = theme_key
        self.apply_theme(theme_key)
        self.theme_changed.emit(theme_key)

    def apply_theme(self, theme_key):
        """应用主题样式"""
        theme_info = self.THEMES[theme_key]
        qss_file = QSS_DIR / theme_info["file"]

        if not qss_file.exists():
            print(f"主题文件不存在: {qss_file}")
            return

        try:
            with open(qss_file, "r", encoding="utf-8") as f:
                style_content = f.read()

            # 应用到应用程序
            app = QApplication.instance()
            if app:
                app.setStyleSheet(style_content)
                print(f"主题切换成功: {theme_info['name']}")

        except Exception as e:
            print(f"加载主题失败: {e}")

    def get_theme_colors(self, theme_key=None):
        """获取主题颜色配置"""
        if theme_key is None:
            theme_key = self.current_theme
        return self.THEMES.get(theme_key, {})


# 全局主题管理器实例
theme_manager = ThemeManager()
