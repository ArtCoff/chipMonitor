import logging
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
import numpy as np
from collections import deque
import time
from datetime import datetime


class DeviceChartsWidget(QWidget):
    """设备图表显示组件 - 优化版本，提升可视化效果"""

    chart_config_changed = Signal(str, dict)  # 图表配置变更信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DeviceChartsWidget")

        # 当前设备和数据
        self.current_device = None
        self.device_data = {}

        # 图表组件引用
        self.charts = {}
        self.chart_info = {}

        # 图表配置
        self.chart_config = {
            "time_window": 300,  # 时间窗口(秒)
            "update_rate": 500,  # 更新频率(ms) - 调整为500ms
            "auto_scale": True,  # 自动缩放
            "show_grid": True,  # 显示网格
            "line_width": 2,  # 线条宽度
        }

        self.setup_ui()
        self.configure_pyqtgraph()
        self.setup_timer()

        self.logger.info("设备图表组件初始化完成")

    def setup_ui(self):
        """设置用户界面 - 优化布局比例"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 🔥 顶部控制栏 - 减小高度
        control_bar = self.create_control_bar()
        control_bar.setMaximumHeight(40)  # 减小高度
        layout.addWidget(control_bar)

        # 🔥 图表区域 - 大幅增加比例
        charts_area = self.create_charts_area()
        layout.addWidget(charts_area, 10)  # 给图表区域最大权重

        # 🔥 底部状态栏 - 减小高度
        status_bar = self.create_status_bar()
        status_bar.setMaximumHeight(25)  # 减小高度
        layout.addWidget(status_bar)

    def configure_pyqtgraph(self):
        """配置PyQtGraph为暗黑主题"""
        pg.setConfigOption("background", "#111827")
        pg.setConfigOption("foreground", "#f9fafb")
        pg.setConfigOption("antialias", True)

    def create_control_bar(self) -> QWidget:
        """创建顶部控制栏 - 紧凑布局"""
        control_bar = QFrame()
        control_bar.setObjectName("chartsControlBar")

        layout = QHBoxLayout(control_bar)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # 设备信息标签 - 缩小字体
        self.device_label = QLabel("设备: 未选择")
        self.device_label.setObjectName("chartsDeviceLabel")
        self.device_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(self.device_label)

        layout.addStretch()

        # 时间窗口选择 - 缩小
        time_window_label = QLabel("窗口:")
        time_window_label.setFont(QFont("Segoe UI", 9))
        layout.addWidget(time_window_label)

        self.time_window_combo = QComboBox()
        self.time_window_combo.setObjectName("timeWindowCombo")
        self.time_window_combo.setMaximumWidth(80)
        self.time_window_combo.addItems(
            ["1分钟", "5分钟", "10分钟", "30分钟", "1小时", "全部"]
        )
        self.time_window_combo.setCurrentText("5分钟")
        self.time_window_combo.currentTextChanged.connect(self.on_time_window_changed)
        layout.addWidget(self.time_window_combo)

        # 自动缩放开关 - 缩小
        self.auto_scale_check = QCheckBox("自动缩放")
        self.auto_scale_check.setObjectName("autoScaleCheck")
        self.auto_scale_check.setChecked(True)
        self.auto_scale_check.toggled.connect(self.on_auto_scale_toggled)
        layout.addWidget(self.auto_scale_check)

        # 暂停/恢复按钮 - 缩小
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.setObjectName("pauseBtn")
        self.pause_btn.setMaximumWidth(70)
        self.pause_btn.clicked.connect(self.toggle_pause)
        layout.addWidget(self.pause_btn)

        # 清除数据按钮 - 缩小
        clear_btn = QPushButton("🗑 清除")
        clear_btn.setObjectName("clearChartsBtn")
        clear_btn.setMaximumWidth(70)
        clear_btn.clicked.connect(self.clear_charts)
        layout.addWidget(clear_btn)

        return control_bar

    def create_charts_area(self) -> QWidget:
        """创建图表区域 - 优化布局，移除标题"""
        charts_widget = QWidget()
        charts_layout = QGridLayout(charts_widget)
        charts_layout.setSpacing(6)  # 减小间距
        charts_layout.setContentsMargins(0, 0, 0, 0)

        # 🔥 创建各种参数图表 - 移除GroupBox标题，直接使用图表
        self.charts = {}
        self.chart_info = {}

        # 第一行：温度和压力
        self.charts["temperature"] = self.create_trend_chart(
            "温度", "温度 (°C)", "#ef4444", "temperature"
        )
        charts_layout.addWidget(self.charts["temperature"], 0, 0)

        self.charts["pressure"] = self.create_trend_chart(
            "压力", "压力 (Torr)", "#3b82f6", "pressure"
        )
        charts_layout.addWidget(self.charts["pressure"], 0, 1)

        # 第二行：功率和端点信号
        self.charts["rf_power"] = self.create_trend_chart(
            "RF功率", "功率 (W)", "#f59e0b", "rf_power"
        )
        charts_layout.addWidget(self.charts["rf_power"], 1, 0)

        self.charts["endpoint"] = self.create_trend_chart(
            "端点信号", "端点信号", "#10b981", "endpoint"
        )
        charts_layout.addWidget(self.charts["endpoint"], 1, 1)

        # 第三行：湿度和振动（可选参数）
        self.charts["humidity"] = self.create_trend_chart(
            "湿度", "湿度 (%RH)", "#8b5cf6", "humidity"
        )
        charts_layout.addWidget(self.charts["humidity"], 2, 0)

        self.charts["vibration"] = self.create_trend_chart(
            "振动", "振动 (mm/s)", "#f97316", "vibration"
        )
        charts_layout.addWidget(self.charts["vibration"], 2, 1)

        return charts_widget

    def create_trend_chart(self, title: str, ylabel: str, color: str, param_key: str):
        """创建单个趋势图表 - 移除GroupBox，优化布局"""
        # 🔥 直接创建Widget，不用GroupBox
        widget = QWidget()
        widget.setObjectName("chartWidget")
        widget.setMinimumHeight(180)  # 减小最小高度

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # 🔥 创建图表组件 - 占据主要空间
        plot_widget = pg.PlotWidget()
        plot_widget.setBackground("#111827")

        # 设置标签和样式
        plot_widget.setLabel("left", ylabel, color="#f9fafb", size="9pt")
        plot_widget.setLabel("bottom", "时间 (秒)", color="#f9fafb", size="9pt")

        # 🔥 配置网格 - 更清晰的网格
        plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # 设置鼠标交互
        plot_widget.setMouseEnabled(x=True, y=True)
        plot_widget.enableAutoRange(axis="y")

        # 🔥 创建数据曲线 - 更醒目的线条
        curve = plot_widget.plot(
            [],
            [],
            pen=pg.mkPen(
                color=color, width=self.chart_config["line_width"] + 1
            ),  # 稍粗线条
            name=title,
            antialias=True,
        )

        # 🔥 添加十字准线 - 更清晰
        crosshair_v = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen("#9ca3af", width=1, style=Qt.DashLine)
        )
        crosshair_h = pg.InfiniteLine(
            angle=0, movable=False, pen=pg.mkPen("#9ca3af", width=1, style=Qt.DashLine)
        )
        plot_widget.addItem(crosshair_v, ignoreBounds=True)
        plot_widget.addItem(crosshair_h, ignoreBounds=True)

        # 鼠标移动事件
        def mouse_moved(evt):
            if plot_widget.sceneBoundingRect().contains(evt):
                mouse_point = plot_widget.getViewBox().mapSceneToView(evt)
                crosshair_v.setPos(mouse_point.x())
                crosshair_h.setPos(mouse_point.y())

        plot_widget.scene().sigMouseMoved.connect(mouse_moved)

        # 🔥 图表占据主要空间
        layout.addWidget(plot_widget, 10)

        # 🔥 底部简化的统计信息 - 一行显示
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)
        stats_layout.setContentsMargins(0, 0, 0, 0)

        # 图表名称标签
        name_label = QLabel(title)
        name_label.setObjectName("chartNameLabel")
        name_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        stats_layout.addWidget(name_label)

        stats_layout.addStretch()

        # 统计信息标签 - 紧凑布局
        current_label = QLabel("当前: --")
        current_label.setObjectName("chartStatsLabel")
        current_label.setFont(QFont("Segoe UI", 8))
        stats_layout.addWidget(current_label)

        min_label = QLabel("最小: --")
        min_label.setObjectName("chartStatsLabel")
        min_label.setFont(QFont("Segoe UI", 8))
        stats_layout.addWidget(min_label)

        max_label = QLabel("最大: --")
        max_label.setObjectName("chartStatsLabel")
        max_label.setFont(QFont("Segoe UI", 8))
        stats_layout.addWidget(max_label)

        avg_label = QLabel("平均: --")
        avg_label.setObjectName("chartStatsLabel")
        avg_label.setFont(QFont("Segoe UI", 8))
        stats_layout.addWidget(avg_label)

        # 统计信息高度最小化
        stats_widget = QWidget()
        stats_widget.setLayout(stats_layout)
        stats_widget.setMaximumHeight(20)
        layout.addWidget(stats_widget)

        # 🔥 存储图表信息
        chart_info = {
            "widget": widget,
            "plot_widget": plot_widget,
            "curve": curve,
            "color": color,
            "param_key": param_key,
            "crosshair_v": crosshair_v,
            "crosshair_h": crosshair_h,
            "name_label": name_label,
            "current_label": current_label,
            "min_label": min_label,
            "max_label": max_label,
            "avg_label": avg_label,
        }

        self.chart_info[param_key] = chart_info

        return widget

    def create_status_bar(self) -> QWidget:
        """创建底部状态栏 - 紧凑布局"""
        status_bar = QFrame()
        status_bar.setObjectName("chartsStatusBar")

        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(10)

        # 数据状态信息 - 缩小字体
        self.data_points_label = QLabel("数据点: 0")
        self.data_points_label.setObjectName("chartsStatusLabel")
        self.data_points_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self.data_points_label)

        # 分隔符
        sep1 = QLabel("│")
        sep1.setObjectName("separator")
        layout.addWidget(sep1)

        # 更新频率
        self.update_rate_label = QLabel("更新率: 0 Hz")
        self.update_rate_label.setObjectName("chartsStatusLabel")
        self.update_rate_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self.update_rate_label)

        # 分隔符
        sep2 = QLabel("│")
        sep2.setObjectName("separator")
        layout.addWidget(sep2)

        # 最后更新时间
        self.last_update_label = QLabel("最后更新: --")
        self.last_update_label.setObjectName("chartsStatusLabel")
        self.last_update_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self.last_update_label)

        layout.addStretch()

        # 暂停状态指示
        self.pause_indicator = QLabel("")
        self.pause_indicator.setObjectName("pauseIndicator")
        layout.addWidget(self.pause_indicator)

        return status_bar

    def setup_timer(self):
        """设置更新定时器"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_charts)
        self.is_paused = False

    # === 公共接口方法 ===

    def set_current_device(self, device_id: str):
        """设置当前显示的设备"""
        try:
            if device_id != self.current_device:
                self.current_device = device_id
                self.device_label.setText(
                    f"设备: {device_id}" if device_id else "设备: 未选择"
                )

                # 清空图表数据
                self.clear_charts()

                self.logger.info(f"设置图表显示设备: {device_id}")

        except Exception as e:
            self.logger.error(f"设置设备失败: {e}")

    def update_device_data(self, device_data: dict):
        """更新设备数据并刷新图表"""
        try:
            if not self.current_device:
                return

            # 🔥 更新设备数据
            self.device_data = device_data

            # 🔥 如果定时器未启动，启动它
            if not self.update_timer.isActive() and not self.is_paused:
                self.update_timer.start(self.chart_config["update_rate"])

            # 🔥 立即更新一次图表
            self.update_charts()

        except Exception as e:
            self.logger.error(f"设备数据更新失败: {e}")

    def clear_charts(self):
        """清空所有图表数据"""
        try:
            for param_key, chart_info in self.chart_info.items():
                chart_info["curve"].setData([], [])

                # 重置统计标签
                chart_info["current_label"].setText("当前: --")
                chart_info["min_label"].setText("最小: --")
                chart_info["max_label"].setText("最大: --")
                chart_info["avg_label"].setText("平均: --")

            # 重置状态栏
            self.data_points_label.setText("数据点: 0")
            self.update_rate_label.setText("更新率: 0 Hz")
            self.last_update_label.setText("最后更新: --")

            # 停止定时器
            if self.update_timer.isActive():
                self.update_timer.stop()

            self.logger.info("图表数据已清空")

        except Exception as e:
            self.logger.error(f"图表清空失败: {e}")

    # === 🔥 优化的图表更新方法 ===

    @Slot()
    def update_charts(self):
        """更新所有图表显示 - 修复显示问题"""
        try:
            if not self.device_data or self.is_paused:
                return

            # 🔥 获取时间戳数据
            timestamps = self.device_data.get("timestamps", [])
            if not timestamps or len(timestamps) == 0:
                return

            # 🔥 转换时间戳为相对时间（秒）
            timestamps_list = list(timestamps)  # 转换deque为list
            if len(timestamps_list) == 0:
                return

            base_time = timestamps_list[0]
            relative_times = [(t - base_time) for t in timestamps_list]

            # 🔥 更新各个参数图表
            for param_key, chart_info in self.chart_info.items():
                param_data = self.device_data.get(param_key, [])
                if param_data and len(param_data) > 0:
                    self.update_single_chart(
                        chart_info, relative_times, list(param_data)
                    )

            # 更新状态信息
            self.update_status_info(len(timestamps_list))

        except Exception as e:
            self.logger.error(f"图表更新失败: {e}")

    def update_single_chart(
        self, chart_info: dict, relative_times: list, param_values: list
    ):
        """更新单个图表"""
        try:
            if not relative_times or not param_values:
                return

            # 🔥 确保数据长度一致
            min_length = min(len(relative_times), len(param_values))
            if min_length == 0:
                return

            display_times = relative_times[:min_length]
            display_values = param_values[:min_length]

            # 🔥 应用时间窗口过滤
            if self.chart_config["time_window"] > 0:
                current_time = display_times[-1] if display_times else 0
                window_start = current_time - self.chart_config["time_window"]

                # 过滤数据
                filtered_times = []
                filtered_values = []

                for t, v in zip(display_times, display_values):
                    if t >= window_start:
                        filtered_times.append(t)
                        filtered_values.append(v)

                display_times = filtered_times
                display_values = filtered_values

            # 🔥 更新曲线数据
            if (
                display_times
                and display_values
                and len(display_times) == len(display_values)
            ):
                # 转换为numpy数组以提高性能
                x_data = np.array(display_times)
                y_data = np.array(display_values)

                chart_info["curve"].setData(x_data, y_data)

                # 更新统计信息
                self.update_chart_statistics(chart_info, display_values)

                # 🔥 自动缩放
                if self.chart_config["auto_scale"]:
                    chart_info["plot_widget"].enableAutoRange(axis="y")

        except Exception as e:
            self.logger.error(f"单个图表更新失败: {e}")

    def update_chart_statistics(self, chart_info: dict, values: list):
        """更新图表统计信息"""
        try:
            if not values:
                return

            values_array = np.array(values)
            min_val = np.min(values_array)
            max_val = np.max(values_array)
            avg_val = np.mean(values_array)
            current_val = values_array[-1]

            # 🔥 格式化显示，根据数值大小调整精度
            def format_value(val):
                if abs(val) >= 1000:
                    return f"{val:.0f}"
                elif abs(val) >= 10:
                    return f"{val:.1f}"
                else:
                    return f"{val:.2f}"

            chart_info["current_label"].setText(f"当前: {format_value(current_val)}")
            chart_info["min_label"].setText(f"最小: {format_value(min_val)}")
            chart_info["max_label"].setText(f"最大: {format_value(max_val)}")
            chart_info["avg_label"].setText(f"平均: {format_value(avg_val)}")

        except Exception as e:
            self.logger.error(f"统计信息更新失败: {e}")

    def update_status_info(self, data_count: int):
        """更新状态栏信息"""
        try:
            # 数据点数
            self.data_points_label.setText(f"数据点: {data_count}")

            # 更新率
            update_freq = (
                1000 / self.chart_config["update_rate"]
                if self.chart_config["update_rate"] > 0
                else 0
            )
            self.update_rate_label.setText(f"更新率: {update_freq:.1f} Hz")

            # 最后更新时间
            current_time = datetime.now().strftime("%H:%M:%S")
            self.last_update_label.setText(f"最后更新: {current_time}")

        except Exception as e:
            self.logger.error(f"状态信息更新失败: {e}")

    # === 控制栏事件处理 ===

    @Slot(str)
    def on_time_window_changed(self, window_text: str):
        """时间窗口变更处理"""
        try:
            window_mapping = {
                "1分钟": 60,
                "5分钟": 300,
                "10分钟": 600,
                "30分钟": 1800,
                "1小时": 3600,
                "全部": 0,
            }

            self.chart_config["time_window"] = window_mapping.get(window_text, 300)
            self.logger.info(f"时间窗口设置为: {window_text}")

        except Exception as e:
            self.logger.error(f"时间窗口变更失败: {e}")

    @Slot(bool)
    def on_auto_scale_toggled(self, enabled: bool):
        """自动缩放切换处理"""
        try:
            self.chart_config["auto_scale"] = enabled

            for chart_info in self.chart_info.values():
                if enabled:
                    chart_info["plot_widget"].enableAutoRange()
                else:
                    chart_info["plot_widget"].disableAutoRange()

            self.logger.info(f"自动缩放设置为: {enabled}")

        except Exception as e:
            self.logger.error(f"自动缩放切换失败: {e}")

    @Slot()
    def toggle_pause(self):
        """切换暂停/恢复状态"""
        try:
            self.is_paused = not self.is_paused

            if self.is_paused:
                self.update_timer.stop()
                self.pause_btn.setText("▶ 恢复")
                self.pause_indicator.setText("⏸ 已暂停")
                self.pause_indicator.setStyleSheet("color: #f59e0b;")
            else:
                self.update_timer.start(self.chart_config["update_rate"])
                self.pause_btn.setText("⏸ 暂停")
                self.pause_indicator.setText("")

            self.logger.info(f"图表更新状态: {'暂停' if self.is_paused else '恢复'}")

        except Exception as e:
            self.logger.error(f"暂停切换失败: {e}")
