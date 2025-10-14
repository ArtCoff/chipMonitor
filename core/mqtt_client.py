import paho.mqtt.client as mqtt
import json
import time
import logging
import msgpack
from typing import Dict, List, Optional, Callable, Set, Any
from PySide6.QtCore import QObject, Signal, QTimer, Qt, Slot
from .thread_pool import get_thread_pool, TaskType, TaskPriority
from .data_bus import get_data_bus, DataChannel, DataMessage


class MessageParser:
    """统一的消息解析器"""

    @staticmethod
    def parse_topic(topic: str) -> tuple[str, str]:
        """解析主题，返回 (clean_topic, format_type)"""
        if topic.endswith("/msgpack"):
            return topic[:-8], "msgpack"
        elif topic.endswith("/json"):
            return topic[:-5], "json"
        else:
            return topic, "auto"

    @staticmethod
    def parse_payload(payload: bytes, format_hint: str = "auto") -> tuple[Any, str]:
        """解析载荷，返回 (data, actual_format)"""
        if format_hint == "msgpack":
            try:
                data = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                return data, "msgpack"
            except Exception as e:
                raise ValueError(f"MessagePack解析失败: {e}")

        elif format_hint == "json":
            try:
                data = json.loads(payload.decode("utf-8"))
                return data, "json"
            except Exception as e:
                raise ValueError(f"JSON解析失败: {e}")

        else:  # auto detect
            # 先尝试 MessagePack
            try:
                data = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                return data, "msgpack"
            except Exception:
                pass

            # 再尝试 JSON
            try:
                data = json.loads(payload.decode("utf-8"))
                return data, "json"
            except Exception:
                pass

            # 尝试纯文本
            try:
                text = payload.decode("utf-8")
                return {"text": text}, "text"
            except Exception:
                pass

            raise ValueError("无法识别数据格式")


class TopicRouter:
    """主题路由器"""

    @staticmethod
    def parse_device_topic(topic: str) -> Optional[dict]:
        """解析设备主题: factory/telemetry/{device_type}/{device_id}"""
        parts = topic.split("/")
        if len(parts) >= 4 and parts[0] == "factory" and parts[1] == "telemetry":
            device_type = parts[2]
            device_id = parts[3]

            # 解析设备ID获取厂商
            id_parts = device_id.split("_")
            vendor = id_parts[0] if len(id_parts) > 0 else "UNKNOWN"
            # self.logger.debug(
            #     f"解析设备主题: {topic} -> {device_type}, {device_id}, {vendor}"
            # )
            return {
                "device_id": device_id,
                "device_type": device_type,
                "vendor": vendor,
                "topic_type": "telemetry",
            }

        return None

    @staticmethod
    def parse_gateway_topic(topic: str) -> Optional[dict]:
        """解析网关主题: gateway/{gateway_id}/{function}"""
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "gateway":
            return {
                "device_id": parts[1],
                "device_type": "GATEWAY",
                "vendor": "SYSTEM",
                "function": parts[2],
                "topic_type": "gateway",
            }
        return None

    @staticmethod
    def classify_topic(topic: str) -> str:
        """分类主题类型"""
        clean_topic, _ = MessageParser.parse_topic(topic)

        if TopicRouter.parse_device_topic(clean_topic):
            return "device_telemetry"
        elif TopicRouter.parse_gateway_topic(clean_topic):
            return "gateway"
        else:
            return "system"


