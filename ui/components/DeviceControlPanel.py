import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QComboBox,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from datetime import datetime
import time


class DeviceControlPanel(QWidget):
    """设备选择和控制面板 - 右侧面板"""

    device_selected = Signal(str)  # 设备选择信号
    refresh_requested = Signal()  # 刷新请求信号
    clear_requested = Signal()  # 清空请求信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DeviceControlPanel")
        self.current_device = None

        # 初始化UI组件引用
        self.device_combo = None
        self.device_count_label = None
        self.status_indicator = None
        self.status_text = None
        self.last_update_label = None
        self.data_rate_label = None
        self.device_info_labels = {}
        self.stats_labels = {}

        self.setup_ui()
        self.logger.info("设备控制面板初始化完成")

    def setup_ui(self):
        """设置UI布局"""
        self.setMaximumWidth(260)
        self.setMinimumWidth(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 设备选择组
        layout.addWidget(self.create_device_selection_group())

        # 连接状态组
        layout.addWidget(self.create_status_group())

        # 设备信息组
        layout.addWidget(self.create_device_info_group())

        # 数据统计组
        layout.addWidget(self.create_stats_group())

        layout.addStretch()

        # 操作按钮组
        layout.addWidget(self.create_actions_group())

    def create_device_selection_group(self) -> QWidget:
        """创建设备选择组"""
        group = QGroupBox("设备选择")
        group.setObjectName("deviceSelectionGroup")
        layout = QVBoxLayout(group)

        # 设备下拉框
        self.device_combo = QComboBox()
        self.device_combo.setObjectName("deviceCombo")
        self.device_combo.setMinimumHeight(20)
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        layout.addWidget(self.device_combo)

        # 设备数量统计
        self.device_count_label = QLabel("设备数: 0")
        self.device_count_label.setObjectName("deviceCountLabel")
        layout.addWidget(self.device_count_label)

        return group

    def create_status_group(self) -> QWidget:
        """创建连接状态组"""
        group = QGroupBox("连接状态")
        group.setObjectName("statusGroup")
        layout = QVBoxLayout(group)

        # 状态指示器行
        status_layout = QHBoxLayout()

        self.status_indicator = QLabel("●")
        self.status_indicator.setObjectName("statusIndicator")
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel("离线")
        self.status_text.setObjectName("statusText")
        status_layout.addWidget(self.status_text)

        status_layout.addStretch()
        layout.addLayout(status_layout)

        # 最后更新时间
        self.last_update_label = QLabel("最后更新: --")
        self.last_update_label.setObjectName("lastUpdateLabel")
        layout.addWidget(self.last_update_label)

        # 数据接收率
        self.data_rate_label = QLabel("数据率: 0 Hz")
        self.data_rate_label.setObjectName("dataRateLabel")
        layout.addWidget(self.data_rate_label)

        return group

    def create_device_info_group(self) -> QWidget:
        """创建设备信息组"""
        group = QGroupBox("设备信息")
        group.setObjectName("deviceInfoGroup")
        layout = QVBoxLayout(group)

        # 设备信息项列表
        info_items = [
            ("设备类型", "device_type"),
            ("当前工艺", "recipe"),
            ("工艺步骤", "step"),
            ("批次号", "lot_number"),
            ("晶圆号", "wafer_id"),
        ]

        for label_text, key in info_items:
            item_layout = QHBoxLayout()

            # 标签
            label = QLabel(f"{label_text}:")
            label.setMinimumWidth(60)
            item_layout.addWidget(label)

            # 值
            value_label = QLabel("--")
            value_label.setObjectName(f"deviceInfo_{key}")
            item_layout.addWidget(value_label)

            layout.addLayout(item_layout)
            self.device_info_labels[key] = value_label

        return group

    def create_stats_group(self) -> QWidget:
        """创建数据统计组"""
        group = QGroupBox("数据统计")
        group.setObjectName("statsGroup")
        layout = QVBoxLayout(group)

        # 统计信息项列表
        stats_items = [
            ("数据点数", "data_points"),
            ("平均温度", "avg_temp"),
            ("平均压力", "avg_pressure"),
            ("运行时长", "runtime"),
        ]

        for label_text, key in stats_items:
            item_layout = QHBoxLayout()

            # 标签
            label = QLabel(f"{label_text}:")
            label.setMinimumWidth(60)
            item_layout.addWidget(label)

            # 值
            value_label = QLabel("--")
            value_label.setObjectName(f"stats_{key}")
            item_layout.addWidget(value_label)

            layout.addLayout(item_layout)
            self.stats_labels[key] = value_label

        return group

    def create_actions_group(self) -> QWidget:
        """创建操作按钮组"""
        group = QGroupBox("操作")
        group.setObjectName("actionsGroup")
        layout = QVBoxLayout(group)

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新数据")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.setMinimumHeight(32)
        refresh_btn.clicked.connect(self.on_refresh_clicked)
        layout.addWidget(refresh_btn)

        # 清空数据按钮
        clear_btn = QPushButton("🗑️ 清空数据")
        clear_btn.setObjectName("clearBtn")
        clear_btn.setMinimumHeight(32)
        clear_btn.clicked.connect(self.on_clear_clicked)
        layout.addWidget(clear_btn)

        return group

    # === 公共接口方法 ===

    def update_device_list(self, devices: list):
        """更新设备列表"""
        try:
            if not self.device_combo:
                return

            current_text = self.device_combo.currentText()
            self.device_combo.clear()

            if devices:
                self.device_combo.addItems(sorted(devices))

                # 恢复之前的选择
                if current_text in devices:
                    self.device_combo.setCurrentText(current_text)

            # 更新设备数量显示
            self.device_count_label.setText(f"设备数: {len(devices)}")

        except Exception as e:
            self.logger.error(f"设备列表更新失败: {e}")

    def update_device_status(self, device_id: str, device_data: dict):
        """更新设备状态信息"""
        try:
            if device_id != self.current_device:
                self.current_device = device_id

            # 更新连接状态
            self.update_connection_status(device_data)

            # 更新设备信息
            self.update_device_info(device_data)

            # 更新统计信息
            self.update_statistics(device_data)

        except Exception as e:
            self.logger.error(f"设备状态更新失败: {e}")

    def set_current_device(self, device_id: str):
        """设置当前设备"""
        try:
            if device_id != self.current_device:
                self.current_device = device_id

                # 更新下拉框选择
                if self.device_combo and device_id:
                    items = [
                        self.device_combo.itemText(i)
                        for i in range(self.device_combo.count())
                    ]
                    if device_id in items:
                        self.device_combo.setCurrentText(device_id)

                # 重置显示状态
                self.reset_display()

        except Exception as e:
            self.logger.error(f"设置当前设备失败: {e}")

    def get_current_device(self) -> str:
        """获取当前选择的设备ID"""
        return self.current_device

    # === 内部更新方法 ===

    def update_connection_status(self, device_data: dict):
        """更新连接状态显示（优先使用 online 字段；否则按 last_update 判定）"""
        try:
            if "online" in device_data:
                is_online = bool(device_data.get("online"))
            else:
                last_update = device_data.get("last_update") or 0
                threshold = device_data.get("offline_threshold", 30)
                is_online = last_update and (time.time() - last_update) < threshold

            if is_online:
                self.status_indicator.setObjectName("statusIndicatorOnline")
                self.status_text.setObjectName("statusTextOnline")
                self.status_text.setText("在线")
            else:
                self.status_indicator.setObjectName("statusIndicatorOffline")
                self.status_text.setObjectName("statusTextOffline")
                self.status_text.setText("离线")

            # 重新应用样式
            self.status_indicator.style().unpolish(self.status_indicator)
            self.status_indicator.style().polish(self.status_indicator)
            self.status_text.style().unpolish(self.status_text)
            self.status_text.style().polish(self.status_text)

            # 最后更新时间
            if device_data.get("last_update"):
                update_time = datetime.fromtimestamp(
                    device_data["last_update"]
                ).strftime("%H:%M:%S")
                self.last_update_label.setText(f"最后更新: {update_time}")
            else:
                self.last_update_label.setText("最后更新: --")

            # 数据率
            rate = device_data.get("data_rate") or "--"
            self.data_rate_label.setText(f"数据率: {rate}")

        except Exception as e:
            self.logger.error(f"连接状态更新失败: {e}")

    def update_device_info(self, device_data: dict):
        """更新设备信息显示"""
        try:
            info_mapping = {
                "device_type": device_data.get("device_type", "--"),
                "recipe": device_data.get("recipe", "--"),
                "step": device_data.get("step", "--"),
                "lot_number": device_data.get("lot_number", "--"),
                "wafer_id": device_data.get("wafer_id", "--"),
            }
            for key, value in info_mapping.items():
                if key in self.device_info_labels:
                    self.device_info_labels[key].setText(str(value))
        except Exception as e:
            self.logger.error(f"设备信息更新失败: {e}")

    def update_statistics(self, device_data: dict):
        """更新统计信息显示（直接用汇总值，不再依赖原始数组）"""
        try:
            self.stats_labels["data_points"].setText(
                str(device_data.get("data_points", 0))
            )

            avg_temp = device_data.get("avg_temp")
            self.stats_labels["avg_temp"].setText(
                f"{avg_temp:.1f}°C" if isinstance(avg_temp, (int, float)) else "--"
            )

            avg_pressure = device_data.get("avg_pressure")
            self.stats_labels["avg_pressure"].setText(
                f"{avg_pressure:.2f}Torr"
                if isinstance(avg_pressure, (int, float))
                else "--"
            )

            runtime = device_data.get("runtime", "--")
            self.stats_labels["runtime"].setText(runtime if runtime else "--")

        except Exception as e:
            self.logger.error(f"统计信息更新失败: {e}")

    def reset_display(self):
        """重置显示状态"""
        try:
            # 重置连接状态
            self.status_indicator.setObjectName("statusIndicatorOffline")
            self.status_text.setObjectName("statusTextOffline")
            self.status_text.setText("离线")
            self.last_update_label.setText("最后更新: --")
            self.data_rate_label.setText("数据率: 0 Hz")

            # 重置设备信息
            for label in self.device_info_labels.values():
                label.setText("--")

            # 重置统计信息
            for label in self.stats_labels.values():
                label.setText("--")

            # 重新应用样式
            self.status_indicator.style().unpolish(self.status_indicator)
            self.status_indicator.style().polish(self.status_indicator)
            self.status_text.style().unpolish(self.status_text)
            self.status_text.style().polish(self.status_text)

        except Exception as e:
            self.logger.error(f"重置显示失败: {e}")

    # === 信号处理方法 ===

    @Slot(str)
    def on_device_changed(self, device_id: str):
        """处理设备选择变更"""
        try:
            if device_id and device_id != self.current_device:
                self.current_device = device_id
                self.reset_display()
                self.device_selected.emit(device_id)
                self.logger.info(f"选择设备: {device_id}")

        except Exception as e:
            self.logger.error(f"设备选择处理失败: {e}")

    @Slot()
    def on_refresh_clicked(self):
        """处理刷新按钮点击"""
        try:
            self.refresh_requested.emit()
            self.logger.info("请求刷新数据")
        except Exception as e:
            self.logger.error(f"刷新请求失败: {e}")

    @Slot()
    def on_clear_clicked(self):
        """处理清空按钮点击"""
        try:
            self.clear_requested.emit()
            self.reset_display()
            self.logger.info("请求清空数据")
        except Exception as e:
            self.logger.error(f"清空请求失败: {e}")
