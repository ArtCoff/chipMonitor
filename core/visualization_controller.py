import logging
import time
from typing import Dict, Any, List, Optional
from collections import deque, defaultdict
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer

from .data_bus import data_bus, DataChannel, DataMessage


class VisualizationController(QObject):
    """可视化控制器 - 数据聚合和分发"""

    # 对外信号
    device_data_updated = Signal(str, object)  # (device_id, device_data)
    device_list_updated = Signal(list)  # active_devices
    statistics_updated = Signal(str, dict)  # (device_id, stats)
    connection_status_changed = Signal(bool, str)  # (connected, message)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("VisualizationController")

        # 🔥 数据存储 - 按设备ID组织
        self.device_data = defaultdict(
            lambda: {
                # 时间序列数据（环形缓冲区）
                "temperature": deque(maxlen=300),
                "pressure": deque(maxlen=300),
                "rf_power": deque(maxlen=300),
                "endpoint": deque(maxlen=300),
                "humidity": deque(maxlen=300),
                "vibration": deque(maxlen=300),
                "focus_error": deque(maxlen=300),
                "timestamps": deque(maxlen=300),
                # 设备元信息
                "device_id": "",
                "device_type": "UNKNOWN",
                "vendor": "UNKNOWN",
                "topic": "",
                "last_update": None,
                "connection_status": "offline",
                # 工艺信息
                "recipe": "",
                "step": "",
                "lot_id": "",
                "wafer_id": "",
                # 统计信息
                "total_records": 0,
                "avg_temperature": 0.0,
                "avg_pressure": 0.0,
                "max_power": 0.0,
                "data_integrity": 100.0,
                "update_freq": 0.0,
            }
        )

        # 活跃设备列表
        self.active_devices = set()

        # 当前选中设备
        self.current_device = None

        # 连接状态
        self.connected = False

        # 设置DataBus订阅
        self.setup_databus_subscriptions()

        # 定时器 - 定期发送更新信号
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.emit_periodic_updates)
        self.update_timer.start(1000)  # 1秒更新一次

        # 清理定时器 - 移除离线设备
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.cleanup_offline_devices)
        self.cleanup_timer.start(30000)  # 30秒清理一次

        self.logger.info("可视化控制器初始化完成")

    def setup_databus_subscriptions(self):
        """设置DataBus订阅"""
        try:
            # 订阅遥测数据
            data_bus.subscribe(DataChannel.TELEMETRY_DATA, self.on_telemetry_data)

            # 订阅设备事件
            data_bus.subscribe(DataChannel.DEVICE_EVENTS, self.on_device_events)

            # 订阅错误信息
            data_bus.subscribe(DataChannel.ERRORS, self.on_errors)

            self.logger.info("DataBus订阅设置完成")

        except Exception as e:
            self.logger.error(f"DataBus订阅设置失败: {e}")

    def on_telemetry_data(self, message: DataMessage):
        """处理遥测数据"""
        try:
            device_id = message.device_id
            if not device_id:
                return

            data = message.data

            # 🔥 更新设备数据
            device_storage = self.device_data[device_id]

            # 更新基本信息
            device_storage["device_id"] = device_id
            device_storage["device_type"] = data.get("device_type", "UNKNOWN")
            device_storage["vendor"] = data.get("vendor", "UNKNOWN")
            device_storage["topic"] = data.get("topic", "")
            device_storage["last_update"] = time.time()
            device_storage["connection_status"] = "online"

            # 🔥 处理数据 - 统一处理批次和单条
            batch_size = data.get("batch_size", 1)

            if data.get("is_batch", False) and batch_size > 1:
                # 批次数据处理
                full_batch = data.get("full_batch", [])
                if full_batch:
                    self._process_batch_data(device_storage, full_batch, data)
            else:
                # 单条数据处理
                self._process_single_record(device_storage, data)

            # 更新活跃设备列表
            if device_id not in self.active_devices:
                self.active_devices.add(device_id)
                self.device_list_updated.emit(list(self.active_devices))

            # 发送设备数据更新信号
            self.device_data_updated.emit(device_id, device_storage)

            self.logger.debug(f"处理遥测数据: {device_id} | 批次大小: {batch_size}")

        except Exception as e:
            self.logger.error(f"处理遥测数据失败: {e}")

    def _process_batch_data(
        self, device_storage: dict, batch_data: List[dict], metadata: dict
    ):
        """处理批次数据"""
        try:
            # 批量添加数据点
            for record in batch_data:
                self._add_data_point(device_storage, record)

            # 更新工艺信息（使用最后一条记录）
            if batch_data:
                last_record = batch_data[-1]
                self._update_process_info(device_storage, last_record)

            # 更新统计信息
            device_storage["total_records"] += len(batch_data)

            self.logger.debug(f"批次数据处理完成: {len(batch_data)}条记录")

        except Exception as e:
            self.logger.error(f"批次数据处理失败: {e}")

    def _process_single_record(self, device_storage: dict, data: dict):
        """处理单条记录"""
        try:
            # 添加数据点
            self._add_data_point(device_storage, data)

            # 更新工艺信息
            self._update_process_info(device_storage, data)

            # 更新统计信息
            device_storage["total_records"] += 1

        except Exception as e:
            self.logger.error(f"单条记录处理失败: {e}")

    def _add_data_point(self, device_storage: dict, record: dict):
        """添加单个数据点"""
        try:
            current_time = time.time()

            # 时间戳处理
            device_timestamp = record.get("device_timestamp_sec")
            if device_timestamp:
                timestamp = float(device_timestamp)
            else:
                timestamp = current_time

            device_storage["timestamps"].append(timestamp)

            # 🔥 传感器数据映射
            sensor_mappings = {
                "temperature": ["temperature", "temp", "Temperature"],
                "pressure": ["pressure", "Pressure"],
                "rf_power": ["rf_power", "power", "RF_Power"],
                "endpoint": ["endpoint", "Endpoint"],
                "humidity": ["humidity", "Humidity"],
                "vibration": ["vibration", "Vibration"],
                "focus_error": ["focus_error", "Focus_Error"],
            }

            for storage_key, possible_keys in sensor_mappings.items():
                value = None
                for key in possible_keys:
                    if key in record:
                        value = float(record[key])
                        break

                # 如果没找到值，使用默认值或上一个值
                if value is None:
                    if device_storage[storage_key]:
                        value = device_storage[storage_key][-1]  # 使用上一个值
                    else:
                        value = 0.0  # 默认值

                device_storage[storage_key].append(value)

        except Exception as e:
            self.logger.error(f"添加数据点失败: {e}")

    def _update_process_info(self, device_storage: dict, record: dict):
        """更新工艺信息"""
        try:
            # 工艺参数映射
            process_mappings = {
                "recipe": ["recipe", "Recipe"],
                "step": ["step", "Step"],
                "lot_id": ["lot_id", "LotID", "Lot_ID"],
                "wafer_id": ["wafer_id", "WaferID", "Wafer_ID"],
            }

            for storage_key, possible_keys in process_mappings.items():
                for key in possible_keys:
                    if key in record:
                        device_storage[storage_key] = str(record[key])
                        break

        except Exception as e:
            self.logger.error(f"更新工艺信息失败: {e}")

    def on_device_events(self, message: DataMessage):
        """处理设备事件"""
        try:
            event_data = message.data
            event_type = event_data.get("event_type", event_data.get("message_type"))
            device_id = message.device_id

            if event_type == "device_discovered":
                if device_id and device_id not in self.active_devices:
                    self.active_devices.add(device_id)
                    self.device_list_updated.emit(list(self.active_devices))

            elif event_type == "gateway_message":
                # 网关消息不算作数据设备
                pass

        except Exception as e:
            self.logger.error(f"处理设备事件失败: {e}")

    def on_errors(self, message: DataMessage):
        """处理错误信息"""
        try:
            device_id = message.device_id
            if device_id and device_id in self.device_data:
                # 标记设备有错误，但不移除
                self.device_data[device_id]["connection_status"] = "error"

        except Exception as e:
            self.logger.error(f"处理错误信息失败: {e}")

    def emit_periodic_updates(self):
        """定期发送更新信号"""
        try:
            # 更新统计信息
            for device_id in list(self.active_devices):
                if device_id in self.device_data:
                    stats = self._calculate_statistics(device_id)
                    self.statistics_updated.emit(device_id, stats)

            # 检查连接状态
            current_connected = len(self.active_devices) > 0
            if current_connected != self.connected:
                self.connected = current_connected
                status_msg = (
                    f"活跃设备: {len(self.active_devices)}"
                    if current_connected
                    else "无活跃设备"
                )
                self.connection_status_changed.emit(current_connected, status_msg)

        except Exception as e:
            self.logger.error(f"定期更新失败: {e}")

    def _calculate_statistics(self, device_id: str) -> dict:
        """计算设备统计信息"""
        try:
            device_storage = self.device_data[device_id]

            stats = {
                "total_records": device_storage["total_records"],
                "data_integrity": 100.0,  # 简化计算
                "update_freq": 0.0,
            }

            # 计算平均值
            if device_storage["temperature"]:
                stats["avg_temperature"] = sum(device_storage["temperature"]) / len(
                    device_storage["temperature"]
                )
            else:
                stats["avg_temperature"] = 0.0

            if device_storage["pressure"]:
                stats["avg_pressure"] = sum(device_storage["pressure"]) / len(
                    device_storage["pressure"]
                )
            else:
                stats["avg_pressure"] = 0.0

            if device_storage["rf_power"]:
                stats["max_power"] = max(device_storage["rf_power"])
            else:
                stats["max_power"] = 0.0

            # 计算更新频率
            if len(device_storage["timestamps"]) >= 2:
                time_span = (
                    device_storage["timestamps"][-1] - device_storage["timestamps"][0]
                )
                if time_span > 0:
                    stats["update_freq"] = len(device_storage["timestamps"]) / time_span

            return stats

        except Exception as e:
            self.logger.error(f"统计计算失败: {e}")
            return {}

    def cleanup_offline_devices(self):
        """清理离线设备"""
        try:
            current_time = time.time()
            offline_threshold = 60  # 60秒无数据认为离线

            offline_devices = []
            for device_id in list(self.active_devices):
                device_storage = self.device_data[device_id]
                last_update = device_storage.get("last_update")

                if last_update and (current_time - last_update) > offline_threshold:
                    offline_devices.append(device_id)
                    device_storage["connection_status"] = "offline"

            # 移除离线设备
            for device_id in offline_devices:
                self.active_devices.discard(device_id)

            if offline_devices:
                self.logger.info(f"清理离线设备: {offline_devices}")
                self.device_list_updated.emit(list(self.active_devices))

        except Exception as e:
            self.logger.error(f"清理离线设备失败: {e}")

    # === 对外接口方法 ===

    def get_device_data(self, device_id: str) -> Optional[dict]:
        """获取设备数据"""
        if device_id in self.device_data:
            return self.device_data[device_id]
        return None

    def get_active_devices(self) -> List[str]:
        """获取活跃设备列表"""
        return sorted(list(self.active_devices))

    def set_current_device(self, device_id: str):
        """设置当前设备"""
        if device_id in self.active_devices:
            self.current_device = device_id
            self.logger.info(f"设置当前设备: {device_id}")

    def get_device_statistics(self, device_id: str) -> Optional[dict]:
        """获取设备统计信息"""
        if device_id in self.device_data:
            return self._calculate_statistics(device_id)
        return None

    def stop(self):
        """停止控制器"""
        try:
            self.update_timer.stop()
            self.cleanup_timer.stop()
            self.logger.info("可视化控制器已停止")
        except Exception as e:
            self.logger.error(f"停止控制器失败: {e}")
