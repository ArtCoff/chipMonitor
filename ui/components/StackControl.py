import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QToolButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap, QFont
from utils.path import ICON_DIR


class StackControlWidget(QWidget):
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.current_mode = "table"
        self.setup_ui()
        self.logger.info("StackControl组件初始化完成")

    def setup_ui(self):
        """设置UI布局"""
        # 主容器
        self.setObjectName("stackControlWidget")
        self.setFixedWidth(120)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 15, 10, 15)

        # 按钮组
        buttons_frame = self.create_buttons()
        layout.addWidget(buttons_frame)

        # 弹性空间
        layout.addStretch()

        # 状态信息
        status_frame = self.create_status_info()
        layout.addWidget(status_frame)

    def create_buttons(self):
        """创建按钮组"""
        buttons_frame = QFrame()

        layout = QVBoxLayout(buttons_frame)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建按钮组（确保单选）
        self.button_group = QButtonGroup()
        self.button_group.setExclusive(True)

        # 按钮配置：(显示文本, 模式名称, 图标文件名, 提示文本, 是否默认选中)
        button_configs = [
            (
                "数据表",
                "table",
                f"{ICON_DIR}/icon_table.png",
                True,
            ),
            (
                "仪表盘",
                "dashboard",
                f"{ICON_DIR}/icon_gauge.png",
                False,
            ),
            (
                "趋势曲线",
                "chart",
                f"{ICON_DIR}/icon_screen.png",
                False,
            ),
        ]

        self.mode_buttons = {}
        for i, (text, mode, icon_file, is_default) in enumerate(button_configs):
            button = self.create_mode_button(text, mode, icon_file, is_default)
            self.mode_buttons[mode] = button
            self.button_group.addButton(button, i)
            layout.addWidget(button)

        # 连接按钮组信号
        self.button_group.buttonClicked.connect(self.on_button_clicked)

        return buttons_frame

    def create_mode_button(self, text, mode, icon_file, is_default=False):
        """创建单个模式按钮 - 图标在上方，文字在下方"""
        button = QToolButton()
        button.setCheckable(True)
        button.setChecked(is_default)
        button.setProperty("mode", mode)
        button.setFixedHeight(80)  # 大幅增加按钮高度

        # 设置按钮内容
        icon_path = ICON_DIR / icon_file
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            button.setIcon(icon)
            button.setIconSize(button.size() * 0.5)  # 图标大小

        button.setText(text)

        # 设置按钮样式 - 图标在上方，文字在下方
        button.setStyleSheet(
            """
            QPushButton {
                background-color: #FFFFFF;
                border: 2px solid #BDC3C7;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
                color: #2C3E50;
                text-align: center;
                padding: 8px 4px;
                qproperty-toolButtonStyle: ToolButtonTextUnderIcon;
            }
            QPushButton:checked {
                background-color: #3498DB;
                border-color: #2980B9;
                color: white;
            }
            QPushButton:hover {
                background-color: #F8F9FA;
                border-color: #95A5A6;
            }
            QPushButton:checked:hover {
                background-color: #2E86AB;
            }
            QPushButton:pressed {
                background-color: #3c4655;
            }
        """
        )

        # 设置工具按钮样式 - 图标在上方
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        return button

    def create_status_info(self):
        """创建状态信息面板"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Box)
        status_frame.setMaximumHeight(80)

        layout = QVBoxLayout(status_frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # 当前模式显示
        self.current_mode_label = QLabel("当前: 数据表格")
        self.current_mode_label.setAlignment(Qt.AlignCenter)
        self.current_mode_label.setStyleSheet(
            """
            QLabel {
                font-size: 11px;
                font-weight: bold;
                color: #34495E;
                background-color: #F8F9FA;
                padding: 4px;
                border-radius: 4px;
                border: 1px solid #E9ECEF;
            }
        """
        )

        # 设备状态信息
        self.device_status_label = QLabel("设备: 0")
        self.device_status_label.setAlignment(Qt.AlignCenter)
        self.device_status_label.setStyleSheet(
            """
            QLabel {
                font-size: 10px;
                color: #6C757D;
                padding: 2px;
            }
        """
        )

        layout.addWidget(self.current_mode_label)
        layout.addWidget(self.device_status_label)

        return status_frame

    @Slot()
    def on_button_clicked(self, button):
        """按钮点击事件处理"""
        mode = button.property("mode")
        if mode and mode != self.current_mode:
            old_mode = self.current_mode
            self.current_mode = mode

            # 更新状态显示
            self.update_mode_display(mode)

            # 发射模式切换信号
            self.mode_changed.emit(mode)

            self.logger.info(f"模式切换: {old_mode} -> {mode}")

    def update_mode_display(self, mode):
        """更新模式显示"""
        mode_names = {
            "table": "数据表",
            "dashboard": "仪表盘",
            "chart": "趋势曲线",
        }
        mode_text = mode_names.get(mode, mode)
        self.current_mode_label.setText(f"当前: {mode_text}")

    def set_mode(self, mode):
        """外部设置模式（同步按钮状态）"""
        if mode in self.mode_buttons and mode != self.current_mode:
            self.current_mode = mode

            # 更新按钮状态
            for mode_name, button in self.mode_buttons.items():
                button.setChecked(mode_name == mode)

            # 更新显示
            self.update_mode_display(mode)

    def get_current_mode(self):
        """获取当前模式"""
        return self.current_mode

    def update_device_count(self, count):
        """更新设备计数显示"""
        self.device_status_label.setText(f"设备: {count}")