class MqttManager(QObject):
    # 定义信号
    connection_changed = Signal(bool, str)  # 连接状态变化：(是否连接, 消息)
    statistics_updated = Signal(dict)  # 统计信息更新
    topic_subscribed = Signal(str, bool)  # 主题订阅结果：(主题, 是否成功)
    connection_status = Signal(str)  # 连接状态文本
    message_received = Signal(str, bytes, int)  # (主题, 载荷, QoS)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__()
        self.logger = logging.getLogger("MqttManager")

        self.thread_pool = get_thread_pool()
        self.data_bus = get_data_bus()
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.connection_config = {
            "host": "localhost",
            "port": 1883,
            "keepalive": 60,
            "username": "",
            "password": "",
        }

        # 订阅管理
        self.subscriptions: Dict[str, int] = {}  # topic: qos
        # 设备管理
        self.known_devices: Set[str] = set()
        # 重连机制
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self._attempt_reconnect)
        self.reconnect_interval = 5000  # 5秒
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10

        # 消息统计
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "connection_drops": 0,
            "last_message_time": None,
            "bytes_received": 0,
            "connection_time": None,
        }

        # 统计定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._emit_statistics)
        self.stats_timer.start(2000)  # 每2秒发送统计信息

        self.thread_pool.task_completed.connect(
            self._on_device_data_processed, Qt.QueuedConnection
        )
        self.thread_pool.task_failed.connect(
            self._on_device_data_processing_failed, Qt.QueuedConnection
        )
        self.logger.info("MQTT管理器已初始化")

    def connect(
        self,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
    ) -> bool:
        """连接到MQTT代理"""
        try:
            # 更新连接配置
            if host is not None:
                self.connection_config["host"] = host
            if port is not None:
                self.connection_config["port"] = port
            if username is not None:
                self.connection_config["username"] = username
            if password is not None:
                self.connection_config["password"] = password

            # 断开现有连接
            if self.client:
                self.disconnect()

            # 创建新客户端
            client_id = f"chipmonitor_{int(time.time())}"
            self.client = mqtt.Client(client_id=client_id)

            # 设置认证
            username = self.connection_config["username"]
            password = self.connection_config["password"]
            if username and password:
                self.client.username_pw_set(username, password)

            # 设置回调
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.on_publish = self._on_publish
            self.client.on_subscribe = self._on_subscribe
            self.connection_status.emit("正在连接...")

            self.client.connect_async(
                self.connection_config["host"],
                self.connection_config["port"],
                self.connection_config["keepalive"],
            )
            self.client.loop_start()

            return True

        except Exception as e:
            error_msg = f"MQTT连接初始化失败: {e}"
            self.logger.error(error_msg)
            self.connection_changed.emit(False, error_msg)
            self.connection_status.emit(f"连接失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        try:
            if self.client and self.connected:
                self.connection_status.emit("正在断开连接...")
                self.client.loop_stop()
                self.client.disconnect()
                self.reconnect_timer.stop()
                self.logger.info("MQTT连接已断开")
        except Exception as e:
            self.logger.error(f"断开连接失败: {e}")

    def subscribe_topic(self, topic: str, qos: int = 0) -> bool:
        """订阅主题"""
        try:
            if self.client and self.connected:
                result, _ = self.client.subscribe(topic, qos)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    self.subscriptions[topic] = qos
                    self.logger.info(f"订阅主题: {topic} (QoS: {qos})")
                    return True
                else:
                    self.logger.error(f"订阅主题失败: {topic}, 错误码: {result}")
                    self.topic_subscribed.emit(topic, False)
                    return False
            else:
                # 保存订阅，连接后自动订阅
                self.subscriptions[topic] = qos
                self.logger.info(f"保存订阅主题: {topic} (连接后将自动订阅)")
                return True
        except Exception as e:
            self.logger.error(f"订阅主题失败: {e}")
            self.topic_subscribed.emit(topic, False)
            return False

    def unsubscribe_topic(self, topic: str) -> bool:
        """取消订阅主题"""
        try:
            if self.client and self.connected:
                result, _ = self.client.unsubscribe(topic)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    if topic in self.subscriptions:
                        del self.subscriptions[topic]
                    self.logger.info(f"取消订阅主题: {topic}")
                    return True
            return False
        except Exception as e:
            self.logger.error(f"取消订阅主题失败: {e}")
            return False

    def publish_message(self, topic: str, payload: str, qos: int = 0) -> bool:
        """发布消息"""
        if self.client and self.connected:
            try:
                result = self.client.publish(topic, payload, qos)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.stats["messages_sent"] += 1
                    return True
                else:
                    self.logger.error(f"发布消息失败: 错误码 {result.rc}")
                    return False
            except Exception as e:
                self.logger.error(f"发布消息失败: {e}")
                return False
        return False

    def _on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            self.connected = True
            self.reconnect_timer.stop()
            self.reconnect_attempts = 0
            self.stats["connection_time"] = time.time()

            success_msg = "MQTT连接成功"
            self.logger.info("MQTT连接成功")
            self.connection_changed.emit(True, success_msg)
            self.connection_status.emit("已连接")

            # 重新订阅所有主题
            for topic, qos in self.subscriptions.items():
                client.subscribe(topic, qos)
                self.logger.info(f"重新订阅主题: {topic}")

        else:
            self.connected = False
            error_msgs = {
                1: "协议版本不正确",
                2: "客户端ID无效",
                3: "服务器不可用",
                4: "用户名或密码错误",
                5: "未授权",
            }
            error_msg = error_msgs.get(rc, f"连接失败，错误代码: {rc}")
            self.logger.error(error_msg)
            self.connection_changed.emit(False, error_msg)
            self.connection_status.emit(f"连接失败: {error_msg}")

            # 启动重连
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self.reconnect_timer.start(self.reconnect_interval)

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        self.connected = False
        self.stats["connection_drops"] += 1

        if rc != 0:
            disconnect_msg = "MQTT意外断开连接"
            self.logger.warning(disconnect_msg)
            self.connection_changed.emit(False, disconnect_msg)
            self.connection_status.emit("连接断开")

            # 启动重连
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self.reconnect_timer.start(self.reconnect_interval)
        else:
            disconnect_msg = "MQTT正常断开连接"
            self.logger.info(disconnect_msg)
            self.connection_changed.emit(False, disconnect_msg)
            self.connection_status.emit("已断开")

    def _on_message(self, client, userdata, msg):
        """消息接收回调 —— 提交到线程池异步处理"""
        try:
            self.stats["messages_received"] += 1
            self.stats["last_message_time"] = time.time()
            self.stats["bytes_received"] += len(msg.payload)
            # self.logger.info(f"📥 收到MQTT消息: {topic} | {len(payload)}字节")
            topic_type = TopicRouter.classify_topic(msg.topic)
            if topic_type == "device_telemetry":
                self._handle_device_message(msg.topic, msg.payload, msg.qos)
            elif topic_type == "gateway":
                self._handle_gateway_message(msg.topic, msg.payload, msg.qos)
            else:
                self._handle_system_message(msg.topic, msg.payload, msg.qos)
        except Exception as e:
            self.logger.error(f"处理MQTT消息失败: {e}")

    def _handle_device_message(self, topic: str, payload: bytes, qos: int):
        """处理设备遥测消息"""
        task_id = f"mqtt_{self.stats['messages_received']}_{int(time.time()*1000)}"

        self.thread_pool.submit(
            TaskType.MQTT_PROCESSING,
            self._parse_device_message,
            topic,
            payload,
            qos,
            task_id=task_id,
            priority=TaskPriority.REALTIME,
            timeout=5.0,
        )

    def _parse_device_message(self, topic: str, payload: bytes, qos: int) -> dict:
        """解析设备消息"""
        parse_start_time = time.time()
        try:
            clean_topic, format_hint = MessageParser.parse_topic(topic)
            device_info = TopicRouter.parse_device_topic(clean_topic)

            if not device_info:
                self.logger.debug(f"无法从主题提取设备信息: {clean_topic}")
                return self._create_error_result(
                    topic, payload, qos, "无法提取设备信息"
                )
            data, format_type = MessageParser.parse_payload(payload, format_hint)

            result = self._build_telemetry_result(
                device_info,
                data,
                clean_topic,
                qos,
                format_type,
                len(payload),
                parse_start_time,
            )
            if "device_id" not in result or not result["device_id"]:
                self.logger.error(f"❌ CRITICAL: 结果缺少 device_id！")
            return result

        except Exception as e:
            self.logger.error(f"解析设备消息失败 {topic}: {e}")
            return self._create_error_result(topic, payload, qos, f"解析异常: {str(e)}")

    def _build_telemetry_result(
        self,
        device_info: dict,
        data: Any,
        topic: str,
        qos: int,
        data_format: str,
        data_size: int,
        parse_start: float,
    ) -> dict:
        """构建遥测数据结果"""
        if not device_info or "device_id" not in device_info:
            self.logger.error(f"❌ device_info 无效: {device_info}")
            return {
                "device_id": "UNKNOWN",
                "device_type": "ERROR",
                "vendor": "UNKNOWN",
                "topic": topic,
                "timestamp": time.time(),
                "qos": qos,
                "parse_success": False,
                "parse_error": "device_info 缺少 device_id",
                "data_size": data_size,
            }
        # 基础结果
        result = {
            "device_id": device_info["device_id"],
            "device_type": device_info["device_type"],
            "vendor": device_info["vendor"],
            "topic": topic,
            "timestamp": time.time(),
            "qos": qos,
            "parse_success": True,
            "parse_time": (time.time() - parse_start) * 1000,
            "data_format": data_format,
            "data_size": data_size,
        }

        # 验证数据格式
        if not isinstance(data, list):
            result.update(
                {
                    "parse_success": False,
                    "parse_error": f"期望数组格式，实际: {type(data).__name__}",
                }
            )
            return result

        if not data:
            result.update({"parse_success": False, "parse_error": "空数据数组"})
            return result

        # 批次信息
        batch_size = len(data)
        result["batch_size"] = batch_size

        # 处理第一条记录
        first_record = data[0]
        if isinstance(first_record, dict):
            # 字段映射
            mapped_fields = self._map_fields(first_record)
            result.update(mapped_fields)
            result["sample_record"] = mapped_fields

            # 时间跨度分析（仅多条记录）
            if batch_size > 1:
                time_info = self._analyze_batch_timespan(data)
                result.update(time_info)

        return result

    def _map_fields(self, raw_data: dict) -> dict:
        """字段映射 - 保持原有映射逻辑"""
        mapped_data = {}

        # 字段映射表
        field_map = {
            "eq": "equipment_id",
            "ch": "channel",
            "rt": "recipe",
            "st": "step",
            "lot": "lot_number",
            "wf": "wafer_id",
            "p": "pressure",
            "t": "temperature",
            "rf": "rf_power",
            "ep": "endpoint",
            "ts": "device_timestamp",
        }

        # 应用字段映射
        for old_key, new_key in field_map.items():
            if old_key in raw_data:
                mapped_data[new_key] = raw_data[old_key]

        # 处理嵌套的气体数据
        if "g" in raw_data and isinstance(raw_data["g"], dict):
            gas_data = raw_data["g"]
            for gas_name, flow_rate in gas_data.items():
                mapped_data[f"gas_{gas_name}"] = flow_rate

        # 处理时间戳转换
        if "device_timestamp" in mapped_data:
            ts = mapped_data["device_timestamp"]
            if isinstance(ts, (int, float)) and ts > 1e12:  # 微秒级
                mapped_data["device_timestamp_sec"] = ts / 1000000

        # 数值类型转换
        numeric_fields = ["pressure", "temperature", "rf_power", "endpoint", "channel"]
        for field in numeric_fields:
            if field in mapped_data:
                try:
                    mapped_data[field] = float(mapped_data[field])
                except (ValueError, TypeError):
                    pass

        return mapped_data

    def _analyze_batch_timespan(self, batch_data: list) -> dict:
        """分析批次时间跨度"""
        try:
            timestamps = []
            for record in batch_data:
                if isinstance(record, dict) and "ts" in record:
                    ts = record["ts"]
                    if isinstance(ts, (int, float)):
                        # 转换微秒时间戳
                        if ts > 1e12:
                            ts = ts / 1000000
                        timestamps.append(ts)

            if len(timestamps) > 1:
                time_span = max(timestamps) - min(timestamps)
                data_density = (
                    len(timestamps) / time_span if time_span > 0 else float("inf")
                )

                return {
                    "batch_time_span": time_span,
                    "batch_data_density": data_density,
                    "batch_start_time": min(timestamps),
                    "batch_end_time": max(timestamps),
                    "batch_has_timespan": True,
                }
            elif len(timestamps) == 1:
                return {
                    "batch_time_span": 0,
                    "batch_data_density": float("inf"),
                    "batch_start_time": timestamps[0],
                    "batch_end_time": timestamps[0],
                    "batch_has_timespan": False,
                }
        except Exception as e:
            self.logger.debug(f"时间跨度分析失败: {e}")

        return {
            "batch_time_span": None,
            "batch_data_density": None,
            "batch_has_timespan": False,
        }

    def _create_error_result(
        self, topic: str, payload: bytes, qos: int, error_msg: str
    ) -> dict:
        """创建错误结果 - 确保包含所有必要字段"""
        # 尝试从主题提取设备信息
        clean_topic, _ = MessageParser.parse_topic(topic)
        device_info = TopicRouter.parse_device_topic(clean_topic)

        # 🔥 确保始终有 device_id
        if device_info and "device_id" in device_info:
            device_id = device_info["device_id"]
            device_type = device_info.get("device_type", "UNKNOWN")
            vendor = device_info.get("vendor", "UNKNOWN")
        else:
            # 从主题中提取尽可能多的信息
            parts = clean_topic.split("/")
            if len(parts) >= 4:
                device_id = parts[3]  # factory/telemetry/type/id
                device_type = parts[2]
                vendor = device_id.split("_")[0] if "_" in device_id else "UNKNOWN"
            else:
                device_id = "ERROR_UNKNOWN"
                device_type = "ERROR"
                vendor = "UNKNOWN"

        return {
            "device_id": device_id,  # ✅ 始终存在
            "device_type": device_type,
            "vendor": vendor,
            "topic": topic,
            "timestamp": time.time(),
            "qos": qos,
            "parse_success": False,
            "parse_error": error_msg,
            "data_size": len(payload),
            "raw_payload_preview": (
                payload[:100].hex() if len(payload) > 100 else payload.hex()
            ),
        }

    def _on_publish(self, client, userdata, mid):
        """发布回调"""
        self.logger.debug(f"消息发布成功: {mid}")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """订阅回调"""
        self.logger.debug(f"订阅成功: {mid}, QoS: {granted_qos}")

    def _attempt_reconnect(self):
        """尝试重连"""
        if not self.connected and self.client:
            self.reconnect_attempts += 1
            if self.reconnect_attempts <= self.max_reconnect_attempts:
                try:
                    self.logger.info(
                        f"尝试重新连接MQTT... (第{self.reconnect_attempts}次)"
                    )
                    self.connection_status.emit(
                        f"重连中... ({self.reconnect_attempts}/{self.max_reconnect_attempts})"
                    )
                    self.client.reconnect()
                except Exception as e:
                    self.logger.debug(f"重连失败: {e}")
            else:
                self.logger.error("达到最大重连次数，停止重连")
                self.reconnect_timer.stop()
                self.connection_status.emit("重连失败")

    def _emit_statistics(self):
        """定期发送统计信息"""
        if self.connected:
            current_stats = self.get_statistics()
            self.statistics_updated.emit(current_stats)

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        current_time = time.time()
        connection_duration = 0
        if self.stats["connection_time"] and self.connected:
            connection_duration = current_time - self.stats["connection_time"]

        return {
            **self.stats,
            "connected": self.connected,
            "subscriptions_count": len(self.subscriptions),
            "subscribed_topics": list(self.subscriptions.keys()),
            "connection_duration": connection_duration,
            "reconnect_attempts": self.reconnect_attempts,
            "connection_config": {
                k: v for k, v in self.connection_config.items() if k != "password"
            },
        }

    def update_config(self, config_dict: dict):
        """更新配置"""
        try:
            old_config = self.connection_config.copy()

            # 更新连接配置
            for key in ["host", "port", "username", "password", "keepalive"]:
                if key in config_dict:
                    self.connection_config[key] = config_dict[key]

            # 检查是否需要重新连接
            need_reconnect = (
                old_config["host"] != self.connection_config["host"]
                or old_config["port"] != self.connection_config["port"]
                or old_config["username"] != self.connection_config["username"]
                or old_config["password"] != self.connection_config["password"]
            )

            if need_reconnect and self.connected:
                self.logger.info("配置已更改，将重新连接")
                self.disconnect()
                # 短暂延迟后重新连接
                QTimer.singleShot(1000, lambda: self.connect())

            return True
        except Exception as e:
            self.logger.error(f"更新MQTT配置失败: {e}")
            return False

    def _on_device_data_processed(self, task_id: str, result: Any):
        """主线程：设备数据处理完成-发布到数据总线data_bus"""
        try:
            task_type = result.get("task_type")
            if task_type != TaskType.MQTT_PROCESSING.value:
                return
            result = result.get("data")
            device_id = result.get("device_id")
            if not device_id:
                self.logger.warning(f"任务 {task_id} 缺少 device_id")
                return

            if device_id not in self.known_devices:
                self.known_devices.add(device_id)
                device_info = {
                    "device_id": device_id,
                    "device_type": result.get("device_type", "UNKNOWN"),
                    "vendor": result.get("vendor", "UNKNOWN"),
                    "event": "online",
                    "timestamp": time.time(),
                    "topic": result.get("topic", ""),
                }
                self.data_bus.publish(
                    channel=DataChannel.DEVICE_EVENTS,
                    source="mqtt_client",
                    data=device_info,
                    device_id=device_id,
                )
                self.logger.info(f"新设备上线: {device_id}")

            # 数据处理
            parse_success = result.get("parse_success", True)

            if parse_success:
                # 发布到数据总线

                success = self.data_bus.publish(
                    channel=DataChannel.TELEMETRY_DATA,
                    source="mqtt_client",
                    data=result,
                    device_id=device_id,
                )
                if not success:
                    self.logger.error(f"❌ DataBus发布失败: {device_id}")

            else:
                error_data = {
                    "device_id": device_id,
                    "error": result.get("parse_error", "未知错误"),
                    "task_id": task_id,
                }
                self.logger.error(
                    f"❌ 设备数据解析失败: {device_id} -> {result.get("parse_error", "未知错误")}"
                )
                self.data_bus.publish(
                    channel=DataChannel.ERRORS,
                    source="mqtt_client",
                    data=error_data,
                    device_id=device_id,
                )

        except Exception as e:
            self.logger.error(f"处理任务回调失败: {task_id} -> {e}")

    def _handle_gateway_message(self, topic: str, payload: bytes, qos: int):
        """简化的网关消息处理"""
        try:
            clean_topic, format_hint = MessageParser.parse_topic(topic)
            gateway_info = TopicRouter.parse_gateway_topic(clean_topic)

            if not gateway_info:
                return

            data, actual_format = MessageParser.parse_payload(payload, format_hint)

            self.data_bus.publish(
                channel=DataChannel.DEVICE_EVENTS,
                source="mqtt_client",
                data={
                    **gateway_info,
                    "data": data,
                    "format": actual_format,
                    "timestamp": time.time(),
                },
                device_id=gateway_info["device_id"],
            )
        except Exception as e:
            self.logger.error(f"❌ 处理网关消息失败: {e}")

    def _handle_system_message(self, topic: str, payload: bytes, qos: int):
        """简化的系统消息处理"""
        self.data_bus.publish(
            channel=DataChannel.DEVICE_EVENTS,
            source="mqtt_client",
            data={
                "event_type": "system_message",
                "topic": topic,
                "payload_size": len(payload),
                "timestamp": time.time(),
            },
        )

    @Slot(str, dict)
    def _on_device_data_processing_failed(self, task_id: str, error_info: dict):
        """处理MQTT任务失败"""
        try:
            if error_info.get("task_type") != TaskType.MQTT_PROCESSING.value:
                return  # 静默忽略非MQTT任务

            # 提取错误信息
            error_msg = error_info.get("error", "未知错误")
            error_detail = error_info.get("message", error_msg)

            self.logger.error(f"❌ MQTT任务失败 {task_id}: {error_detail}")

            # 发布错误事件
            self.data_bus.publish(
                channel=DataChannel.ERRORS,
                source="mqtt_client",
                data={
                    "error": error_msg,
                    "error_detail": error_detail,
                    "task_id": task_id,
                    "error_type": "mqtt_processing_failure",
                    "timestamp": time.time(),
                },
            )

        except Exception as e:
            self.logger.error(f"❌ 处理失败回调异常: {task_id} -> {e}", exc_info=True)

    def get_discovered_devices(self) -> Dict[str, dict]:
        """获取已发现的设备信息"""
        return {device_id: {"device_id": device_id} for device_id in self.known_devices}

    def is_connected(self) -> bool:
        """检查MQTT连接状态"""
        return self.connected


_mqtt_manager = None


def get_mqtt_manager() -> MqttManager:
    global _mqtt_manager
    if _mqtt_manager is None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication not created!")
        _mqtt_manager = MqttManager(parent=app)
    return _mqtt_manager
