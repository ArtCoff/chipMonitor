import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QGroupBox,
)
from PySide6.QtCore import Qt
import pyqtgraph as pg


class StatisticsDialog(QDialog):
    """遥测数据统计分析对话框"""

    def __init__(self, data: list, parent=None):
        super().__init__(parent)
        self.data = data
        self.numeric_fields = ["pressure", "temperature", "rf_power", "endpoint"]

        self.setWindowTitle("遥测数据统计分析")
        self.setModal(True)
        self.resize(900, 700)

        self.setup_ui()
        self.calculate_statistics()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 标签页
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 基础统计
        self.tab_widget.addTab(self.create_basic_stats_tab(), "基础统计")

        # 数值分析
        self.tab_widget.addTab(self.create_numeric_analysis_tab(), "数值分析")

        # 设备分布
        self.tab_widget.addTab(self.create_device_distribution_tab(), "设备分布")

        # 工艺分析
        self.tab_widget.addTab(self.create_process_analysis_tab(), "工艺分析")

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def create_basic_stats_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 数据概览
        info_group = QGroupBox("数据概览")
        info_layout = QVBoxLayout(info_group)

        self.basic_info_label = QLabel()
        info_layout.addWidget(self.basic_info_label)
        layout.addWidget(info_group)

        # 基础统计表
        self.basic_stats_table = QTableWidget()
        layout.addWidget(self.basic_stats_table)

        return widget

    def create_numeric_analysis_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 数值统计表
        self.numeric_stats_table = QTableWidget()
        layout.addWidget(self.numeric_stats_table)

        # 分布图
        self.distribution_plot = pg.PlotWidget()
        self.distribution_plot.setBackground("w")
        self.distribution_plot.setLabel("left", "频次")
        self.distribution_plot.setLabel("bottom", "数值")
        layout.addWidget(self.distribution_plot)

        return widget

    def create_device_distribution_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.device_stats_table = QTableWidget()
        layout.addWidget(self.device_stats_table)

        return widget

    def create_process_analysis_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.process_stats_table = QTableWidget()
        layout.addWidget(self.process_stats_table)

        return widget

    def calculate_statistics(self):
        """计算所有统计数据"""
        if not self.data:
            return

        self.calculate_basic_info()
        self.calculate_numeric_stats()
        self.calculate_device_stats()
        self.calculate_process_stats()
        self.create_distribution_plots()

    def calculate_basic_info(self):
        """计算基础信息"""
        total_records = len(self.data)

        # 时间范围
        timestamps = [
            r.get("data_timestamp") for r in self.data if r.get("data_timestamp")
        ]
        time_range = ""
        if timestamps:
            min_time = min(timestamps)
            max_time = max(timestamps)
            time_range = f"{min_time} ~ {max_time}"

        # 设备统计
        devices = set(r.get("device_id") for r in self.data if r.get("device_id"))
        device_count = len(devices)

        # 工艺统计
        recipes = set(r.get("recipe") for r in self.data if r.get("recipe"))
        recipe_count = len(recipes)

        info_text = f"""
总记录数: {total_records}
时间范围: {time_range}
设备数量: {device_count}
工艺数量: {recipe_count}
        """.strip()

        self.basic_info_label.setText(info_text)

    def calculate_numeric_stats(self):
        """计算数值统计"""
        stats_data = []

        for field in self.numeric_fields:
            values = []
            for record in self.data:
                val = record.get(field)
                if val is not None:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        continue

            if values:
                values_array = np.array(values)
                stats = {
                    "field": field,
                    "count": len(values),
                    "mean": np.mean(values_array),
                    "std": np.std(values_array),
                    "min": np.min(values_array),
                    "max": np.max(values_array),
                    "median": np.median(values_array),
                    "q25": np.percentile(values_array, 25),
                    "q75": np.percentile(values_array, 75),
                }
                stats_data.append(stats)

        # 填充表格
        self.numeric_stats_table.setColumnCount(9)
        self.numeric_stats_table.setHorizontalHeaderLabels(
            [
                "参数",
                "计数",
                "均值",
                "标准差",
                "最小值",
                "最大值",
                "中位数",
                "25%",
                "75%",
            ]
        )
        self.numeric_stats_table.setRowCount(len(stats_data))

        for row, stats in enumerate(stats_data):
            self.numeric_stats_table.setItem(row, 0, QTableWidgetItem(stats["field"]))
            self.numeric_stats_table.setItem(
                row, 1, QTableWidgetItem(str(stats["count"]))
            )
            self.numeric_stats_table.setItem(
                row, 2, QTableWidgetItem(f"{stats['mean']:.3f}")
            )
            self.numeric_stats_table.setItem(
                row, 3, QTableWidgetItem(f"{stats['std']:.3f}")
            )
            self.numeric_stats_table.setItem(
                row, 4, QTableWidgetItem(f"{stats['min']:.3f}")
            )
            self.numeric_stats_table.setItem(
                row, 5, QTableWidgetItem(f"{stats['max']:.3f}")
            )
            self.numeric_stats_table.setItem(
                row, 6, QTableWidgetItem(f"{stats['median']:.3f}")
            )
            self.numeric_stats_table.setItem(
                row, 7, QTableWidgetItem(f"{stats['q25']:.3f}")
            )
            self.numeric_stats_table.setItem(
                row, 8, QTableWidgetItem(f"{stats['q75']:.3f}")
            )

        self.numeric_stats_table.resizeColumnsToContents()

    def calculate_device_stats(self):
        """计算设备统计"""
        device_stats = {}

        for record in self.data:
            device_id = record.get("device_id", "Unknown")
            device_type = record.get("device_type", "Unknown")

            if device_id not in device_stats:
                device_stats[device_id] = {
                    "device_type": device_type,
                    "record_count": 0,
                    "recipes": set(),
                    "lots": set(),
                    "wafers": set(),
                }

            device_stats[device_id]["record_count"] += 1

            if record.get("recipe"):
                device_stats[device_id]["recipes"].add(record["recipe"])
            if record.get("lot_number"):
                device_stats[device_id]["lots"].add(record["lot_number"])
            if record.get("wafer_id"):
                device_stats[device_id]["wafers"].add(record["wafer_id"])

        # 填充设备统计表
        self.device_stats_table.setColumnCount(6)
        self.device_stats_table.setHorizontalHeaderLabels(
            ["设备ID", "设备类型", "记录数", "工艺数", "批次数", "晶圆数"]
        )
        self.device_stats_table.setRowCount(len(device_stats))

        for row, (device_id, stats) in enumerate(device_stats.items()):
            self.device_stats_table.setItem(row, 0, QTableWidgetItem(device_id))
            self.device_stats_table.setItem(
                row, 1, QTableWidgetItem(stats["device_type"])
            )
            self.device_stats_table.setItem(
                row, 2, QTableWidgetItem(str(stats["record_count"]))
            )
            self.device_stats_table.setItem(
                row, 3, QTableWidgetItem(str(len(stats["recipes"])))
            )
            self.device_stats_table.setItem(
                row, 4, QTableWidgetItem(str(len(stats["lots"])))
            )
            self.device_stats_table.setItem(
                row, 5, QTableWidgetItem(str(len(stats["wafers"])))
            )

        self.device_stats_table.resizeColumnsToContents()

    def calculate_process_stats(self):
        """计算工艺统计"""
        process_stats = {}

        for record in self.data:
            recipe = record.get("recipe", "Unknown")
            step = record.get("step", "Unknown")
            process_key = f"{recipe}/{step}"

            if process_key not in process_stats:
                process_stats[process_key] = {
                    "record_count": 0,
                    "devices": set(),
                    "lots": set(),
                    "wafers": set(),
                }

            process_stats[process_key]["record_count"] += 1

            if record.get("device_id"):
                process_stats[process_key]["devices"].add(record["device_id"])
            if record.get("lot_number"):
                process_stats[process_key]["lots"].add(record["lot_number"])
            if record.get("wafer_id"):
                process_stats[process_key]["wafers"].add(record["wafer_id"])

        # 填充工艺统计表
        self.process_stats_table.setColumnCount(5)
        self.process_stats_table.setHorizontalHeaderLabels(
            ["工艺/步骤", "记录数", "设备数", "批次数", "晶圆数"]
        )
        self.process_stats_table.setRowCount(len(process_stats))

        for row, (process_key, stats) in enumerate(process_stats.items()):
            self.process_stats_table.setItem(row, 0, QTableWidgetItem(process_key))
            self.process_stats_table.setItem(
                row, 1, QTableWidgetItem(str(stats["record_count"]))
            )
            self.process_stats_table.setItem(
                row, 2, QTableWidgetItem(str(len(stats["devices"])))
            )
            self.process_stats_table.setItem(
                row, 3, QTableWidgetItem(str(len(stats["lots"])))
            )
            self.process_stats_table.setItem(
                row, 4, QTableWidgetItem(str(len(stats["wafers"])))
            )

        self.process_stats_table.resizeColumnsToContents()

    def create_distribution_plots(self):
        """创建分布图"""
        colors = ["r", "g", "b", "orange"]

        for i, field in enumerate(self.numeric_fields):
            values = []
            for record in self.data:
                val = record.get(field)
                if val is not None:
                    try:
                        values.append(float(val))
                    except:
                        continue

            if values:
                # 创建直方图
                hist, bins = np.histogram(values, bins=20)
                self.distribution_plot.plot(
                    bins[:-1],
                    hist,
                    pen=pg.mkPen(colors[i % len(colors)], width=2),
                    name=field,
                )

        self.distribution_plot.addLegend()


