import logging
import numpy as np
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QFrame,
    QMdiArea,
    QMdiSubWindow,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont
import pyqtgraph as pg


class ChartSubWindow(QMdiSubWindow):
    """图表子窗口"""

    def __init__(self, param_key: str, param_label: str, color: str, parent=None):
        super().__init__(parent)
        self.param_key = param_key
        self.param_label = param_label
        self.color = color

        # 设置窗口属性
        self.setWindowTitle(param_label)

        self.setMinimumSize(300, 200)
        self.resize(400, 250)

        # 创建图表widget
        self.chart_widget = QWidget()
        self.setup_chart()
        self.setWidget(self.chart_widget)

        # 数据
        self.current_data = ([], [])

    def setup_chart(self):
        """设置图表"""
        layout = QVBoxLayout(self.chart_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # 图表
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")  # 白色背景
        self.plot_widget.setLabel("left", self.param_label, color="k", size="10pt")
        self.plot_widget.setLabel("bottom", "时间 (秒)", color="k", size="10pt")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setMouseEnabled(x=True, y=True)

        # 创建曲线
        self.curve = self.plot_widget.plot(
            [], [], pen=pg.mkPen(color=self.color, width=2), antialias=True
        )

        layout.addWidget(self.plot_widget, 10)

        # 统计信息
        self.stats_label = QLabel("当前: -- | 范围: --")
        self.stats_label.setFont(QFont("Arial", 9))
        layout.addWidget(self.stats_label)

    def update_data(self, times: np.ndarray, values: np.ndarray):
        """更新数据"""
        try:
            if len(times) == 0 or len(values) == 0:
                self.clear_data()
                return

            # 过滤有效数据
            valid_mask = ~np.isnan(values)
            if not np.any(valid_mask):
                self.clear_data()
                return

            valid_times = times[valid_mask]
            valid_values = values[valid_mask]

            # 更新曲线
            self.curve.setData(valid_times, valid_values)
            self.current_data = (valid_times, valid_values)

            # 更新统计
            self.update_stats(valid_values)

        except Exception as e:
            print(f"更新数据失败: {e}")

    def update_stats(self, values: np.ndarray):
        """更新统计信息"""
        if len(values) == 0:
            self.stats_label.setText("当前: -- | 范围: --")
            return

        current = values[-1]
        min_val = np.nanmin(values)
        max_val = np.nanmax(values)

        def fmt(val):
            if abs(val) < 1:
                return f"{val:.3f}"
            elif abs(val) < 100:
                return f"{val:.1f}"
            else:
                return f"{val:.0f}"

        self.stats_label.setText(
            f"当前: {fmt(current)} | 范围: {fmt(min_val)}~{fmt(max_val)}"
        )

    def clear_data(self):
        """清空数据"""
        self.curve.setData([], [])
        self.stats_label.setText("当前: -- | 范围: --")
        self.current_data = ([], [])


class DeviceChartsWidget(QWidget):
    """设备图表显示组件 - 使用MDI区域"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DeviceChartsWidget")

        # 核心状态
        self.current_device = None
        self.is_paused = False

        # 图表子窗口管理
        self.chart_windows = {}  # param_key -> ChartSubWindow

        # 配置
        self.chart_config = {
            "time_window": 300,  # 秒
            "auto_scale": True,
            "max_points": 4000,  # 降采样上限
        }

        # 字段配置
        self.non_numeric_keys = {
            "timestamp",
            "device_id",
            "device_type",
            "recipe",
            "step",
            "lot_number",
            "wafer_id",
        }
        self.param_label_map = {
            "temperature": "温度 (°C)",
            "pressure": "压力 (Torr)",
            "rf_power": "RF功率 (W)",
            "endpoint": "端点信号",
        }
        self.color_palette = [
            "#ef4444",
            "#3b82f6",
            "#10b981",
            "#f59e0b",
            "#8b5cf6",
            "#06b6d4",
            "#f97316",
            "#22c55e",
            "#eab308",
            "#84cc16",
            "#a855f7",
            "#db2777",
        ]

        self.setup_ui()
        self.configure_pyqtgraph()

        self.logger.info("设备图表组件初始化完成")

    def configure_pyqtgraph(self):
        """配置pyqtgraph"""
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("antialias", True)

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self.mdi_area = QMdiArea()
        # 控制栏
        layout.addWidget(self.create_control_bar())

        # MDI区域

        self.mdi_area.setViewMode(QMdiArea.SubWindowView)
        self.mdi_area.setTabsClosable(False)  # 不允许关闭标签页
        layout.addWidget(self.mdi_area, 10)

        # 状态栏
        layout.addWidget(self.create_status_bar())

    def create_control_bar(self) -> QWidget:
        """创建控制栏"""
        control_bar = QFrame()
        control_bar.setMaximumHeight(40)

        layout = QHBoxLayout(control_bar)
        layout.setContentsMargins(5, 5, 5, 5)

        # 设备标签
        self.device_label = QLabel("设备: 未选择")
        self.device_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self.device_label)

        layout.addStretch()

        # 时间窗口
        layout.addWidget(QLabel("时间窗口:"))
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
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        layout.addWidget(self.pause_btn)

        # 清除按钮
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_charts)
        layout.addWidget(clear_btn)

        # 窗口排列
        tile_btn = QPushButton("平铺")
        tile_btn.clicked.connect(self.mdi_area.tileSubWindows)
        layout.addWidget(tile_btn)

        cascade_btn = QPushButton("层叠")
        cascade_btn.clicked.connect(self.mdi_area.cascadeSubWindows)
        layout.addWidget(cascade_btn)

        return control_bar

    def create_status_bar(self) -> QWidget:
        """创建状态栏"""
        status_bar = QFrame()
        status_bar.setMaximumHeight(25)

        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(5, 2, 5, 2)

        self.data_points_label = QLabel("数据点: 0")
        layout.addWidget(self.data_points_label)

        layout.addWidget(QLabel(" | "))

        self.last_update_label = QLabel("最后更新: --")
        layout.addWidget(self.last_update_label)

        layout.addStretch()

        self.pause_indicator = QLabel("")
        layout.addWidget(self.pause_indicator)

        return status_bar

    # ==== 辅助方法 ====

    def _label_for(self, key: str) -> str:
        """获取参数标签"""
        if key in self.param_label_map:
            return self.param_label_map[key]
        if key.startswith("gas_"):
            return f"气体 {key[4:].upper()} (sccm)"
        return key.replace("_", " ").title()

    def _color_for_index(self, idx: int) -> str:
        """获取颜色"""
        return self.color_palette[idx % len(self.color_palette)]

    def _detect_numeric_params(self, sample: dict) -> list:
        """检测数值参数"""
        numeric_params = []
        for k, v in (sample or {}).items():
            if k in self.non_numeric_keys:
                continue
            if isinstance(v, (int, float)):
                numeric_params.append(k)

        # 稳定排序
        known = [
            k
            for k in ["temperature", "pressure", "rf_power", "endpoint"]
            if k in numeric_params
        ]
        others = sorted([k for k in numeric_params if k not in known])
        return known + others

    def _ensure_chart_windows(self, param_keys: list):
        """确保图表窗口存在"""
        # 移除不需要的窗口
        for key in list(self.chart_windows.keys()):
            if key not in param_keys:
                window = self.chart_windows.pop(key)
                self.mdi_area.removeSubWindow(window)
                window.deleteLater()

        # 创建新的窗口
        for idx, key in enumerate(param_keys):
            if key not in self.chart_windows:
                chart_window = ChartSubWindow(
                    key, self._label_for(key), self._color_for_index(idx)
                )

                self.mdi_area.addSubWindow(chart_window)
                chart_window.show()

                self.chart_windows[key] = chart_window

        # 自动排列窗口
        if len(param_keys) <= 4:
            self.mdi_area.tileSubWindows()

    # === 核心接口 ===

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
        """更新历史数据"""
        try:
            if not history_data:
                self.clear_charts()
                return

            if device_id != self.current_device:
                self.set_current_device(device_id)

            if self.is_paused:
                return

            # 检测参数
            latest = history_data[-1] if isinstance(history_data[-1], dict) else {}
            param_keys = self._detect_numeric_params(latest)
            if not param_keys:
                self.clear_charts()
                return

            # 确保窗口存在
            self._ensure_chart_windows(param_keys)

            # 处理时间数据
            timestamps = [
                p.get("timestamp")
                for p in history_data
                if isinstance(p, dict) and p.get("timestamp") is not None
            ]
            if not timestamps:
                return

            # 时间归一化
            base = timestamps[0]
            if base > 1e12:
                unit_div = 1e6  # 微秒
            elif base > 1e10:
                unit_div = 1e3  # 毫秒
            else:
                unit_div = 1.0  # 秒

            t_arr = np.array(timestamps, dtype=float)
            relative_times = (t_arr - t_arr[0]) / unit_div

            # 时间窗口过滤
            if self.chart_config["time_window"] > 0 and len(relative_times) > 1:
                current_time = relative_times[-1]
                window_start = current_time - self.chart_config["time_window"]
                mask = relative_times >= window_start
                relative_times = relative_times[mask]
                filtered_data = [
                    history_data[i] for i in range(len(history_data)) if mask[i]
                ]
            else:
                filtered_data = history_data

            # 更新每个图表窗口
            for param_key in param_keys:
                values = []
                for point in filtered_data:
                    if isinstance(point, dict):
                        v = point.get(param_key)
                        values.append(v if isinstance(v, (int, float)) else np.nan)

                values = np.array(values)

                # 更新窗口数据
                if param_key in self.chart_windows:
                    self.chart_windows[param_key].update_data(relative_times, values)

            # 更新状态
            self.data_points_label.setText(f"数据点: {len(timestamps)}")

            # 更新标题
            rec = latest.get("recipe", "--")
            step = latest.get("step", "--")
            suffix = f" · {rec}/{step}" if rec != "--" or step != "--" else ""
            base_title = f"设备: {device_id}" if device_id else "设备: 未选择"
            self.device_label.setText(base_title + suffix)

            # 更新时间
            try:
                last_ts = timestamps[-1] / unit_div
                time_str = datetime.fromtimestamp(last_ts).strftime("%H:%M:%S")
                self.last_update_label.setText(f"最后更新: {time_str}")
            except:
                self.last_update_label.setText("最后更新: --")

        except Exception as e:
            self.logger.error(f"更新图表失败: {e}")

    def clear_charts(self):
        """清空图表"""
        try:
            for window in self.chart_windows.values():
                window.clear_data()

            self.data_points_label.setText("数据点: 0")
            self.last_update_label.setText("最后更新: --")

        except Exception as e:
            self.logger.error(f"清空图表失败: {e}")

    # === 事件处理 ===

    @Slot(str)
    def on_time_window_changed(self, window_text: str):
        """时间窗口改变"""
        mapping = {"1分钟": 60, "5分钟": 300, "10分钟": 600, "30分钟": 1800, "全部": 0}
        self.chart_config["time_window"] = mapping.get(window_text, 300)

    @Slot(bool)
    def on_auto_scale_toggled(self, enabled: bool):
        """自动缩放切换"""
        self.chart_config["auto_scale"] = enabled
        for window in self.chart_windows.values():
            if enabled:
                window.plot_widget.enableAutoRange()
            else:
                window.plot_widget.disableAutoRange()

    @Slot()
    def toggle_pause(self):
        """切换暂停状态"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.setText("恢复")
            self.pause_indicator.setText("已暂停")
        else:
            self.pause_btn.setText("暂停")
            self.pause_indicator.setText("")
