import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QColor
from datetime import datetime
import time
from collections import defaultdict


class DeviceOverviewTable(QWidget):
    """设备概览表格组件 - 显示所有设备状态信息"""

    device_selected = Signal(str)  # 设备选择信号
    refresh_requested = Signal()  # 刷新请求信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DeviceOverviewTable")
        self.device_data = {}

        # 初始化UI组件引用
        self.device_overview_table = None
        self.total_devices_label = None
        self.online_devices_label = None
        self.offline_devices_label = None

        self.setup_ui()
        self.logger.info("设备概览表格组件初始化完成")

    def setup_ui(self):
        """设置表格UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部工具栏
        layout.addWidget(self.create_toolbar())

        # 设备概览表格
        layout.addWidget(self.create_table())

        # 底部状态栏
        layout.addWidget(self.create_status_bar())

    def create_toolbar(self) -> QWidget:
        """创建顶部工具栏"""
        toolbar = QWidget()
        toolbar.setObjectName("deviceTableToolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_label = QLabel("设备状态概览")
        title_label.setObjectName("deviceTableTitle")
        title_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        layout.addWidget(title_label)

        layout.addStretch()

        # 刷新按钮
        refresh_btn = QPushButton("⟳ 刷新")
        refresh_btn.setObjectName("deviceTableRefreshBtn")
        refresh_btn.setMaximumWidth(80)
        refresh_btn.clicked.connect(self.on_refresh_clicked)
        layout.addWidget(refresh_btn)

        return toolbar

    def create_table(self) -> QWidget:
        """创建设备概览表格"""
        self.device_overview_table = QTableWidget()
        self.device_overview_table.setObjectName("deviceOverviewTable")
        self.device_overview_table.setAlternatingRowColors(True)
        self.device_overview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.device_overview_table.setSelectionMode(QTableWidget.SingleSelection)
        self.device_overview_table.verticalHeader().setVisible(False)

        # 🔥 设置表格列 - 优化的列设计
        columns = [
            ("设备ID", 100),
            ("类型", 80),
            ("状态", 70),
            ("工艺", 90),
            ("步骤", 50),
            ("批次", 70),
            ("晶圆", 70),
            ("温度", 70),
            ("压力", 70),
            ("功率", 60),
            ("端点", 60),
            ("更新", 70),
            ("数据", 50),
            ("时长", 70),
        ]

        self.device_overview_table.setColumnCount(len(columns))
        self.device_overview_table.setHorizontalHeaderLabels(
            [col[0] for col in columns]
        )

        # 设置列宽
        header = self.device_overview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        for i, (_, width) in enumerate(columns):
            self.device_overview_table.setColumnWidth(i, width)

        # 双击选择设备
        self.device_overview_table.itemDoubleClicked.connect(
            self.on_device_double_clicked
        )

        return self.device_overview_table

    def create_status_bar(self) -> QWidget:
        """创建底部状态栏"""
        status_bar = QWidget()
        status_bar.setObjectName("deviceTableStatusBar")
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(15)

        # 总设备数
        self.total_devices_label = QLabel("总设备: 0")
        self.total_devices_label.setObjectName("totalDevicesLabel")
        layout.addWidget(self.total_devices_label)

        # 分隔符
        sep1 = QLabel("│")
        sep1.setObjectName("separator")
        layout.addWidget(sep1)

        # 在线设备数
        self.online_devices_label = QLabel("在线: 0")
        self.online_devices_label.setObjectName("onlineDevicesLabel")
        layout.addWidget(self.online_devices_label)

        # 分隔符
        sep2 = QLabel("│")
        sep2.setObjectName("separator")
        layout.addWidget(sep2)

        # 离线设备数
        self.offline_devices_label = QLabel("离线: 0")
        self.offline_devices_label.setObjectName("offlineDevicesLabel")
        layout.addWidget(self.offline_devices_label)

        layout.addStretch()

        return status_bar

    # === 公共接口方法 ===

    def update_table_data(self, device_data: dict):
        """更新表格数据

        Args:
            device_data: 设备数据字典 {device_id: device_info}
        """
        try:
            self.device_data = device_data
            self.refresh_table()
        except Exception as e:
            self.logger.error(f"表格数据更新失败: {e}")

    def add_device_data(self, device_id: str, device_info: dict):
        """添加单个设备数据

        Args:
            device_id: 设备ID
            device_info: 设备信息
        """
        try:
            self.device_data[device_id] = device_info
            self.refresh_table()
        except Exception as e:
            self.logger.error(f"设备数据添加失败: {e}")

    def remove_device_data(self, device_id: str):
        """移除设备数据

        Args:
            device_id: 设备ID
        """
        try:
            if device_id in self.device_data:
                del self.device_data[device_id]
                self.refresh_table()
        except Exception as e:
            self.logger.error(f"设备数据移除失败: {e}")

    def clear_table_data(self):
        """清空表格数据"""
        try:
            self.device_data.clear()
            self.refresh_table()
        except Exception as e:
            self.logger.error(f"表格数据清空失败: {e}")

    def get_selected_device(self) -> str:
        """获取当前选中的设备ID"""
        try:
            current_row = self.device_overview_table.currentRow()
            if current_row >= 0:
                device_item = self.device_overview_table.item(current_row, 0)
                return device_item.text() if device_item else ""
            return ""
        except Exception as e:
            self.logger.error(f"获取选中设备失败: {e}")
            return ""

    # === 内部方法 ===

    def refresh_table(self):
        """刷新表格显示"""
        try:
            # 获取所有设备
            all_devices = list(self.device_data.keys())

            # 清空表格
            self.device_overview_table.setRowCount(0)

            if not all_devices:
                self.update_status_bar(0, 0, 0)
                return

            # 设置表格行数
            self.device_overview_table.setRowCount(len(all_devices))

            online_count = 0
            offline_count = 0

            # 填充表格数据
            for row, device_id in enumerate(sorted(all_devices)):
                device_info = self.device_data[device_id]

                # 判断设备在线状态
                is_online = self.is_device_online(device_info)
                if is_online:
                    online_count += 1
                else:
                    offline_count += 1

                # 填充行数据
                self.populate_table_row(row, device_id, device_info, is_online)

            # 更新状态栏
            self.update_status_bar(len(all_devices), online_count, offline_count)

            self.logger.debug(
                f"表格刷新完成: {len(all_devices)}设备, {online_count}在线, {offline_count}离线"
            )

        except Exception as e:
            self.logger.error(f"表格刷新失败: {e}")

    def is_device_online(self, device_info: dict) -> bool:
        """判断设备是否在线"""
        try:
            last_update = device_info.get("last_update")
            if not last_update:
                return False
            return (time.time() - last_update) < 30  # 30秒内认为在线
        except:
            return False

    def populate_table_row(
        self, row: int, device_id: str, device_info: dict, is_online: bool
    ):
        """填充表格行数据"""
        try:
            # 设备ID
            device_item = QTableWidgetItem(device_id)
            device_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.device_overview_table.setItem(row, 0, device_item)

            # 设备类型
            device_type = device_info.get("device_type", "UNKNOWN")
            type_item = QTableWidgetItem(device_type)
            self.device_overview_table.setItem(row, 1, type_item)

            # 连接状态
            status_text = "● 在线" if is_online else "● 离线"
            status_item = QTableWidgetItem(status_text)
            status_color = QColor("#10b981") if is_online else QColor("#ef4444")
            status_item.setForeground(status_color)
            status_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.device_overview_table.setItem(row, 2, status_item)

            # 当前工艺
            recipe_item = QTableWidgetItem(device_info.get("recipe", "--"))
            self.device_overview_table.setItem(row, 3, recipe_item)

            # 工艺步骤
            step_item = QTableWidgetItem(device_info.get("step", "--"))
            self.device_overview_table.setItem(row, 4, step_item)

            # 批次号
            lot_item = QTableWidgetItem(device_info.get("lot_id", "--"))
            self.device_overview_table.setItem(row, 5, lot_item)

            # 晶圆号
            wafer_item = QTableWidgetItem(device_info.get("wafer_id", "--"))
            self.device_overview_table.setItem(row, 6, wafer_item)

            # 🔥 传感器数据 - 显示最新值
            self.populate_sensor_data(row, device_info)

            # 最后更新时间
            update_time = self.format_update_time(device_info.get("last_update"))
            update_item = QTableWidgetItem(update_time)
            self.device_overview_table.setItem(row, 11, update_item)

            # 数据点数
            data_count = len(device_info.get("timestamps", []))
            count_item = QTableWidgetItem(str(data_count))
            self.device_overview_table.setItem(row, 12, count_item)

            # 运行时长
            runtime_text = self.format_runtime(device_info)
            runtime_item = QTableWidgetItem(runtime_text)
            self.device_overview_table.setItem(row, 13, runtime_item)

        except Exception as e:
            self.logger.error(f"行数据填充失败: {e}")

    def populate_sensor_data(self, row: int, device_info: dict):
        """填充传感器数据列"""
        try:
            # 温度
            temp_val = self.get_latest_sensor_value(
                device_info, "temperature", "{:.1f}"
            )
            temp_item = QTableWidgetItem(temp_val)
            self.device_overview_table.setItem(row, 7, temp_item)

            # 压力
            pressure_val = self.get_latest_sensor_value(
                device_info, "pressure", "{:.2f}"
            )
            pressure_item = QTableWidgetItem(pressure_val)
            self.device_overview_table.setItem(row, 8, pressure_item)

            # 功率
            power_val = self.get_latest_sensor_value(device_info, "rf_power", "{:.0f}")
            power_item = QTableWidgetItem(power_val)
            self.device_overview_table.setItem(row, 9, power_item)

            # 端点信号
            endpoint_val = self.get_latest_sensor_value(
                device_info, "endpoint", "{:.3f}"
            )
            endpoint_item = QTableWidgetItem(endpoint_val)
            self.device_overview_table.setItem(row, 10, endpoint_item)

        except Exception as e:
            self.logger.error(f"传感器数据填充失败: {e}")

    def get_latest_sensor_value(
        self, device_info: dict, sensor_key: str, format_str: str
    ) -> str:
        """获取最新的传感器值"""
        try:
            sensor_data = device_info.get(sensor_key)
            if sensor_data and len(sensor_data) > 0:
                latest_value = sensor_data[-1]
                return format_str.format(latest_value)
            return "--"
        except:
            return "--"

    def format_update_time(self, last_update) -> str:
        """格式化更新时间"""
        try:
            if last_update:
                return datetime.fromtimestamp(last_update).strftime("%H:%M:%S")
            return "--"
        except:
            return "--"

    def format_runtime(self, device_info: dict) -> str:
        """格式化运行时长"""
        try:
            timestamps = device_info.get("timestamps", [])
            if not timestamps:
                return "--"

            first_time = timestamps[0]
            last_time = device_info.get("last_update", first_time)
            runtime_seconds = last_time - first_time

            if runtime_seconds > 3600:  # 超过1小时
                hours = int(runtime_seconds // 3600)
                minutes = int((runtime_seconds % 3600) // 60)
                return f"{hours}h{minutes}m"
            elif runtime_seconds > 60:  # 超过1分钟
                minutes = int(runtime_seconds // 60)
                seconds = int(runtime_seconds % 60)
                return f"{minutes}m{seconds}s"
            else:
                return f"{runtime_seconds:.0f}s"

        except:
            return "--"

    def update_status_bar(self, total: int, online: int, offline: int):
        """更新状态栏统计信息"""
        try:
            self.total_devices_label.setText(f"总设备: {total}")
            self.online_devices_label.setText(f"在线: {online}")
            self.offline_devices_label.setText(f"离线: {offline}")
        except Exception as e:
            self.logger.error(f"状态栏更新失败: {e}")

    # === 信号处理方法 ===

    @Slot()
    def on_refresh_clicked(self):
        """处理刷新按钮点击"""
        try:
            self.refresh_requested.emit()
            self.refresh_table()
            self.logger.info("表格手动刷新")
        except Exception as e:
            self.logger.error(f"刷新处理失败: {e}")

    @Slot()
    def on_device_double_clicked(self, item):
        """处理设备双击选择"""
        try:
            if not item:
                return

            row = item.row()
            device_item = self.device_overview_table.item(row, 0)  # 第0列是设备ID

            if device_item:
                device_id = device_item.text()
                self.device_selected.emit(device_id)
                self.logger.info(f"双击选择设备: {device_id}")

        except Exception as e:
            self.logger.error(f"设备双击处理失败: {e}")

    def update_devices_data(self, devices_data: list):
        """兼容方法 - 将列表格式转换为字典格式"""
        try:
            if isinstance(devices_data, list):
                # 将列表格式转换为字典格式
                device_dict = {}
                for device in devices_data:
                    device_id = device.get("device_id")
                    if device_id:
                        device_dict[device_id] = device
                self.update_table_data(device_dict)
            else:
                # 如果已经是字典格式，直接调用
                self.update_table_data(devices_data)

        except Exception as e:
            self.logger.error(f"设备数据更新失败: {e}")

    def set_selected_device(self, device_id: str):
        """设置选中的设备"""
        try:
            for row in range(self.device_overview_table.rowCount()):
                item = self.device_overview_table.item(row, 0)
                if item and item.text() == device_id:
                    self.device_overview_table.selectRow(row)
                    break
        except Exception as e:
            self.logger.error(f"设置选中设备失败: {e}")

    def update_device_row(self, device_id: str, device_info: dict):
        """更新单个设备行"""
        try:
            # 找到设备对应的行
            for row in range(self.device_overview_table.rowCount()):
                item = self.device_overview_table.item(row, 0)
                if item and item.text() == device_id:
                    # 判断在线状态
                    is_online = self.is_device_online(device_info)
                    # 更新该行数据
                    self.populate_table_row(row, device_id, device_info, is_online)
                    break
        except Exception as e:
            self.logger.error(f"更新设备行失败: {e}")