import numpy as np
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QLabel,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QGridLayout,
)
from PySide6.QtCore import Qt
import pyqtgraph as pg


class TrendAnalysisDialog(QDialog):
    """趋势分析对话框"""

    def __init__(self, data: list, selected_params: list, parent=None):
        super().__init__(parent)
        self.data = data
        self.selected_params = selected_params

        self.setWindowTitle("趋势分析")
        self.setModal(True)
        self.resize(1000, 700)

        self.setup_ui()
        self.create_trend_plots()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 控制区域
        control_group = QGroupBox("显示控制")
        control_layout = QHBoxLayout(control_group)

        # 时间聚合选择
        control_layout.addWidget(QLabel("时间聚合:"))
        self.aggregation_combo = QComboBox()
        self.aggregation_combo.addItems(["原始数据", "按分钟", "按小时", "按天"])
        self.aggregation_combo.currentTextChanged.connect(self.update_plots)
        control_layout.addWidget(self.aggregation_combo)

        # 平滑处理
        self.smooth_checkbox = QCheckBox("平滑处理")
        self.smooth_checkbox.toggled.connect(self.update_plots)
        control_layout.addWidget(self.smooth_checkbox)

        control_layout.addStretch()

        layout.addWidget(control_group)

        # 图表区域
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.setLabel("left", "参数值")
        self.plot_widget.setLabel("bottom", "时间")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()
        layout.addWidget(self.plot_widget, 1)

        # 按钮区域
        btn_layout = QHBoxLayout()

        export_btn = QPushButton("导出图表")
        export_btn.clicked.connect(self.export_chart)
        btn_layout.addWidget(export_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def create_trend_plots(self):
        """创建趋势图"""
        colors = ["red", "blue", "green", "orange", "purple"]

        for i, param in enumerate(self.selected_params):
            # 提取时间序列数据
            time_data = []
            value_data = []

            for record in self.data:
                timestamp = record.get("data_timestamp")
                value = record.get(param)

                if timestamp and value is not None:
                    try:
                        time_data.append(timestamp.timestamp())
                        value_data.append(float(value))
                    except:
                        continue

            if time_data and value_data:
                # 按时间排序
                sorted_data = sorted(zip(time_data, value_data))
                times, values = zip(*sorted_data)

                # 绘制曲线
                self.plot_widget.plot(
                    times,
                    values,
                    pen=pg.mkPen(colors[i % len(colors)], width=2),
                    name=param,
                )

    def update_plots(self):
        """更新图表"""
        self.plot_widget.clear()
        self.create_trend_plots()

    def export_chart(self):
        """导出图表"""
        # 实现图表导出功能
        pass


import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
)
from PySide6.QtCore import Qt
import pyqtgraph as pg


