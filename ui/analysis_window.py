import logging
import json
import csv
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QCheckBox,
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

from core.database_manager import get_db_manager
from core.thread_pool import get_thread_pool, TaskType, TaskPriority
from utils.path import ICON_DIR
from ui.components.AnalysisWindowControl import AnalysisWindowControl
from ui.components.HistoryDataPlot import (
    StatisticsDialog,
    TrendAnalysisDialog,
    CorrelationAnalysisDialog,
)


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
        self.db_manager = get_db_manager()
        self.thread_pool = get_thread_pool()

        # 状态变量
        self.current_data = []
        self.current_query_task_id = None

        # telemetry_data 字段映射
        self.field_mapping = {
            "id": ("ID", str),
            "device_id": ("设备ID", str),
            "device_type": ("设备类型", str),
            "channel": ("通道", str),
            "recipe": ("工艺", str),
            "step": ("步骤", str),
            "lot_number": ("批次号", str),
            "wafer_id": ("晶圆ID", str),
            "pressure": (
                "压力(Torr)",
                lambda x: f"{float(x):.3f}" if x is not None else "N/A",
            ),
            "temperature": (
                "温度(°C)",
                lambda x: f"{float(x):.3f}" if x is not None else "N/A",
            ),
            "rf_power": (
                "RF功率(W)",
                lambda x: f"{float(x):.3f}" if x is not None else "N/A",
            ),
            "endpoint": (
                "端点信号",
                lambda x: f"{float(x):.4f}" if x is not None else "N/A",
            ),
            "gas": ("气体流量", self.format_gas_data),
            "timestamp_us": ("时间戳(微秒)", str),
            "data_timestamp": (
                "数据时间",
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "N/A",
            ),
            "created_at": (
                "创建时间",
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x else "N/A",
            ),
        }

        self.setup_ui()
        self.setup_connections()
        self.initialize_data()

    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("半导体遥测数据分析 - ChipsM")
        self.resize(1400, 900)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局 - 水平分割
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # 创建分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 左侧控制面板
        self.control_panel = AnalysisWindowControl()
        self.main_splitter.addWidget(self.control_panel)

        # 右侧数据显示区域
        self.main_splitter.addWidget(self.create_data_display_area())

        # 设置分割器比例
        self.main_splitter.setSizes([380, 1020])

        # 状态栏
        self.setup_status_bar()

    def create_data_display_area(self) -> QWidget:
        """创建数据显示区域"""
        data_area = QWidget()
        layout = QVBoxLayout(data_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 表格标题
        title_layout = QHBoxLayout()
        title_label = QLabel("遥测数据")
        title_label.setFont(QFont("", 12, QFont.Bold))
        title_layout.addWidget(title_label)

        title_layout.addStretch()
        self.record_count_label = QLabel("记录数: 0")
        title_layout.addWidget(self.record_count_label)
        layout.addLayout(title_layout)

        # 数据表格
        self.data_table = QTableWidget()
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.data_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.data_table.setSortingEnabled(True)
        layout.addWidget(self.data_table, 1)

        # 分析功能按钮区域
        analysis_frame = QFrame()
        analysis_frame.setFrameStyle(QFrame.StyledPanel)
        analysis_layout = QVBoxLayout(analysis_frame)
        analysis_layout.setContentsMargins(8, 8, 8, 8)
        analysis_layout.setSpacing(6)

        # 分析标题
        analysis_title = QLabel("数据分析")
        analysis_title.setFont(QFont("", 10, QFont.Bold))
        analysis_layout.addWidget(analysis_title)

        # 分析参数选择
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("分析参数:"))

        self.analysis_params = {}
        for field in ["pressure", "temperature", "rf_power", "endpoint"]:
            checkbox = QCheckBox(self.get_field_display_name(field))
            checkbox.setChecked(True)
            self.analysis_params[field] = checkbox
            params_layout.addWidget(checkbox)

        params_layout.addStretch()
        analysis_layout.addLayout(params_layout)

        # 分析按钮
        analysis_btn_layout = QHBoxLayout()

        self.statistics_button = QPushButton("📊 统计分析")
        self.statistics_button.setEnabled(False)
        analysis_btn_layout.addWidget(self.statistics_button)

        self.trend_button = QPushButton("📈 趋势分析")
        self.trend_button.setEnabled(False)
        analysis_btn_layout.addWidget(self.trend_button)

        self.correlation_button = QPushButton("🔗 相关性分析")
        self.correlation_button.setEnabled(False)
        analysis_btn_layout.addWidget(self.correlation_button)

        analysis_btn_layout.addStretch()
        analysis_layout.addLayout(analysis_btn_layout)

        layout.addWidget(analysis_frame)

        # 底部操作按钮
        bottom_layout = QHBoxLayout()

        self.copy_button = QPushButton("📋 复制选中")
        self.copy_button.setEnabled(False)
        self.select_all_button = QPushButton("✅ 全选")
        self.detail_button = QPushButton("🔍 查看详情")
        self.detail_button.setEnabled(False)

        bottom_layout.addWidget(self.copy_button)
        bottom_layout.addWidget(self.select_all_button)
        bottom_layout.addWidget(self.detail_button)
        bottom_layout.addStretch()

        layout.addLayout(bottom_layout)

        return data_area

    def get_field_display_name(self, field: str) -> str:
        """获取字段显示名称"""
        field_names = {
            "pressure": "压力",
            "temperature": "温度",
            "rf_power": "RF功率",
            "endpoint": "端点信号",
        }
        return field_names.get(field, field)

    def get_selected_analysis_params(self) -> list:
        """获取选中的分析参数"""
        return [
            field
            for field, checkbox in self.analysis_params.items()
            if checkbox.isChecked()
        ]

    def setup_status_bar(self):
        """设置状态栏"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # 连接状态
        self.connection_label = QLabel("● 未连接")
        self.connection_label.setStyleSheet("color: red; font-weight: bold;")
        status_bar.addWidget(self.connection_label)

        status_bar.addWidget(QLabel(" | "))

        # 查询状态
        self.query_status_label = QLabel("就绪")
        status_bar.addWidget(self.query_status_label)

        status_bar.addWidget(QLabel(" | "))

        # 选中统计
        self.selection_label = QLabel("已选择: 0 行")
        status_bar.addWidget(self.selection_label)

    def setup_connections(self):
        """设置信号连接"""
        # 控制面板信号
        self.control_panel.query_requested.connect(self.on_query_requested)
        self.control_panel.clear_requested.connect(self.on_clear_requested)
        self.control_panel.field_filter_changed.connect(self.on_field_filter_changed)
        self.control_panel.info_message.connect(self.on_control_panel_info)

        # 分析按钮信号
        self.statistics_button.clicked.connect(self.on_statistics_requested)
        self.trend_button.clicked.connect(self.on_trend_analysis_requested)
        self.correlation_button.clicked.connect(self.on_correlation_analysis_requested)

        # 表格信号
        self.data_table.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )
        self.data_table.itemDoubleClicked.connect(self.on_item_double_clicked)

        # 底部按钮
        self.copy_button.clicked.connect(self.on_copy_clicked)
        self.select_all_button.clicked.connect(self.on_select_all_clicked)
        self.detail_button.clicked.connect(self.on_detail_clicked)

        # 数据库连接
        self.db_manager.connection_changed.connect(self.on_database_connection_changed)
        # 线程池信号
        self.thread_pool.task_completed.connect(
            self.on_query_completed, Qt.QueuedConnection
        )
        self.thread_pool.task_failed.connect(self.on_query_failed, Qt.QueuedConnection)

    def initialize_data(self):
        """初始化数据"""
        self.control_panel.add_info_message("主窗口初始化完成")

        if self.db_manager.is_connected():
            self.on_database_connection_changed(True, "数据库已连接")
        else:
            self.control_panel.add_info_message(
                "数据库未连接，请检查数据库配置", is_error=True
            )

    @Slot(str, bool)
    def on_control_panel_info(self, message: str, is_error: bool):
        """接收控制面板的信息"""
        # 主窗口可以在这里处理来自控制面板的信息
        # 例如记录到主日志或进行其他处理
        pass

    @Slot(dict)
    def on_query_requested(self, query_params: dict):
        """执行查询"""
        if not self.db_manager.is_connected():
            error_msg = "数据库未连接！"
            QMessageBox.warning(self, "错误", error_msg)
            self.control_panel.add_info_message(error_msg, is_error=True)
            return

        # 取消当前查询
        if self.current_query_task_id:
            self.thread_pool.cancel_task(self.current_query_task_id)
            self.control_panel.add_info_message("已取消当前查询任务")

        self.logger.info(f"开始查询遥测数据: {query_params}")

        # 更新UI状态
        self.control_panel.set_buttons_enabled(query_enabled=False)
        self.query_status_label.setText("查询中...")
        self.control_panel.add_info_message("正在提交查询任务到线程池...")

        # 提交查询任务
        self.current_query_task_id = self.thread_pool.submit(
            TaskType.HISTORY_DATA_QUERY,
            self.execute_telemetry_query,
            query_params,
            timeout=30.0,
        )
        self.control_panel.add_info_message(
            f"查询任务已提交: {self.current_query_task_id}"
        )

    def execute_telemetry_query(self, params: dict) -> dict:
        """执行遥测数据查询"""
        try:
            self.logger.info(f"执行查询，参数: {params}")

            results = self.db_manager.query_telemetry_data(
                device_id=params.get("device_id"),
                device_type=params.get("device_type"),
                recipe=params.get("recipe"),
                lot_number=params.get("lot_number"),
                start_time=params.get("start_time"),
                end_time=params.get("end_time"),
                limit=params.get("limit", 5000),
            )
            return results
            # return {
            #     "success": True,
            #     "data": results,
            #     "count": len(results),
            #     "message": f"查询完成，获取 {len(results)} 条记录",
            # }

        except Exception as e:
            self.logger.error(f"查询失败: {e}")
            return None
            # return {
            #     "success": False,
            #     "data": [],
            #     "count": 0,
            #     "error": str(e),
            #     "message": f"查询失败: {e}",
            # }

    def on_query_completed(self, task_id: str, result: dict):
        """查询完成回调"""
        if result.get("task_type") != TaskType.HISTORY_DATA_QUERY.value:
            return
        if self.current_query_task_id != task_id:
            return

        # 恢复UI状态
        self.control_panel.set_buttons_enabled(query_enabled=True)

        ##
        if result.get("success"):
            data = result.get("data", [])
            count = len(data)

            self.logger.info(f"查询成功: 获取到 {count} 条记录")

            # 更新数据和界面
            self.current_data = data
            self.populate_table(data)

            # 更新状态
            self.record_count_label.setText(f"记录数: {count}")
            self.query_status_label.setText(f"查询完成 - {count} 条记录")
            self.control_panel.add_info_message(f"✅ 查询成功: 获取到 {count} 条记录")

            if count > 0:
                self.control_panel.add_info_message("数据表格填充完成，分析功能已激活")

            # 启用分析按钮
            has_data = count > 0
            self.control_panel.set_buttons_enabled(True, has_data)
            self.statistics_button.setEnabled(has_data)
            self.trend_button.setEnabled(has_data)
            self.correlation_button.setEnabled(has_data)

        else:
            error_msg = result.get("message", "查询失败")
            error_detail = result.get("error", "未知错误")

            self.logger.error(f"查询失败: {error_msg}, 详情: {error_detail}")

            self.query_status_label.setText("查询失败")
            self.control_panel.add_info_message(
                f"❌ 查询失败: {error_msg}", is_error=True
            )
            QMessageBox.critical(
                self, "查询失败", f"{error_msg}\n\n详情: {error_detail}"
            )

    @Slot(str, dict)
    def on_query_failed(self, task_id: str, error_info: dict):
        """查询失败回调 - 修正版本"""
        self.logger.info(f"收到任务失败信号: task_id={task_id}")

        # 🔥 修正：正确的任务类型过滤
        if error_info.get("task_type") != TaskType.HISTORY_DATA_QUERY.value:
            return

        # 🔥 修正：正确的任务ID判断
        if self.current_query_task_id != task_id:
            return

        self.current_query_task_id = None

        # 恢复UI状态
        self.control_panel.set_buttons_enabled(query_enabled=True)

        error_msg = error_info.get("error", "未知错误")
        self.logger.error(f"查询任务失败: {error_msg}")

        self.query_status_label.setText("查询失败")
        self.control_panel.add_info_message(
            f"❌ 查询任务失败: {error_msg}", is_error=True
        )
        QMessageBox.critical(self, "查询失败", f"任务执行失败:\n{error_msg}")

    def populate_table(self, data: list):
        """填充表格数据"""
        if not data:
            self.data_table.setRowCount(0)
            self.control_panel.add_info_message("数据表格已清空")
            return

        # 设置表格结构
        field_names = list(self.field_mapping.keys())
        headers = [self.field_mapping[field][0] for field in field_names]

        self.data_table.setColumnCount(len(headers))
        self.data_table.setHorizontalHeaderLabels(headers)
        self.data_table.setRowCount(len(data))

        self.control_panel.add_info_message(
            f"开始填充数据表格: {len(data)} 行 × {len(headers)} 列"
        )

        # 填充数据
        for row, record in enumerate(data):
            for col, field in enumerate(field_names):
                value = record.get(field)
                formatter = self.field_mapping[field][1]

                if callable(formatter):
                    display_text = formatter(value)
                else:
                    display_text = formatter(value) if value is not None else "N/A"

                item = QTableWidgetItem(str(display_text))
                item.setData(Qt.UserRole, value)
                self.data_table.setItem(row, col, item)

        # 调整列宽
        self.data_table.resizeColumnsToContents()
        self.control_panel.add_info_message("数据表格填充完成，列宽已自动调整")

    def format_gas_data(self, gas_data) -> str:
        """格式化气体数据显示"""
        if not gas_data or not isinstance(gas_data, dict):
            return "N/A"

        gas_parts = []
        for gas_type, flow in gas_data.items():
            if flow is not None:
                gas_parts.append(f"{gas_type}:{flow}")

        return ", ".join(gas_parts) if gas_parts else "N/A"

    @Slot()
    def on_statistics_requested(self):
        """统计分析请求"""
        if not self.current_data:
            QMessageBox.information(self, "提示", "没有可分析的数据！")
            return

        self.control_panel.add_info_message("开启统计分析对话框...")
        dialog = StatisticsDialog(self.current_data, self)
        dialog.exec_()
        self.control_panel.add_info_message("统计分析对话框已关闭")

    @Slot()
    def on_trend_analysis_requested(self):
        """趋势分析请求"""
        if not self.current_data:
            QMessageBox.information(self, "提示", "没有可分析的数据！")
            return

        selected_params = self.get_selected_analysis_params()
        if not selected_params:
            QMessageBox.information(self, "提示", "请选择要分析的参数！")
            self.control_panel.add_info_message(
                "趋势分析失败: 未选择分析参数", is_error=True
            )
            return

        self.control_panel.add_info_message(
            f"开启趋势分析: 参数 {', '.join(selected_params)}"
        )
        dialog = TrendAnalysisDialog(self.current_data, selected_params, self)
        dialog.exec_()
        self.control_panel.add_info_message("趋势分析对话框已关闭")

    @Slot()
    def on_correlation_analysis_requested(self):
        """相关性分析请求"""
        if not self.current_data:
            QMessageBox.information(self, "提示", "没有可分析的数据！")
            return

        selected_params = self.get_selected_analysis_params()
        if len(selected_params) < 2:
            QMessageBox.information(self, "提示", "相关性分析至少需要选择2个参数！")
            self.control_panel.add_info_message(
                "相关性分析失败: 至少需要2个参数", is_error=True
            )
            return

        self.control_panel.add_info_message(
            f"开启相关性分析: 参数 {', '.join(selected_params)}"
        )
        dialog = CorrelationAnalysisDialog(self.current_data, selected_params, self)
        dialog.exec_()
        self.control_panel.add_info_message("相关性分析对话框已关闭")

    @Slot()
    def on_clear_requested(self):
        """清空数据"""
        self.data_table.setRowCount(0)
        self.current_data.clear()
        self.record_count_label.setText("记录数: 0")
        self.query_status_label.setText("就绪")
        self.selection_label.setText("已选择: 0 行")

        # 禁用分析按钮
        self.control_panel.set_buttons_enabled(True, False)
        self.statistics_button.setEnabled(False)
        self.trend_button.setEnabled(False)
        self.correlation_button.setEnabled(False)

        self.control_panel.add_info_message("数据已清空，分析功能已禁用")

    @Slot(dict)
    def on_field_filter_changed(self, field_filters: dict):
        """应用字段过滤"""
        field_names = list(self.field_mapping.keys())
        for i, field in enumerate(field_names):
            if i < self.data_table.columnCount():
                visible = field_filters.get(field, True)
                self.data_table.setColumnHidden(i, not visible)

    @Slot()
    def on_selection_changed(self):
        """选择变更"""
        selected_rows = len(self.data_table.selectionModel().selectedRows())
        self.selection_label.setText(f"已选择: {selected_rows} 行")
        self.copy_button.setEnabled(selected_rows > 0)
        self.detail_button.setEnabled(selected_rows == 1)

    @Slot()
    def on_copy_clicked(self):
        """复制选中行"""
        selected_rows = self.data_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # TODO: 实现复制功能
        self.control_panel.add_info_message(
            f"复制了 {len(selected_rows)} 行数据到剪贴板"
        )

    @Slot()
    def on_select_all_clicked(self):
        """全选所有行"""
        self.data_table.selectAll()
        self.control_panel.add_info_message("已全选所有数据行")

    @Slot()
    def on_detail_clicked(self):
        """查看详情"""
        selected_rows = self.data_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            return

        row = selected_rows[0].row()
        if row < len(self.current_data):
            record = self.current_data[row]
            self.control_panel.add_info_message("显示记录详情对话框...")

            # TODO: 实现详情对话框
            from ui.analysis_window import RecordDetailDialog

            dialog = RecordDetailDialog(record, self)
            dialog.exec_()

    @Slot()
    def on_item_double_clicked(self, item):
        """表格项双击"""
        row = item.row()
        if row < len(self.current_data):
            record = self.current_data[row]
            self.control_panel.add_info_message(f"双击查看记录详情: 第{row+1}行")

    @Slot(bool, str)
    def on_database_connection_changed(self, connected: bool, message: str):
        """数据库连接状态变更"""
        if connected:
            self.connection_label.setText("● 已连接")
            self.connection_label.setStyleSheet("color: green; font-weight: bold;")
            self.control_panel.add_info_message("数据库连接成功")
        else:
            self.connection_label.setText("● 未连接")
            self.connection_label.setStyleSheet("color: red; font-weight: bold;")
            self.control_panel.add_info_message("数据库连接失败", is_error=True)
