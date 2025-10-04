import logging
import json
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QFormLayout,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSplitter,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QDateTimeEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QStatusBar,
    QFrame,
    QMessageBox,
    QFileDialog,
    QTextEdit,
    QDialog,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QThread
from PySide6.QtGui import QIcon, QFont, QColor

from core.database_manager import db_manager
from core.thread_pool import thread_pool, TaskType, TaskPriority
from utils.path import ICON_DIR
from ui.components.AnalysisWindowControl import AnalysisWindowControl


class RecordDetailDialog(QDialog):
    """记录详情对话框"""

    def __init__(self, record_data: dict, parent=None):
        super().__init__(parent)
        self.record_data = record_data
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("记录详情")
        self.setModal(True)
        self.resize(600, 500)

        layout = QVBoxLayout(self)

        # JSON格式显示
        json_text = QTextEdit()
        json_text.setReadOnly(True)
        json_content = json.dumps(
            self.record_data, ensure_ascii=False, indent=2, default=str
        )
        json_text.setPlainText(json_content)
        json_text.setFont(QFont("Courier New", 10))

        layout.addWidget(QLabel("记录详细信息:"))
        layout.addWidget(json_text)

        # 按钮
        button_layout = QHBoxLayout()

        copy_btn = QPushButton("复制到剪贴板")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(copy_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def copy_to_clipboard(self):
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        json_content = json.dumps(
            self.record_data, ensure_ascii=False, indent=2, default=str
        )
        clipboard.setText(json_content)


class HistoryDataWindow(QMainWindow):
    """历史数据查询窗口"""

    # 信号定义
    data_selected = Signal(list)  # 选中的数据
    chart_requested = Signal(list)  # 图表请求
    export_completed = Signal(str)  # 导出完成

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("HistoryDataWindow")

        # 状态变量
        self.current_data = []
        self.comparison_data = []
        self.current_query_task_id = None

        self.setup_ui()
        self.setup_connections()
        self.initialize_data()

        self.logger.info("历史数据查询窗口初始化完成")

    def setup_ui(self):
        self.setWindowTitle("历史数据分析 - ChipMonitor")
        self.setWindowIcon(QIcon(f"{ICON_DIR}/icon_analysis.png"))
        self.resize(1200, 800)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局 - 水平分割
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(8)

        # 创建主分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 左侧控制面板
        self.control_panel = AnalysisWindowControl()
        self.main_splitter.addWidget(self.control_panel)

        # 右侧数据显示区域
        self.main_splitter.addWidget(self.create_data_display_area())

        # 设置分割器比例
        self.main_splitter.setSizes([300, 1000])
        self.main_splitter.setCollapsible(0, False)  # 左侧不可折叠

        # 状态栏
        self.setup_status_bar()

    def create_data_display_area(self) -> QWidget:
        """创建右侧数据显示区域"""
        data_area = QWidget()
        layout = QVBoxLayout(data_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 创建数据表格分割器（上下两个表格）
        self.data_splitter = QSplitter(Qt.Vertical)
        self.data_splitter.setObjectName("dataSplitter")

        # 上方表格区域
        upper_table_widget = self.create_data_table_widget("主要数据", primary=True)
        self.data_splitter.addWidget(upper_table_widget)

        # 下方表格区域
        lower_table_widget = self.create_data_table_widget("对比数据", primary=False)
        self.data_splitter.addWidget(lower_table_widget)

        # 设置分割器比例
        self.data_splitter.setSizes([600, 300])
        layout.addWidget(self.data_splitter, 1)

        # 底部功能按钮区域
        layout.addWidget(self.create_bottom_function_buttons())

        return data_area

    def create_data_table_widget(self, title: str, primary: bool = True) -> QWidget:
        """创建数据表格组件"""
        table_widget = QWidget()
        table_widget.setObjectName("dataTableWidget")

        layout = QVBoxLayout(table_widget)

        # 表格标题栏
        title_layout = QHBoxLayout()

        title_label = QLabel(title)
        title_label.setObjectName("tableTitle")
        title_label.setFont(QFont("", 0, QFont.Bold))
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # 记录计数标签
        if primary:
            self.record_count_label = QLabel("记录数: 0")
            title_layout.addWidget(self.record_count_label)
        else:
            self.comparison_count_label = QLabel("对比记录: 0")
            title_layout.addWidget(self.comparison_count_label)

        layout.addLayout(title_layout)

        # 数据表格
        table = QTableWidget()
        if primary:
            self.data_table = table
            table.setObjectName("primaryDataTable")
        else:
            self.comparison_table = table
            table.setObjectName("comparisonDataTable")

        # 表格配置
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        layout.addWidget(table, 1)

        return table_widget

    def create_bottom_function_buttons(self) -> QFrame:
        """创建底部功能按钮区域"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setObjectName("bottomFunctionFrame")
        frame.setMaximumHeight(60)

        layout = QHBoxLayout(frame)

        # 左侧：表格操作按钮
        table_ops_layout = QHBoxLayout()

        self.copy_selected_button = QPushButton("📋 复制选中")
        self.copy_selected_button.setEnabled(False)
        self.copy_selected_button.setObjectName("tableOpButton")
        table_ops_layout.addWidget(self.copy_selected_button)

        self.select_all_rows_button = QPushButton("✅ 全选行")
        self.select_all_rows_button.setObjectName("tableOpButton")
        table_ops_layout.addWidget(self.select_all_rows_button)

        self.toggle_view_button = QPushButton("🔄 切换视图")
        self.toggle_view_button.setObjectName("tableOpButton")
        table_ops_layout.addWidget(self.toggle_view_button)

        layout.addLayout(table_ops_layout)

        layout.addStretch()

        # 右侧：数据处理按钮
        data_ops_layout = QHBoxLayout()

        self.filter_button = QPushButton("🔍 实时过滤")
        self.filter_button.setObjectName("dataOpButton")
        data_ops_layout.addWidget(self.filter_button)

        self.statistics_button = QPushButton("📊 统计分析")
        self.statistics_button.setEnabled(False)
        self.statistics_button.setObjectName("dataOpButton")
        data_ops_layout.addWidget(self.statistics_button)

        self.batch_process_button = QPushButton("⚡ 批量处理")
        self.batch_process_button.setEnabled(False)
        self.batch_process_button.setObjectName("dataOpButton")
        data_ops_layout.addWidget(self.batch_process_button)

        layout.addLayout(data_ops_layout)

        return frame

    def setup_status_bar(self):
        """设置状态栏"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # 连接状态
        self.connection_status_label = QLabel("● 未连接")
        self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
        status_bar.addWidget(self.connection_status_label)

        status_bar.addWidget(QLabel(" | "))

        # 查询状态
        self.query_status_label = QLabel("就绪")
        status_bar.addWidget(self.query_status_label)

        status_bar.addWidget(QLabel(" | "))

        # 选择计数
        self.selected_count_label = QLabel("已选择: 0 行")
        status_bar.addWidget(self.selected_count_label)

    def setup_connections(self):
        """设置信号连接"""
        # 查询控制信号
        self.control_panel.query_requested.connect(self.on_query_requested)
        self.control_panel.clear_requested.connect(self.on_clear_requested)
        self.control_panel.export_requested.connect(self.on_export_requested)
        self.control_panel.chart_requested.connect(self.on_chart_requested)
        self.control_panel.table_type_changed.connect(self.on_table_type_changed)
        self.control_panel.field_filter_changed.connect(self.on_field_filter_changed)

        # 主表格操作
        self.data_table.selectionModel().selectionChanged.connect(
            self.on_table_selection_changed
        )
        self.data_table.itemDoubleClicked.connect(self.on_table_item_double_clicked)

        # 底部按钮
        self.copy_selected_button.clicked.connect(self.on_copy_selected_clicked)
        self.select_all_rows_button.clicked.connect(self.on_select_all_rows_clicked)
        # 数据库连接状态
        db_manager.connection_changed.connect(self.on_database_connection_changed)

    def initialize_data(self):
        """初始化数据"""
        # 检查数据库连接
        if db_manager.is_connected():
            self.on_database_connection_changed(True, "数据库已连接")
        else:
            self.on_database_connection_changed(False, "数据库未连接")

    def setup_table_columns(self, table_type: str):
        """设置表格列"""
        self.data_table.clear()
        self.data_table.setRowCount(0)

        self.comparison_table.clear()
        self.comparison_table.setRowCount(0)

        # 根据表类型定义列
        if table_type == "telemetry_data":
            headers = [
                "ID",
                "设备ID",
                "通道",
                "数据源",
                "温度(°C)",
                "压力(Pa)",
                "RF功率(W)",
                "终点值",
                "湿度(%)",
                "振动(Hz)",
                "数据时间",
                "创建时间",
            ]
            self.table_fields[table_type] = [
                "id",
                "device_id",
                "channel",
                "source",
                "temperature",
                "pressure",
                "rf_power",
                "endpoint",
                "humidity",
                "vibration",
                "data_timestamp",
                "created_at",
            ]
        elif table_type == "alerts":
            headers = [
                "ID",
                "设备ID",
                "告警类型",
                "严重程度",
                "消息",
                "数据时间",
                "创建时间",
                "解决时间",
            ]
            self.table_fields[table_type] = [
                "id",
                "device_id",
                "alert_type",
                "severity",
                "message",
                "data_timestamp",
                "created_at",
                "resolved_at",
            ]
        elif table_type == "device_events":
            headers = ["ID", "设备ID", "事件类型", "严重程度", "数据时间", "创建时间"]
            self.table_fields[table_type] = [
                "id",
                "device_id",
                "event_type",
                "severity",
                "data_timestamp",
                "created_at",
            ]
        elif table_type == "error_logs":
            headers = [
                "ID",
                "设备ID",
                "错误类型",
                "错误代码",
                "消息",
                "严重程度",
                "数据时间",
                "创建时间",
            ]
            self.table_fields[table_type] = [
                "id",
                "device_id",
                "error_type",
                "error_code",
                "message",
                "severity",
                "data_timestamp",
                "created_at",
            ]
        else:
            headers = []
            self.table_fields[table_type] = []

        # 设置主表格列
        self.data_table.setColumnCount(len(headers))
        self.data_table.setHorizontalHeaderLabels(headers)

        # 设置对比表格列
        self.comparison_table.setColumnCount(len(headers))
        self.comparison_table.setHorizontalHeaderLabels(headers)

        # 设置列宽
        if headers:
            for table in [self.data_table, self.comparison_table]:
                header = table.horizontalHeader()
                header.resizeSection(0, 80)  # ID
                header.resizeSection(1, 120)  # 设备ID
                for i in range(2, len(headers)):
                    header.resizeSection(i, 100)

        self.logger.info(f"设置表格列: {table_type}, 列数: {len(headers)}")

    def update_field_list(self, table_type: str):
        """更新字段列表"""
        # 清空现有字段复选框
        for checkbox in self.field_checkboxes.values():
            checkbox.deleteLater()
        self.field_checkboxes.clear()

        # 获取字段列表
        fields = self.table_fields.get(table_type, [])

        # 添加字段复选框
        for field in fields:
            checkbox = QCheckBox(field)
            checkbox.setChecked(True)  # 默认全部选中
            checkbox.toggled.connect(self.on_field_filter_changed)

            self.field_filter_layout.addWidget(checkbox)
            self.field_checkboxes[field] = checkbox

    # === 槽函数实现 ===

    @Slot()
    def on_query_clicked(self, query_params: dict):
        """执行查询"""
        if not db_manager.is_connected():
            QMessageBox.warning(self, "错误", "数据库未连接！")
            return
            # 取消当前正在执行的查询任务
        if self.current_query_task_id:
            thread_pool.cancel_task(self.current_query_task_id)

        self.logger.info(f"开始执行查询: {self.current_table_type}")

        # 显示进度条
        self.control_panel.set_buttons_enabled(query_enabled=False)
        self.query_status_label.setText("查询中...")

        self.current_query_task_id = thread_pool.submit(
            TaskType.DATA_PROCESSING,
            self.execute_query_task,
            query_params,
            priority=TaskPriority.HIGH,
            callback=self.on_query_task_completed,
            timeout=30.0,  # 30秒超时
            max_retries=1,  # 重试1次
            task_id=f"history_query_{datetime.now().timestamp()}",
        )

    def execute_query_task(self, query_params: dict) -> dict:
        """执行查询任务 - 在线程池中运行"""
        try:
            table_type = query_params.get("table_type")
            start_time = query_params.get("start_time")
            end_time = query_params.get("end_time")
            limit = query_params.get("limit", 1000)
            order_desc = query_params.get("order_desc", True)

            # 根据表类型执行不同查询
            if table_type == "telemetry_data":
                results = db_manager.query_telemetry_data(
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                    order_desc=order_desc,
                )
            elif table_type == "alerts":
                results = db_manager.query_alerts(limit=limit)
            elif table_type == "device_events":
                results = db_manager.query_device_events(
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                )
            else:
                results = []

            return {
                "success": True,
                "data": results,
                "message": f"查询完成，获取 {len(results)} 条记录",
            }

        except Exception as e:
            self.logger.error(f"查询执行失败: {e}")
            return {"success": False, "error": str(e), "message": f"查询失败: {e}"}

    def on_query_task_completed(self, task_id: str, result: dict):
        """查询任务完成回调"""
        # 重置任务ID
        if self.current_query_task_id == task_id:
            self.current_query_task_id = None

        # 隐藏进度条
        # 恢复UI状态
        self.control_panel.set_buttons_enabled(query_enabled=True)

        if result.get("success", False):
            # 查询成功
            results = result.get("data", [])
            self.logger.info(f"查询完成，结果数量: {len(results)}")

            self.query_status_label.setText(f"查询完成 - {len(results)} 条记录")

            # 更新数据
            self.current_data = results
            self.populate_table_data(results)

            # 更新记录计数
            self.record_count_label.setText(f"记录数: {len(results)}")
            self.query_status_label.setText(f"查询完成 - {len(results)} 条记录")

            # 启用相关按钮
            has_data = len(results) > 0
            self.control_panel.set_buttons_enabled(
                query_enabled=True, data_buttons_enabled=has_data
            )
            self.statistics_button.setEnabled(has_data)
            self.statusBar().showMessage(result.get("message", "查询完成"), 5000)
        else:
            # 查询失败
            error_msg = result.get("error", "未知错误")
            self.logger.warning(f"查询失败: {error_msg}")

            self.query_status_label.setText("查询失败")
            QMessageBox.critical(self, "查询失败", error_msg)
            self.statusBar().showMessage(result.get("message", "查询失败"), 5000)

    def populate_table_data(self, data: list):
        """填充表格数据"""
        self.data_table.setRowCount(len(data))

        for row, record in enumerate(data):
            self.populate_table_row(self.data_table, row, record)

        # 自动调整列宽
        self.data_table.resizeColumnsToContents()

        self.logger.debug(f"表格数据填充完成，行数: {len(data)}")

    def populate_table_row(self, table: QTableWidget, row: int, record: dict):
        """填充表格行数据"""
        if self.current_table_type == "telemetry_data":
            fields = [
                ("id", str),
                ("device_id", str),
                ("channel", str),
                ("source", str),
                ("temperature", lambda x: f"{x:.2f}" if x is not None else "N/A"),
                ("pressure", lambda x: f"{x:.2f}" if x is not None else "N/A"),
                ("rf_power", lambda x: f"{x:.2f}" if x is not None else "N/A"),
                ("endpoint", lambda x: f"{x:.2f}" if x is not None else "N/A"),
                ("humidity", lambda x: f"{x:.1f}" if x is not None else "N/A"),
                ("vibration", lambda x: f"{x:.1f}" if x is not None else "N/A"),
                (
                    "data_timestamp",
                    lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "N/A",
                ),
                (
                    "created_at",
                    lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "N/A",
                ),
            ]
        elif self.current_table_type == "alerts":
            fields = [
                ("id", str),
                ("device_id", str),
                ("alert_type", str),
                ("severity", str),
                ("message", str),
                (
                    "data_timestamp",
                    lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "N/A",
                ),
                (
                    "created_at",
                    lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "N/A",
                ),
                (
                    "resolved_at",
                    lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "未解决",
                ),
            ]
        # ... 其他表类型的字段处理

        for col, (field, formatter) in enumerate(fields):
            value = record.get(field)
            if callable(formatter):
                display_value = formatter(value)
            else:
                display_value = formatter(value) if value is not None else "N/A"

            item = QTableWidgetItem(display_value)
            item.setData(Qt.UserRole, value)

            # 根据数据类型设置样式
            if field == "severity" and value:
                if value.lower() == "critical":
                    item.setBackground(QColor(255, 200, 200))
                elif value.lower() == "warning":
                    item.setBackground(QColor(255, 255, 200))
                elif value.lower() == "info":
                    item.setBackground(QColor(200, 255, 200))

            table.setItem(row, col, item)

    @Slot()
    def on_copy_selected_clicked(self):
        """复制选中行"""
        selected_data = self.get_selected_row_data()
        if not selected_data:
            QMessageBox.information(self, "提示", "请选择要复制的数据行！")
            return

        # 复制到剪贴板
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()

        # 转换为制表符分隔的文本
        text_data = []
        for record in selected_data:
            row_data = [
                str(record.get(field, ""))
                for field in self.table_fields[self.current_table_type]
            ]
            text_data.append("\t".join(row_data))

        clipboard.setText("\n".join(text_data))
        self.statusBar().showMessage(f"已复制 {len(selected_data)} 行数据", 3000)

    @Slot()
    def on_select_all_rows_clicked(self):
        """全选表格行"""
        self.data_table.selectAll()

    @Slot()
    def on_toggle_view_clicked(self):
        """切换视图模式"""
        # 简单的视图切换逻辑
        current_policy = self.data_table.selectionBehavior()
        if current_policy == QAbstractItemView.SelectRows:
            self.data_table.setSelectionBehavior(QAbstractItemView.SelectColumns)
            self.toggle_view_button.setText("🔄 行选择")
        else:
            self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.toggle_view_button.setText("🔄 列选择")

    @Slot()
    def on_filter_clicked(self):
        """实时过滤"""
        # 这里可以弹出过滤器对话框
        QMessageBox.information(self, "提示", "实时过滤功能开发中...")

    @Slot()
    def on_statistics_clicked(self):
        """统计分析"""
        if not self.current_data:
            return

        # 简单的统计信息
        stats = {
            "总记录数": len(self.current_data),
            "时间范围": f"{self.start_time_edit.dateTime().toString()} - {self.end_time_edit.dateTime().toString()}",
            "数据表": self.current_table_type,
        }

        stats_text = "\n".join([f"{k}: {v}" for k, v in stats.items()])
        QMessageBox.information(self, "统计信息", stats_text)

    @Slot()
    def on_clear_clicked(self):
        """清空数据"""
        self.data_table.setRowCount(0)
        self.comparison_table.setRowCount(0)
        self.current_data.clear()
        self.comparison_data.clear()

        self.record_count_label.setText("记录数: 0")
        self.comparison_count_label.setText("对比记录: 0")
        self.selected_count_label.setText("已选择: 0 行")

        # 禁用相关按钮
        self.export_button.setEnabled(False)
        self.chart_button.setEnabled(False)
        self.statistics_button.setEnabled(False)
        self.batch_process_button.setEnabled(False)
        self.copy_selected_button.setEnabled(False)

        self.statusBar().showMessage("数据已清空", 3000)
        self.logger.info("清空表格数据")

    @Slot(str)
    def on_table_type_changed(self, table_type: str):
        """表格类型变更"""
        self.current_table_type = table_type
        self.setup_table_columns(table_type)
        self.update_field_list(table_type)
        self.on_clear_clicked()

        self.logger.info(f"切换数据表类型: {table_type}")

    @Slot()
    def on_table_selection_changed(self):
        """表格选择变更"""
        selected_rows = self.data_table.selectionModel().selectedRows()
        selected_count = len(selected_rows)

        self.selected_count_label.setText(f"已选择: {selected_count} 行")
        self.copy_selected_button.setEnabled(selected_count > 0)

        # 获取选中的数据
        if selected_count > 0:
            selected_data = self.get_selected_row_data()
            self.data_selected.emit(selected_data)

        self.logger.debug(f"表格选择变更，选中行数: {selected_count}")

    @Slot(QTableWidgetItem)
    def on_table_item_double_clicked(self, item: QTableWidgetItem):
        """表格项双击"""
        if not item:
            return

        row = item.row()
        if row < len(self.current_data):
            record_data = self.current_data[row]

            # 显示记录详情对话框
            dialog = RecordDetailDialog(record_data, self)
            dialog.exec_()

            self.logger.info(f"双击表格项，行: {row}")

    def get_selected_row_data(self) -> list:
        """获取选中行的数据"""
        selected_data = []
        selected_rows = self.data_table.selectionModel().selectedRows()

        for index in selected_rows:
            row = index.row()
            if row < len(self.current_data):
                selected_data.append(self.current_data[row])

        return selected_data

    @Slot()
    def on_export_clicked(self):
        """导出数据"""
        if not self.current_data:
            QMessageBox.information(self, "提示", "没有可导出的数据！")
            return

        # 文件保存对话框
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "导出历史数据",
            f"history_data_{self.current_table_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV文件 (*.csv);;JSON文件 (*.json);;Excel文件 (*.xlsx)",
        )

        if not file_name:
            return

        try:
            if file_name.endswith(".csv"):
                self.export_to_csv(file_name)
            elif file_name.endswith(".json"):
                self.export_to_json(file_name)
            elif file_name.endswith(".xlsx"):
                self.export_to_excel(file_name)

            QMessageBox.information(self, "导出成功", f"数据已导出到:\n{file_name}")
            self.export_completed.emit(file_name)

        except Exception as e:
            self.logger.error(f"导出失败: {e}")
            QMessageBox.critical(self, "导出失败", str(e))

    def export_to_csv(self, file_path: str):
        """导出到CSV"""
        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            if not self.current_data:
                return

            # 获取字段名
            fieldnames = list(self.current_data[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # 写入标题行
            writer.writeheader()

            # 写入数据行
            for record in self.current_data:
                # 处理日期时间字段
                processed_record = {}
                for key, value in record.items():
                    if isinstance(value, datetime):
                        processed_record[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        processed_record[key] = value
                writer.writerow(processed_record)

        self.logger.info(f"CSV导出完成: {file_path}")

    def export_to_json(self, file_path: str):
        """导出到JSON"""
        export_data = {
            "table_type": self.current_table_type,
            "export_time": datetime.now().isoformat(),
            "record_count": len(self.current_data),
            "data": [],
        }

        # 处理数据
        for record in self.current_data:
            processed_record = {}
            for key, value in record.items():
                if isinstance(value, datetime):
                    processed_record[key] = value.isoformat()
                else:
                    processed_record[key] = value
            export_data["data"].append(processed_record)

        with open(file_path, "w", encoding="utf-8") as jsonfile:
            json.dump(export_data, jsonfile, ensure_ascii=False, indent=2)

        self.logger.info(f"JSON导出完成: {file_path}")

    def export_to_excel(self, file_path: str):
        """导出到Excel"""
        try:
            import pandas as pd

            df = pd.DataFrame(self.current_data)

            # 处理日期时间列
            for col in df.columns:
                if df[col].dtype == "object":
                    try:
                        df[col] = pd.to_datetime(df[col])
                    except:
                        pass

            # 导出到Excel
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=self.current_table_type, index=False)

            self.logger.info(f"Excel导出完成: {file_path}")

        except ImportError:
            QMessageBox.warning(self, "警告", "Excel导出需要安装pandas和openpyxl库")
        except Exception as e:
            self.logger.error(f"Excel导出失败: {e}")
            raise

    @Slot()
    def on_chart_clicked(self):
        """图表请求"""
        selected_data = self.get_selected_row_data()
        if not selected_data:
            QMessageBox.information(self, "提示", "请选择要制作图表的数据行！")
            return

        self.chart_requested.emit(selected_data)
        self.logger.info(f"请求制作图表，数据行数: {len(selected_data)}")

    @Slot()
    def on_field_filter_changed(self):
        """字段过滤变更"""
        self.apply_column_filters()

    def apply_column_filters(self):
        """应用列过滤器"""
        fields = self.table_fields.get(self.current_table_type, [])

        for i, field in enumerate(fields):
            if i < self.data_table.columnCount():
                checkbox = self.field_checkboxes.get(field)
                if checkbox:
                    visible = checkbox.isChecked()
                    self.data_table.setColumnHidden(i, not visible)
                    self.comparison_table.setColumnHidden(i, not visible)

    @Slot(bool)
    def on_auto_refresh_toggled(self, enabled: bool):
        """自动刷新切换"""
        if enabled:
            self.auto_refresh_timer.start()
            self.statusBar().showMessage("自动刷新已启用", 3000)
        else:
            self.auto_refresh_timer.stop()
            self.statusBar().showMessage("自动刷新已禁用", 3000)

        self.logger.info(f"自动刷新切换: {enabled}")

    @Slot()
    def on_auto_refresh_timer(self):
        """自动刷新定时器"""
        if db_manager.is_connected():
            self.on_query_clicked()
            self.logger.debug("自动刷新执行查询")

    @Slot(str)
    def on_device_filter_changed(self, text: str):
        """设备过滤变更"""
        pass

    @Slot()
    def on_date_range_changed(self):
        """日期范围变更"""
        pass

    @Slot(bool, str)
    def on_database_connection_changed(self, connected: bool, message: str):
        """数据库连接状态变更"""
        if connected:
            self.connection_status_label.setText("● 已连接")
            self.connection_status_label.setStyleSheet(
                "color: green; font-weight: bold;"
            )
            self.query_button.setEnabled(True)
            self.update_device_list()
        else:
            self.connection_status_label.setText("● 未连接")
            self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.query_button.setEnabled(False)

        self.statusBar().showMessage(message, 3000)
        self.logger.info(f"数据库连接状态变更: {connected} - {message}")

    def update_device_list(self):
        """更新设备列表"""
        if not db_manager.is_connected():
            return

        try:
            self.available_devices = []
            self.logger.debug(f"更新设备列表，设备数量: {len(self.available_devices)}")
        except Exception as e:
            self.logger.error(f"更新设备列表失败: {e}")

    def show_window(self):
        """显示窗口"""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """关闭事件"""
        # 取消当前查询任务
        if self.current_query_task_id:
            thread_pool.cancel_task(self.current_query_task_id)

        # 停止定时器
        self.auto_refresh_timer.stop()

        self.logger.info("历史数据查询窗口关闭")
        event.accept()
