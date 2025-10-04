import logging
import numpy as np
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont
import pyqtgraph as pg


class DeviceChartsWidget(QWidget):
    """设备图表显示组件 - 简化版本"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DeviceChartsWidget")

        # 🔥 核心状态变量
        self.current_device = None
        self.is_paused = False

        # 🔥 图表配置
        self.chart_config = {
            "time_window": 300,  # 5分钟窗口
            "update_rate": 1000,  # 1秒更新
            "auto_scale": True,
        }

        # 🔥 图表信息存储
        self.chart_info = {}

        self.setup_ui()
        self.configure_pyqtgraph()

        # 🔥 简化定时器 - 仅用于状态更新
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_display)
        self.status_timer.start(5000)  # 5秒更新状态

        self.logger.info("设备图表组件初始化完成")

    def configure_pyqtgraph(self):
        """配置PyQtGraph"""
        pg.setConfigOption("background", "#111827")
        pg.setConfigOption("foreground", "#f9fafb")
        pg.setConfigOption("antialias", True)

    def setup_ui(self):
        """设置UI - 简化布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 🔥 顶部控制栏
        layout.addWidget(self.create_control_bar())

        # 🔥 图表区域
        layout.addWidget(self.create_charts_area(), 10)

        # 🔥 状态栏
        layout.addWidget(self.create_status_bar())

    def create_control_bar(self) -> QWidget:
        """创建控制栏"""
        control_bar = QFrame()
        control_bar.setObjectName("chartsControlBar")
        control_bar.setMaximumHeight(35)

        layout = QHBoxLayout(control_bar)
        layout.setContentsMargins(5, 5, 5, 5)

        # 设备标签
        self.device_label = QLabel("设备: 未选择")
        self.device_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(self.device_label)

        layout.addStretch()

        # 时间窗口
        layout.addWidget(QLabel("窗口:"))
        self.time_window_combo = QComboBox()
        self.time_window_combo.addItems(["1分钟", "5分钟", "10分钟", "30分钟", "全部"])
        self.time_window_combo.setCurrentText("5分钟")
        self.time_window_combo.currentTextChanged.connect(self.on_time_window_changed)
        layout.addWidget(self.time_window_combo)

        # 自动缩放
        self.auto_scale_check = QCheckBox("自动缩放")
        self.auto_scale_check.setChecked(True)
        self.auto_scale_check.toggled.connect(self.on_auto_scale_toggled)
        layout.addWidget(self.auto_scale_check)

        # 暂停按钮
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        layout.addWidget(self.pause_btn)

        # 清除按钮
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_charts)
        layout.addWidget(clear_btn)

        return control_bar

    def create_charts_area(self) -> QWidget:
        """创建图表区域"""
        charts_widget = QWidget()
        layout = QGridLayout(charts_widget)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # 🔥 定义图表参数
        chart_params = [
            ("temperature", "温度 (°C)", "#ef4444", 0, 0),
            ("pressure", "压力 (Torr)", "#3b82f6", 0, 1),
            ("rf_power", "RF功率 (W)", "#f59e0b", 1, 0),
            ("endpoint", "端点信号", "#10b981", 1, 1),
        ]

        # 🔥 创建图表
        for param_key, ylabel, color, row, col in chart_params:
            chart_widget = self.create_chart(param_key, ylabel, color)
            layout.addWidget(chart_widget, row, col)

        return charts_widget

    def create_chart(self, param_key: str, ylabel: str, color: str) -> QWidget:
        """创建单个图表"""
        widget = QWidget()
        widget.setMinimumHeight(160)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # 🔥 图表组件
        plot_widget = pg.PlotWidget()
        plot_widget.setBackground("#f9fafb")
        plot_widget.setLabel("left", ylabel, color="#080808", size="9pt")
        plot_widget.setLabel("bottom", "时间 (秒)", color="#080808", size="9pt")
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.setMouseEnabled(x=True, y=True)

        # 创建曲线
        curve = plot_widget.plot(
            [], [], pen=pg.mkPen(color=color, width=2), antialias=True
        )

        layout.addWidget(plot_widget, 10)

        # 🔥 底部统计信息
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(param_key.replace("_", " ").title())
        name_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        stats_layout.addWidget(name_label)

        stats_layout.addStretch()

        stats_label = QLabel("当前: -- | 范围: --")
        stats_label.setFont(QFont("Segoe UI", 8))
        stats_layout.addWidget(stats_label)

        stats_widget = QWidget()
        stats_widget.setLayout(stats_layout)
        stats_widget.setMaximumHeight(20)
        layout.addWidget(stats_widget)

        # 🔥 存储图表信息
        self.chart_info[param_key] = {
            "plot_widget": plot_widget,
            "curve": curve,
            "stats_label": stats_label,
            "color": color,
        }

        return widget

    def create_status_bar(self) -> QWidget:
        """创建状态栏"""
        status_bar = QFrame()
        status_bar.setObjectName("chartsStatusBar")
        status_bar.setMaximumHeight(25)

        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(5, 2, 5, 2)

        self.data_points_label = QLabel("数据点: 0")
        self.data_points_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self.data_points_label)

        layout.addWidget(QLabel("│"))

        self.last_update_label = QLabel("最后更新: --")
        self.last_update_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self.last_update_label)

        layout.addStretch()

        self.pause_indicator = QLabel("")
        layout.addWidget(self.pause_indicator)

        return status_bar

    # === 🔥 核心接口方法 ===

    def set_current_device(self, device_id: str):
        """设置当前设备"""
        if device_id != self.current_device:
            self.current_device = device_id
            self.device_label.setText(
                f"设备: {device_id}" if device_id else "设备: 未选择"
            )
            self.clear_charts()
            self.logger.info(f"切换到设备: {device_id}")

    def update_from_history_data(self, device_id: str, history_data: list):
        """🔥 核心更新方法 - 从历史数据更新图表"""
        try:
            if not history_data:
                self.clear_charts()
                return

            if device_id != self.current_device:
                self.set_current_device(device_id)

            if self.is_paused:
                return

            # 🔥 解析数据
            timestamps = []
            param_data = {key: [] for key in self.chart_info.keys()}

            for point in history_data:
                if isinstance(point, dict) and "timestamp" in point:
                    timestamps.append(point["timestamp"])
                    for param_key in param_data.keys():
                        value = point.get(param_key)
                        param_data[param_key].append(
                            value if value is not None else np.nan
                        )

            if not timestamps:
                return

            # 🔥 转换为相对时间
            base_time = timestamps[0]
            relative_times = np.array([(t - base_time) for t in timestamps])

            # 🔥 应用时间窗口过滤
            if self.chart_config["time_window"] > 0:
                current_time = relative_times[-1]
                window_start = current_time - self.chart_config["time_window"]
                mask = relative_times >= window_start
                relative_times = relative_times[mask]

                for param_key in param_data.keys():
                    param_data[param_key] = np.array(param_data[param_key])[mask]

            # 🔥 更新所有图表
            for param_key, chart_info in self.chart_info.items():
                values = param_data[param_key]

                # 过滤有效数据
                valid_mask = ~np.isnan(values)
                if np.any(valid_mask):
                    valid_times = relative_times[valid_mask]
                    valid_values = values[valid_mask]

                    # 更新曲线
                    chart_info["curve"].setData(valid_times, valid_values)

                    # 更新统计
                    self.update_chart_stats(chart_info, valid_values)

                    # 自动缩放
                    if self.chart_config["auto_scale"]:
                        chart_info["plot_widget"].enableAutoRange(axis="y")
                else:
                    chart_info["curve"].setData([], [])
                    chart_info["stats_label"].setText("当前: -- | 范围: --")

            # 更新状态
            self.data_points_label.setText(f"数据点: {len(timestamps)}")

        except Exception as e:
            self.logger.error(f"更新图表失败: {e}")

    def update_chart_stats(self, chart_info: dict, values: np.ndarray):
        """更新图表统计信息"""
        if len(values) == 0:
            chart_info["stats_label"].setText("当前: -- | 范围: --")
            return

        current = values[-1]
        min_val = np.min(values)
        max_val = np.max(values)

        # 🔥 简化格式化
        def fmt(val):
            return f"{val:.1f}" if abs(val) < 100 else f"{val:.0f}"

        chart_info["stats_label"].setText(
            f"当前: {fmt(current)} | 范围: {fmt(min_val)}~{fmt(max_val)}"
        )

    def clear_charts(self):
        """清空图表"""
        try:
            for chart_info in self.chart_info.values():
                chart_info["curve"].setData([], [])
                chart_info["stats_label"].setText("当前: -- | 范围: --")

            self.data_points_label.setText("数据点: 0")
            self.last_update_label.setText("最后更新: --")

        except Exception as e:
            self.logger.error(f"清空图表失败: {e}")

    # === 🔥 事件处理 ===

    @Slot(str)
    def on_time_window_changed(self, window_text: str):
        """时间窗口变更"""
        window_mapping = {
            "1分钟": 60,
            "5分钟": 300,
            "10分钟": 600,
            "30分钟": 1800,
            "全部": 0,
        }
        self.chart_config["time_window"] = window_mapping.get(window_text, 300)

    @Slot(bool)
    def on_auto_scale_toggled(self, enabled: bool):
        """自动缩放切换"""
        self.chart_config["auto_scale"] = enabled
        for chart_info in self.chart_info.values():
            if enabled:
                chart_info["plot_widget"].enableAutoRange()
            else:
                chart_info["plot_widget"].disableAutoRange()

    @Slot()
    def toggle_pause(self):
        """暂停/恢复"""
        self.is_paused = not self.is_paused

        if self.is_paused:
            self.pause_btn.setText("▶ 恢复")
            self.pause_indicator.setText("⏸ 已暂停")
            self.pause_indicator.setStyleSheet("color: #f59e0b;")
        else:
            self.pause_btn.setText("⏸ 暂停")
            self.pause_indicator.setText("")

    @Slot()
    def update_status_display(self):
        """更新状态显示"""
        if self.current_device and not self.is_paused:
            current_time = datetime.now().strftime("%H:%M:%S")
            self.last_update_label.setText(f"最后更新: {current_time}")