class CorrelationAnalysisDialog(QDialog):
    """相关性分析对话框"""

    def __init__(self, data: list, selected_params: list, parent=None):
        super().__init__(parent)
        self.data = data
        self.selected_params = selected_params

        self.setWindowTitle("相关性分析")
        self.setModal(True)
        self.resize(800, 600)

        self.setup_ui()
        self.calculate_correlations()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 相关性矩阵表格
        layout.addWidget(QLabel("参数相关性矩阵:"))
        self.correlation_table = QTableWidget()
        layout.addWidget(self.correlation_table)

        # 散点图
        layout.addWidget(QLabel("散点图:"))
        self.scatter_plot = pg.PlotWidget()
        self.scatter_plot.setBackground("w")
        self.scatter_plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.scatter_plot)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def calculate_correlations(self):
        """计算参数相关性"""
        # 提取参数数据
        param_data = {}
        for param in self.selected_params:
            values = []
            for record in self.data:
                val = record.get(param)
                if val is not None:
                    try:
                        values.append(float(val))
                    except:
                        values.append(np.nan)
                else:
                    values.append(np.nan)
            param_data[param] = np.array(values)

        # 计算相关性矩阵
        param_count = len(self.selected_params)
        correlation_matrix = np.zeros((param_count, param_count))

        for i, param1 in enumerate(self.selected_params):
            for j, param2 in enumerate(self.selected_params):
                if i == j:
                    correlation_matrix[i, j] = 1.0
                else:
                    # 计算皮尔逊相关系数
                    data1 = param_data[param1]
                    data2 = param_data[param2]

                    # 移除NaN值
                    mask = ~(np.isnan(data1) | np.isnan(data2))
                    if np.sum(mask) > 1:
                        corr = np.corrcoef(data1[mask], data2[mask])[0, 1]
                        correlation_matrix[i, j] = corr
                    else:
                        correlation_matrix[i, j] = 0.0

        # 填充相关性表格
        self.correlation_table.setRowCount(param_count)
        self.correlation_table.setColumnCount(param_count)
        self.correlation_table.setHorizontalHeaderLabels(self.selected_params)
        self.correlation_table.setVerticalHeaderLabels(self.selected_params)

        for i in range(param_count):
            for j in range(param_count):
                corr_value = correlation_matrix[i, j]
                item = QTableWidgetItem(f"{corr_value:.3f}")

                # 根据相关性强度设置颜色
                if abs(corr_value) > 0.7:
                    item.setBackground(Qt.red if corr_value > 0 else Qt.blue)
                elif abs(corr_value) > 0.4:
                    item.setBackground(Qt.yellow)

                self.correlation_table.setItem(i, j, item)

        self.correlation_table.resizeColumnsToContents()

        # 绘制散点图 (选择前两个参数)
        if len(self.selected_params) >= 2:
            param1, param2 = self.selected_params[0], self.selected_params[1]
            data1 = param_data[param1]
            data2 = param_data[param2]

            # 移除NaN值
            mask = ~(np.isnan(data1) | np.isnan(data2))
            valid_data1 = data1[mask]
            valid_data2 = data2[mask]

            if len(valid_data1) > 0:
                self.scatter_plot.plot(
                    valid_data1,
                    valid_data2,
                    pen=None,
                    symbol="o",
                    symbolSize=5,
                    symbolBrush="blue",
                )
                self.scatter_plot.setLabel("left", param2)
                self.scatter_plot.setLabel("bottom", param1)
