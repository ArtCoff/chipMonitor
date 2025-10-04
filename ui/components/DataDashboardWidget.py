import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QFrame,
    QHeaderView,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from datetime import datetime
from collections import deque


class DashboardWidget(QWidget):
    """实时数据仪表盘 - 显示选定设备的全部数据"""

    device_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DashboardWidget")

        # 当前显示的设备
        self.current_device = None

        # 数据缓存 - 最多保留500行
        self.data_cache = deque(maxlen=500)

        # 数据列名映射（用于显示友好名称）
        self.column_mapping = {
            "timestamp": "时间戳",
            "temperature": "温度(°C)",
            "pressure": "压力(Torr)",
            "rf_power": "RF功率(W)",
            "endpoint": "终点信号",
            "recipe": "工艺",
            "step": "步骤",
            "lot_id": "批次号",
            "wafer_id": "晶圆号",
            "channel": "通道",
        }

        self.setup_ui()

    def setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 头部信息
        header_frame = self.create_header()
        layout.addWidget(header_frame)

        # 数据表格
        self.data_table = self.create_data_table()
        layout.addWidget(self.data_table, 1)

        # 底部控制
        controls_frame = self.create_controls()
        layout.addWidget(controls_frame)

    def create_header(self) -> QWidget:
        """创建头部信息显示"""
        frame = QFrame()
        frame.setObjectName("dashboardHeader")
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setMaximumHeight(60)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        # 设备信息
        self.device_label = QLabel("未选择设备")
        self.device_label.setObjectName("deviceLabel")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.device_label.setFont(font)
        layout.addWidget(self.device_label)

        layout.addStretch()

        # 数据统计
        self.stats_label = QLabel("数据行数: 0")
        self.stats_label.setObjectName("statsLabel")
        layout.addWidget(self.stats_label)

        return frame

    def create_data_table(self) -> QTableWidget:
        """创建数据表格"""
        table = QTableWidget()
        table.setObjectName("dashboardTable")

        # 表格设置
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSortingEnabled(False)  # 禁用排序，保持时间顺序
        table.setWordWrap(False)

        # 表头设置
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)

        # 垂直表头设置
        v_header = table.verticalHeader()
        v_header.setVisible(False)

        # 初始列设置
        self.setup_table_columns(table, [])

        return table

    def create_controls(self) -> QWidget:
        """创建底部控制按钮"""
        frame = QFrame()
        frame.setObjectName("dashboardControls")
        frame.setMaximumHeight(50)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addStretch()

        # 清空数据按钮
        clear_btn = QPushButton("🗑️ 清空数据")
        clear_btn.setObjectName("clearDataBtn")
        clear_btn.clicked.connect(self.clear_data)
        layout.addWidget(clear_btn)

        # 导出数据按钮
        export_btn = QPushButton("📤 导出数据")
        export_btn.setObjectName("exportDataBtn")
        export_btn.clicked.connect(self.export_data)
        layout.addWidget(export_btn)

        return frame

    def setup_table_columns(self, table: QTableWidget, data_keys: list):
        """根据数据键设置表格列"""
        # 基础列：时间戳
        columns = ["timestamp"]

        # 添加数据列（排序以便显示）
        data_columns = [key for key in sorted(data_keys) if key != "timestamp"]
        columns.extend(data_columns)

        # 设置表格列数和表头
        table.setColumnCount(len(columns))

        headers = []
        for col in columns:
            header_name = self.column_mapping.get(col, col)
            headers.append(header_name)

        table.setHorizontalHeaderLabels(headers)

        # 存储列映射供后续使用
        self.current_columns = columns

        # 设置列宽
        if "timestamp" in columns:
            timestamp_col = columns.index("timestamp")
            table.setColumnWidth(timestamp_col, 140)

    def set_device(self, device_id: str):
        """设置当前显示的设备"""
        if device_id == self.current_device:
            return

        self.current_device = device_id
        self.device_label.setText(f"设备: {device_id}")

        # 清空现有数据
        self.clear_data()

        self.logger.info(f"切换到设备: {device_id}")

    def update_device_data(self, device_data: dict):
        """更新设备数据"""
        if not self.current_device:
            return

        data_points = device_data.get("data_points", [])
        if not data_points:
            return

        # 获取最新的数据点
        latest_point = data_points[-1]

        # 检查是否需要更新表格结构
        data_keys = list(latest_point.keys())
        if not hasattr(self, "current_columns") or set(data_keys) != set(
            self.current_columns
        ):
            self.setup_table_columns(self.data_table, data_keys)

        # 添加新数据到缓存
        self.data_cache.append(latest_point)

        # 在表格顶部插入新行
        self.insert_data_row(latest_point)

        # 更新统计信息
        self.update_stats()

    def insert_data_row(self, data_point: dict):
        """在表格顶部插入新数据行"""
        # 在第0行插入新行
        self.data_table.insertRow(0)

        # 填充数据
        for col_idx, col_key in enumerate(self.current_columns):
            value = data_point.get(col_key, "")

            # 格式化时间戳
            if col_key == "timestamp" and isinstance(value, (int, float)):
                formatted_value = datetime.fromtimestamp(value).strftime("%H:%M:%S.%f")[
                    :-3
                ]
            else:
                formatted_value = str(value)

            # 创建表格项
            item = QTableWidgetItem(formatted_value)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 只读

            # 新数据行高亮
            if col_key == "timestamp":
                item.setBackground(Qt.lightGray)

            self.data_table.setItem(0, col_idx, item)

        # 限制表格行数，移除超出的行
        max_rows = 200
        while self.data_table.rowCount() > max_rows:
            self.data_table.removeRow(self.data_table.rowCount() - 1)

    def update_stats(self):
        """更新统计信息"""
        row_count = self.data_table.rowCount()
        cache_count = len(self.data_cache)
        self.stats_label.setText(f"显示: {row_count} 行 | 缓存: {cache_count} 行")

    @Slot()
    def clear_data(self):
        """清空所有数据"""
        self.data_table.setRowCount(0)
        self.data_cache.clear()
        self.update_stats()
        self.logger.info("已清空仪表盘数据")

    @Slot()
    def export_data(self):
        """导出数据（简单实现）"""
        if not self.data_cache:
            self.logger.warning("没有数据可导出")
            return

        try:
            # 生成CSV格式数据
            csv_lines = []

            # 表头
            if hasattr(self, "current_columns"):
                headers = [
                    self.column_mapping.get(col, col) for col in self.current_columns
                ]
                csv_lines.append(",".join(headers))

            # 数据行
            for data_point in self.data_cache:
                row_data = []
                for col_key in self.current_columns:
                    value = data_point.get(col_key, "")
                    if col_key == "timestamp" and isinstance(value, (int, float)):
                        value = datetime.fromtimestamp(value).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    row_data.append(str(value))
                csv_lines.append(",".join(row_data))

            # 写入文件
            filename = f"dashboard_{self.current_device}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(csv_lines))

            self.logger.info(f"数据已导出到: {filename}")

        except Exception as e:
            self.logger.error(f"数据导出失败: {e}")

    def get_current_device(self) -> str:
        """获取当前设备ID"""
        return self.current_device

    def get_data_count(self) -> int:
        """获取当前数据行数"""
        return len(self.data_cache)
