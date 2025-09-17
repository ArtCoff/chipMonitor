import sys
import asyncio
import msgpack
import paho.mqtt.client as mqtt
from datetime import datetime
from collections import defaultdict, deque
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QGridLayout,
    QProgressBar,
    QTabWidget,
    QSplitter,
)
from PySide6.QtCore import QTimer, QThread, Signal, QObject, Qt
from PySide6.QtGui import QFont, QColor


class MQTTWorker(QObject):
    """MQTT工作线程"""

    data_received = Signal(str, dict, int)  # 主题, 解析数据, 批次大小
    connection_status = Signal(bool, str)  # 连接状态, 消息
    statistics_updated = Signal(dict)  # 统计信息
    gateway_status = Signal(str, str)  # 网关ID, 状态

    def __init__(self):
        super().__init__()
        self.client = mqtt.Client(client_id="pyside6_viewer")
        self.connected = False
        self.message_count = 0
        self.start_time = datetime.now()

        # 设备统计
        self.device_stats = defaultdict(
            lambda: {
                "message_count": 0,
                "record_count": 0,
                "batch_count": 0,
                "data_size": 0,
                "last_seen": None,
                "device_type": "",
                "avg_batch_size": 0.0,
            }
        )

        # 网关状态
        self.gateway_info = {}

    def setup_mqtt(self):
        """设置MQTT客户端"""

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self.connected = True
                self.connection_status.emit(True, "已连接到MQTT代理")

                # 订阅工厂遥测数据
                client.subscribe("factory/telemetry/+/+", 0)

                # 订阅网关状态信息
                client.subscribe("gateway/+/status", 0)
                client.subscribe("gateway/+/info", 0)

                print("📡 已订阅以下主题:")
                print("   - factory/telemetry/+/+")
                print("   - gateway/+/status")
                print("   - gateway/+/info")
            else:
                self.connected = False
                self.connection_status.emit(False, f"连接失败: {rc}")

        def on_disconnect(client, userdata, rc):
            self.connected = False
            self.connection_status.emit(False, "已断开连接")

        def on_message(client, userdata, msg):
            self.process_message(msg.topic, msg.payload)

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message

    def process_message(self, topic, payload):
        """处理接收到的MQTT消息"""
        try:
            self.message_count += 1

            # 处理网关状态消息
            if topic.startswith("gateway/"):
                self._process_gateway_message(topic, payload)
                return

            # 处理设备遥测数据
            if topic.startswith("factory/telemetry/"):
                self._process_telemetry_message(topic, payload)

            # 定期更新统计
            if self.message_count % 10 == 0:
                self._emit_statistics()

        except Exception as e:
            print(f"处理消息失败: {e}")

    def _process_gateway_message(self, topic, payload):
        """处理网关状态消息"""
        try:
            parts = topic.split("/")
            if len(parts) >= 3:
                gateway_id = parts[1]
                message_type = parts[2]

                if message_type == "status":
                    status = payload.decode("utf-8") if payload else "unknown"
                    self.gateway_status.emit(gateway_id, status)

                elif message_type == "info":
                    try:
                        info = msgpack.unpackb(payload, raw=False)
                        self.gateway_info[gateway_id] = info
                    except:
                        pass

        except Exception as e:
            print(f"处理网关消息失败: {e}")

    def _process_telemetry_message(self, topic, payload):
        """处理遥测数据消息"""
        try:
            # 解析主题: factory/telemetry/DEVICE_TYPE/EQUIPMENT_ID
            parts = topic.split("/")
            if len(parts) >= 4:
                device_type = parts[2]
                equipment_id = parts[3]
                device_key = f"{device_type}/{equipment_id}"

                # 解析MessagePack数据
                batch_data = msgpack.unpackb(payload, raw=False)

                if isinstance(batch_data, list) and batch_data:
                    batch_size = len(batch_data)

                    # 更新设备统计
                    stats = self.device_stats[device_key]
                    stats["message_count"] += 1
                    stats["record_count"] += batch_size
                    stats["batch_count"] += 1
                    stats["data_size"] += len(payload)
                    stats["last_seen"] = datetime.now()
                    stats["device_type"] = device_type
                    stats["avg_batch_size"] = (
                        stats["record_count"] / stats["batch_count"]
                    )

                    # 准备显示数据 - 使用第一条记录作为样本
                    display_data = {
                        "type": "telemetry_batch",
                        "device_type": device_type,
                        "equipment_id": equipment_id,
                        "batch_size": batch_size,
                        "sample_record": batch_data[0],
                        "full_batch": batch_data,  # 用于详细分析
                        "data_size": len(payload),
                    }

                    # 发送数据更新信号
                    self.data_received.emit(topic, display_data, batch_size)

        except Exception as e:
            print(f"处理遥测消息失败: {e}")

    def _emit_statistics(self):
        """发送统计信息"""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        # 计算聚合统计
        total_records = sum(
            stats["record_count"] for stats in self.device_stats.values()
        )
        total_data_size = sum(
            stats["data_size"] for stats in self.device_stats.values()
        )
        total_batches = sum(
            stats["batch_count"] for stats in self.device_stats.values()
        )

        stats = {
            "total_messages": self.message_count,
            "total_devices": len(self.device_stats),
            "total_records": total_records,
            "total_batches": total_batches,
            "total_data_size": total_data_size,
            "message_rate": self.message_count / elapsed if elapsed > 0 else 0,
            "record_rate": total_records / elapsed if elapsed > 0 else 0,
            "avg_batch_size": total_records / total_batches if total_batches > 0 else 0,
            "device_stats": dict(self.device_stats),
            "gateway_info": dict(self.gateway_info),
            "elapsed_time": elapsed,
        }
        self.statistics_updated.emit(stats)

    def connect_to_broker(self, host="localhost", port=1883):
        """连接到MQTT代理"""
        try:
            self.client.connect(host, port, 60)
            self.client.loop_start()
        except Exception as e:
            self.connection_status.emit(False, f"连接异常: {e}")

    def disconnect_from_broker(self):
        """断开MQTT连接"""
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()


class MqttDebuggerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("半导体设备数据监控器 - 优化版")
        self.setGeometry(100, 100, 1400, 900)

        # 数据存储
        self.current_data = {}
        self.device_list = set()
        self.gateway_status = {}
        self.message_history = deque(maxlen=500)  # 保留最近500条消息

        # 设置UI
        self.setup_ui()

        # 设置MQTT工作线程
        self.setup_mqtt_worker()

        # 启动定时器更新UI
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)  # 每秒更新一次

    def setup_ui(self):
        """设置用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 网关状态区域
        self.setup_gateway_area(main_layout)

        # 统计信息区域
        self.setup_statistics_area(main_layout)

        # 标签页区域
        tab_widget = QTabWidget()

        # 设备监控标签页
        device_tab = self.create_device_tab()
        tab_widget.addTab(device_tab, "设备监控")

        # 实时数据标签页
        realtime_tab = self.create_realtime_tab()
        tab_widget.addTab(realtime_tab, "实时数据")

        # 批次分析标签页
        batch_tab = self.create_batch_analysis_tab()
        tab_widget.addTab(batch_tab, "批次分析")

        main_layout.addWidget(tab_widget)

    def setup_gateway_area(self, parent_layout):
        """设置网关状态区域"""
        gateway_group = QGroupBox("网关状态")
        gateway_layout = QHBoxLayout(gateway_group)

        # 连接控制
        self.connect_btn = QPushButton("连接MQTT")
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.connection_status_label = QLabel("未连接")
        self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")

        # 网关信息
        self.gateway_status_label = QLabel("网关: 未知")

        gateway_layout.addWidget(self.connect_btn)
        gateway_layout.addWidget(QLabel("连接状态:"))
        gateway_layout.addWidget(self.connection_status_label)
        gateway_layout.addWidget(QLabel("|"))
        gateway_layout.addWidget(self.gateway_status_label)
        gateway_layout.addStretch()

        parent_layout.addWidget(gateway_group)

    def setup_statistics_area(self, parent_layout):
        """设置统计信息区域"""
        stats_group = QGroupBox("系统统计")
        stats_layout = QGridLayout(stats_group)

        # 统计标签
        self.total_messages_label = QLabel("0")
        self.total_devices_label = QLabel("0")
        self.total_records_label = QLabel("0")
        self.message_rate_label = QLabel("0.0 msg/s")
        self.record_rate_label = QLabel("0.0 rec/s")
        self.avg_batch_size_label = QLabel("0.0")
        self.data_volume_label = QLabel("0 B")
        self.uptime_label = QLabel("00:00:00")

        # 布局统计信息
        stats_layout.addWidget(QLabel("MQTT消息:"), 0, 0)
        stats_layout.addWidget(self.total_messages_label, 0, 1)
        stats_layout.addWidget(QLabel("数据记录:"), 0, 2)
        stats_layout.addWidget(self.total_records_label, 0, 3)
        stats_layout.addWidget(QLabel("设备数:"), 0, 4)
        stats_layout.addWidget(self.total_devices_label, 0, 5)

        stats_layout.addWidget(QLabel("消息速率:"), 1, 0)
        stats_layout.addWidget(self.message_rate_label, 1, 1)
        stats_layout.addWidget(QLabel("记录速率:"), 1, 2)
        stats_layout.addWidget(self.record_rate_label, 1, 3)
        stats_layout.addWidget(QLabel("平均批次:"), 1, 4)
        stats_layout.addWidget(self.avg_batch_size_label, 1, 5)

        parent_layout.addWidget(stats_group)

    def create_device_tab(self):
        """创建设备监控标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 设备表格
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(9)
        self.device_table.setHorizontalHeaderLabels(
            [
                "设备ID",
                "设备类型",
                "MQTT消息",
                "数据记录",
                "批次数",
                "平均批次",
                "数据量",
                "最后更新",
                "状态",
            ]
        )
        self.device_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.device_table)
        return widget

    def create_realtime_tab(self):
        """创建实时数据标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 当前数据显示
        self.current_data_table = QTableWidget()
        self.current_data_table.setColumnCount(2)
        self.current_data_table.setHorizontalHeaderLabels(["参数", "值"])
        self.current_data_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(QLabel("当前数据参数:"))
        layout.addWidget(self.current_data_table)

        # JSON格式显示
        self.json_display = QTextEdit()
        self.json_display.setFont(QFont("Consolas", 9))
        self.json_display.setMaximumHeight(200)

        layout.addWidget(QLabel("JSON格式:"))
        layout.addWidget(self.json_display)

        return widget

    def create_batch_analysis_tab(self):
        """创建批次分析标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 批次信息
        self.batch_info_table = QTableWidget()
        self.batch_info_table.setColumnCount(4)
        self.batch_info_table.setHorizontalHeaderLabels(
            ["设备ID", "批次大小", "数据大小", "接收时间"]
        )
        self.batch_info_table.setMaximumHeight(200)

        layout.addWidget(QLabel("最近批次信息:"))
        layout.addWidget(self.batch_info_table)

        # 批次数据详情
        self.batch_detail_text = QTextEdit()
        self.batch_detail_text.setFont(QFont("Consolas", 8))

        layout.addWidget(QLabel("批次数据详情:"))
        layout.addWidget(self.batch_detail_text)

        return widget

    def setup_mqtt_worker(self):
        """设置MQTT工作线程"""
        self.mqtt_thread = QThread()
        self.mqtt_worker = MQTTWorker()
        self.mqtt_worker.moveToThread(self.mqtt_thread)

        # 连接信号
        self.mqtt_worker.data_received.connect(self.on_data_received)
        self.mqtt_worker.connection_status.connect(self.on_connection_status)
        self.mqtt_worker.statistics_updated.connect(self.on_statistics_updated)
        self.mqtt_worker.gateway_status.connect(self.on_gateway_status)

        # 设置MQTT
        self.mqtt_worker.setup_mqtt()

        # 启动线程
        self.mqtt_thread.start()

    def toggle_connection(self):
        """切换MQTT连接状态"""
        if not self.mqtt_worker.connected:
            self.mqtt_worker.connect_to_broker()
            self.connect_btn.setText("断开连接")
        else:
            self.mqtt_worker.disconnect_from_broker()
            self.connect_btn.setText("连接MQTT")

    def on_connection_status(self, connected, message):
        """处理连接状态变化"""
        if connected:
            self.connection_status_label.setText("已连接")
            self.connection_status_label.setStyleSheet(
                "color: green; font-weight: bold;"
            )
            self.connect_btn.setText("断开连接")
        else:
            self.connection_status_label.setText("未连接")
            self.connection_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.connect_btn.setText("连接MQTT")

    def on_gateway_status(self, gateway_id, status):
        """处理网关状态变化"""
        self.gateway_status[gateway_id] = status

        # 更新网关状态显示
        if status == "online":
            self.gateway_status_label.setText(f"网关: {gateway_id} (在线)")
            self.gateway_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.gateway_status_label.setText(f"网关: {gateway_id} (离线)")
            self.gateway_status_label.setStyleSheet("color: red; font-weight: bold;")

    def on_data_received(self, topic, data, batch_size):
        """处理接收到的数据"""
        timestamp = datetime.now()

        # 解析主题获取设备信息
        parts = topic.split("/")
        if len(parts) >= 4:
            device_type = parts[2]
            equipment_id = parts[3]
            device_key = f"{device_type}/{equipment_id}"

            # 存储最新数据
            self.current_data[device_key] = {
                "topic": topic,
                "device_type": device_type,
                "equipment_id": equipment_id,
                "data": data,
                "timestamp": timestamp,
                "batch_size": batch_size,
            }

            self.device_list.add(device_key)

            # 添加到消息历史
            self.message_history.append(
                {
                    "timestamp": timestamp,
                    "topic": topic,
                    "device_key": device_key,
                    "batch_size": batch_size,
                    "data_size": data.get("data_size", 0),
                }
            )

            # 更新实时数据显示（显示最新收到的数据）
            if data.get("type") == "telemetry_batch":
                self.update_realtime_data(data["sample_record"])
                self.update_batch_analysis(equipment_id, data)

    def on_statistics_updated(self, stats):
        """更新统计信息"""
        self.total_messages_label.setText(str(stats["total_messages"]))
        self.total_devices_label.setText(str(stats["total_devices"]))
        self.total_records_label.setText(str(stats["total_records"]))
        self.message_rate_label.setText(f"{stats['message_rate']:.1f} msg/s")
        self.record_rate_label.setText(f"{stats['record_rate']:.1f} rec/s")
        self.avg_batch_size_label.setText(f"{stats['avg_batch_size']:.1f}")

        # 格式化数据量
        data_size = stats["total_data_size"]
        self.data_volume_label.setText(self.format_bytes(data_size))

        # 更新运行时间
        elapsed = stats["elapsed_time"]
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def update_realtime_data(self, record):
        """更新实时数据显示"""
        try:
            # 更新参数表格
            params = {
                "设备ID": record.get("eq", ""),
                "传感器通道": record.get("ch", ""),
                "工艺配方": record.get("rt", ""),
                "工艺步骤": record.get("st", ""),
                "批次号": record.get("lot", ""),
                "晶圆号": record.get("wf", ""),
                "压力 (Torr)": record.get("p", ""),
                "温度 (°C)": record.get("t", ""),
                "RF功率 (W)": record.get("rf", ""),
                "终点信号": record.get("ep", ""),
                "时间戳": record.get("ts", ""),
            }

            self.current_data_table.setRowCount(len(params))
            for i, (param, value) in enumerate(params.items()):
                self.current_data_table.setItem(i, 0, QTableWidgetItem(param))
                self.current_data_table.setItem(i, 1, QTableWidgetItem(str(value)))

            # 显示JSON数据
            import json

            formatted_data = json.dumps(record, indent=2, ensure_ascii=False)
            self.json_display.setPlainText(formatted_data)

        except Exception as e:
            print(f"更新实时数据失败: {e}")

    def update_batch_analysis(self, equipment_id, data):
        """更新批次分析"""
        try:
            # 更新批次信息表格
            current_time = datetime.now().strftime("%H:%M:%S")
            batch_size = data["batch_size"]
            data_size = self.format_bytes(data["data_size"])

            # 在表格顶部插入新行
            self.batch_info_table.insertRow(0)
            self.batch_info_table.setItem(0, 0, QTableWidgetItem(equipment_id))
            self.batch_info_table.setItem(0, 1, QTableWidgetItem(str(batch_size)))
            self.batch_info_table.setItem(0, 2, QTableWidgetItem(data_size))
            self.batch_info_table.setItem(0, 3, QTableWidgetItem(current_time))

            # 限制表格行数
            while self.batch_info_table.rowCount() > 20:
                self.batch_info_table.removeRow(self.batch_info_table.rowCount() - 1)

            # 显示批次详情（前5条记录）
            if "full_batch" in data and data["full_batch"]:
                import json

                sample_batch = data["full_batch"][:5]  # 只显示前5条
                batch_detail = {
                    "equipment_id": equipment_id,
                    "batch_size": batch_size,
                    "sample_records": sample_batch,
                    "note": f"显示前5条记录，实际批次包含{batch_size}条记录",
                }
                formatted_detail = json.dumps(
                    batch_detail, indent=2, ensure_ascii=False
                )
                self.batch_detail_text.setPlainText(formatted_detail)

        except Exception as e:
            print(f"更新批次分析失败: {e}")

    def update_ui(self):
        """定时更新UI"""
        # 更新设备表格
        self.update_device_table()

    def update_device_table(self):
        """更新设备表格"""
        if hasattr(self.mqtt_worker, "device_stats"):
            devices = self.mqtt_worker.device_stats
            self.device_table.setRowCount(len(devices))

            for i, (device_key, stats) in enumerate(sorted(devices.items())):
                device_parts = device_key.split("/")
                device_type = device_parts[0] if len(device_parts) > 0 else ""
                equipment_id = device_parts[1] if len(device_parts) > 1 else device_key

                self.device_table.setItem(i, 0, QTableWidgetItem(equipment_id))
                self.device_table.setItem(i, 1, QTableWidgetItem(device_type))
                self.device_table.setItem(
                    i, 2, QTableWidgetItem(str(stats["message_count"]))
                )
                self.device_table.setItem(
                    i, 3, QTableWidgetItem(str(stats["record_count"]))
                )
                self.device_table.setItem(
                    i, 4, QTableWidgetItem(str(stats["batch_count"]))
                )
                self.device_table.setItem(
                    i, 5, QTableWidgetItem(f"{stats['avg_batch_size']:.1f}")
                )
                self.device_table.setItem(
                    i, 6, QTableWidgetItem(self.format_bytes(stats["data_size"]))
                )

                if stats["last_seen"]:
                    self.device_table.setItem(
                        i, 7, QTableWidgetItem(stats["last_seen"].strftime("%H:%M:%S"))
                    )
                else:
                    self.device_table.setItem(i, 7, QTableWidgetItem("--"))

                self.device_table.setItem(i, 8, QTableWidgetItem("在线"))

    def format_bytes(self, bytes_count):
        """格式化字节数"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} TB"

    def closeEvent(self, event):
        """应用关闭时清理资源"""
        self.mqtt_worker.disconnect_from_broker()
        self.mqtt_thread.quit()
        self.mqtt_thread.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)

    window = MqttDebuggerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
