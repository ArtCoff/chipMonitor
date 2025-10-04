import paho.mqtt.client as mqtt
import json
import time
import logging
import msgpack
from typing import Dict, List, Optional, Callable, Set, Any
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from .thread_pool import thread_pool, TaskType, TaskPriority
from .data_bus import data_bus, DataChannel, DataMessage


class MqttManager(QObject):
    # 定义信号
    connection_changed = Signal(bool, str)  # 连接状态变化：(是否连接, 消息)
    statistics_updated = Signal(dict)  # 统计信息更新
    topic_subscribed = Signal(str, bool)  # 主题订阅结果：(主题, 是否成功)
    connection_status = Signal(str)  # 连接状态文本
    message_received = Signal(str, bytes, int)  # (主题, 载荷, QoS)

    def __init__(self):
        super().__init__()
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
        # 设备管理
        self.known_devices: Set[str] = set()

        # 统计定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._emit_statistics)
        self.stats_timer.start(2000)  # 每2秒发送统计信息
        logging.info("MQTT管理器已初始化")
        thread_pool.task_completed.connect(
            self._on_device_data_processed, Qt.QueuedConnection
        )
        thread_pool.task_failed.connect(
            self._on_device_data_processing_failed, Qt.QueuedConnection
        )

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
            logging.error(error_msg)
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
                logging.info("MQTT连接已断开")
        except Exception as e:
            logging.error(f"断开连接失败: {e}")

    def subscribe_topic(self, topic: str, qos: int = 0) -> bool:
        """订阅主题"""
        try:
            if self.client and self.connected:
                result, _ = self.client.subscribe(topic, qos)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    self.subscriptions[topic] = qos
                    logging.info(f"订阅主题: {topic} (QoS: {qos})")
                    return True
                else:
                    logging.error(f"订阅主题失败: {topic}, 错误码: {result}")
                    self.topic_subscribed.emit(topic, False)
                    return False
            else:
                # 保存订阅，连接后自动订阅
                self.subscriptions[topic] = qos
                logging.info(f"保存订阅主题: {topic} (连接后将自动订阅)")
                return True
        except Exception as e:
            logging.error(f"订阅主题失败: {e}")
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
                    logging.info(f"取消订阅主题: {topic}")
                    return True
            return False
        except Exception as e:
            logging.error(f"取消订阅主题失败: {e}")
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
                    logging.error(f"发布消息失败: 错误码 {result.rc}")
                    return False
            except Exception as e:
                logging.error(f"发布消息失败: {e}")
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
            logging.info("MQTT连接成功")
            self.connection_changed.emit(True, success_msg)
            self.connection_status.emit("已连接")

            # 重新订阅所有主题
            for topic, qos in self.subscriptions.items():
                client.subscribe(topic, qos)
                logging.info(f"重新订阅主题: {topic}")

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
            logging.error(error_msg)
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
            logging.warning(disconnect_msg)
            self.connection_changed.emit(False, disconnect_msg)
            self.connection_status.emit("连接断开")

            # 启动重连
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self.reconnect_timer.start(self.reconnect_interval)
        else:
            disconnect_msg = "MQTT正常断开连接"
            logging.info(disconnect_msg)
            self.connection_changed.emit(False, disconnect_msg)
            self.connection_status.emit("已断开")

    def _on_message(self, client, userdata, msg):
        """消息接收回调 —— 提交到线程池异步处理"""
        try:
            topic = msg.topic
            payload = msg.payload
            qos = msg.qos
            properties = getattr(msg, "properties", None)

            self.stats["messages_received"] += 1
            self.stats["last_message_time"] = time.time()
            self.stats["bytes_received"] += len(msg.payload)
            # logging.info(f"📥 收到MQTT消息: {topic} | {len(payload)}字节")

            if self._is_device_telemetry_topic(topic):
                # 提交到线程池
                # task_id：使用消息序号 + 时间戳
                task_id = (
                    f"mqtt_{self.stats['messages_received']}_{int(time.time()*1000)}"
                )
                # logging.info(f"🔄 提交解析任务: {task_id} | {topic}")

                success = thread_pool.submit(
                    TaskType.DATA_PROCESSING,  # 或 ANALYTICS
                    self._parse_device_message,  # 子线程执行的函数
                    topic,
                    payload,
                    qos,
                    task_id=task_id,
                    priority=TaskPriority.REALTIME,  # 高优先级，确保实时性
                    callback=None,  # 不使用 callback，用信号
                    timeout=5.0,  # 5秒超时
                )
                if success:
                    pass
                    # logging.info(f"✅ 任务提交成功: {task_id}")
                else:
                    logging.error(f"❌ 任务提交失败: {task_id}")

            elif self._is_gateway_topic(topic):
                self._handle_gateway_message(topic, payload, qos, properties)
            else:
                self._handle_system_message(topic, payload, qos, properties)

        except Exception as e:
            logging.error(f"处理MQTT消息失败: {e}")

    def _parse_device_message(
        self, topic: str, payload: bytes, qos: int
    ) -> Optional[dict]:
        """解析设备消息"""
        parse_start_time = time.time()
        try:
            data = None
            format_type = None
            clean_topic = topic
            if topic.endswith("/msgpack"):
                try:
                    data = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                    format_type = "MessagePack"
                    clean_topic = topic[:-8]  # 移除后缀
                except Exception as e:
                    return self._create_error_result(
                        topic, payload, qos, f"MessagePack解析失败: {e}"
                    )
            elif topic.endswith("/json"):
                try:
                    data = json.loads(payload.decode("utf-8"))
                    format_type = "JSON"
                    clean_topic = topic[:-5]  # 移除后缀
                except Exception as e:
                    return self._create_error_result(
                        topic, payload, qos, f"Json解析失败: {e}"
                    )
            else:
                try:
                    data = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                    format_type = "MessagePack"
                except Exception:
                    try:
                        data = json.loads(payload.decode("utf-8"))
                        format_type = "JSON"
                    except Exception:
                        return self._create_error_result(
                            topic, payload, qos, "未知数据格式，非MessagePack或JSON"
                        )
            # 提取设备信息
            device_info = self._extract_device_info(clean_topic)
            if not device_info:
                logging.debug(f"无法从主题提取设备信息: {clean_topic}")
                return self._create_error_result(
                    topic, payload, qos, "无法提取设备信息"
                )
            return self._process_data(
                data,
                device_info,
                clean_topic,
                qos,
                format_type,
                payload,
                parse_start_time,
            )

        except Exception as e:
            logging.error(f"解析设备消息失败 {topic}: {e}")
            return None

    def _extract_device_info(self, topic: str) -> Optional[dict]:
        """从主题提取设备信息"""
        try:
            parts = topic.split("/")

            if len(parts) >= 4 and parts[0] == "factory" and parts[1] == "telemetry":
                # factory/telemetry/{device_type}/{device_id}
                device_type = parts[2]
                device_id = parts[3]

                # 解析设备ID: LAM_ETCH_000 -> 厂商_类型_编号
                id_parts = device_id.split("_")
                vendor = id_parts[0] if len(id_parts) > 0 else "UNKNOWN"

                return {
                    "device_id": device_id,
                    "device_type": device_type,
                    "vendor": vendor,
                    "event": "online",
                    "timestamp": time.time(),
                    "topic": topic,
                    "status": {"last_update": time.time()},
                }
            return None

        except Exception as e:
            logging.debug(f"提取设备信息失败: {topic} -> {e}")
            return None

    def _process_data(
        self,
        data: any,
        device_info: dict,
        topic: str,
        qos: int,
        format_type: str,
        payload: bytes,
        parse_start_time: float,
    ) -> dict:
        result = {
            "device_id": device_info["device_id"],
            "device_type": device_info["device_type"],
            "vendor": device_info.get("vendor", "UNKNOWN"),
            "topic": topic,
            "timestamp": time.time(),
            "qos": qos,
            "parse_success": True,
            "parse_time": (time.time() - parse_start_time) * 1000,
            "data_format": format_type,
            "data_size": len(payload),
        }
        if not isinstance(data, list):
            logging.warning(
                f"期望数组格式但是收到{type(data)}:{device_info['device_id']}"
            )
            return {
                **result,
                "parse_success": False,
                "parse_error": "数据格式错误，期望数组",
            }
        if not data:
            logging.warning(f"收到空数据数组: {device_info['device_id']}")
            return {
                **result,
                "parse_success": False,
                "parse_error": "空数据数组",
            }
        batch_size = len(data)
        result.update({"batch_size": batch_size})

        # 使用第一条记录进行字段映射（无论单条还是多条）
        first_record = data[0]
        if isinstance(first_record, dict):
            mapped_fields = self._map_fields(first_record)
            result.update(mapped_fields)
            result["sample_record"] = mapped_fields

            # 只有多条记录时才进行时间跨度分析
            if batch_size > 1:
                time_span_info = self._analyze_batch_timespan(data)
                result.update(time_span_info)
            else:
                # 单条记录的时间信息
                result.update(
                    {
                        "batch_has_timespan": False,
                        "batch_time_span": 0,
                        "batch_data_density": float("inf"),
                    }
                )
        else:
            logging.warning(f"数组中的记录不是字典格式: {type(first_record)}")
            result["raw_first_record"] = first_record

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
            logging.debug(f"时间跨度分析失败: {e}")

        return {
            "batch_time_span": None,
            "batch_data_density": None,
            "batch_has_timespan": False,
        }

    def _create_error_result(
        self, topic: str, payload: bytes, qos: int, error_msg: str
    ) -> dict:
        """创建错误结果"""
        # 尝试从主题提取基本信息
        device_info = self._extract_device_info(topic) or {
            "device_id": "unknown",
            "device_type": "ERROR",
            "vendor": "UNKNOWN",
        }

        return {
            "device_id": device_info["device_id"],
            "device_type": device_info["device_type"],
            "vendor": device_info.get("vendor", "UNKNOWN"),
            "topic": topic,
            "timestamp": time.time(),
            "qos": qos,
            "parse_success": False,
            "parse_error": error_msg,
            "data_size": len(payload),
            "raw_payload_preview": (
                str(payload[:100]) + "..." if len(payload) > 100 else str(payload)
            ),
        }

    def _on_publish(self, client, userdata, mid):
        """发布回调"""
        logging.debug(f"消息发布成功: {mid}")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """订阅回调"""
        logging.debug(f"订阅成功: {mid}, QoS: {granted_qos}")

    def _attempt_reconnect(self):
        """尝试重连"""
        if not self.connected and self.client:
            self.reconnect_attempts += 1
            if self.reconnect_attempts <= self.max_reconnect_attempts:
                try:
                    logging.info(f"尝试重新连接MQTT... (第{self.reconnect_attempts}次)")
                    self.connection_status.emit(
                        f"重连中... ({self.reconnect_attempts}/{self.max_reconnect_attempts})"
                    )
                    self.client.reconnect()
                except Exception as e:
                    logging.debug(f"重连失败: {e}")
            else:
                logging.error("达到最大重连次数，停止重连")
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
                logging.info("配置已更改，将重新连接")
                self.disconnect()
                # 短暂延迟后重新连接
                QTimer.singleShot(1000, lambda: self.connect())

            return True
        except Exception as e:
            logging.error(f"更新MQTT配置失败: {e}")
            return False

    def _on_device_data_processed(self, task_id: str, result: Any):
        """主线程：设备数据处理完成-发布到数据总线data_bus"""
        try:
            if not isinstance(result, dict):
                logging.warning(f"任务 {task_id} 返回无效数据类型: {type(result)}")
                return

            device_id = result.get("device_id")
            if not device_id:
                logging.warning(f"任务 {task_id} 缺少 device_id")
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
                data_bus.publish(
                    channel=DataChannel.DEVICE_EVENTS,
                    source="mqtt_client",
                    data=device_info,
                    device_id=device_id,
                )

            # 增强的日志记录 - 区分批次和单条
            parse_success = result.get("parse_success", True)

            if parse_success:

                channel = DataChannel.TELEMETRY_DATA
                success = data_bus.publish(
                    channel=channel,
                    source="mqtt_client",
                    data=result,
                    device_id=device_id,
                )
                if success:
                    pass
                    # logging.info(f"✅ DataBus发布成功: {device_id}")
                else:
                    logging.error(f"❌ DataBus发布失败: {device_id}")

            else:
                error_data = {
                    "device_id": device_id,
                    "error": result.get("parse_error", "未知错误"),
                    "task_id": task_id,
                }
                data_bus.publish(
                    channel=DataChannel.ERRORS,
                    source="mqtt_client",
                    data=error_data,
                    device_id=device_id,
                )

        except Exception as e:
            logging.error(f"处理任务回调失败: {task_id} -> {e}")
            try:
                data_bus.publish(
                    channel=DataChannel.ERRORS,
                    source="mqtt_client",
                    data={
                        "error": str(e),
                        "task_id": task_id,
                        "error_type": "callback_failure",
                    },
                )
            except:
                pass  # 避免递归错误

    def _is_device_telemetry_topic(self, topic: str) -> bool:
        """判断是否为设备遥测数据主题"""
        clean_topic = topic
        if topic.endswith("/msgpack"):
            clean_topic = topic[:-8]
        elif topic.endswith("/json"):
            clean_topic = topic[:-5]

        parts = clean_topic.split("/")
        return len(parts) >= 4 and parts[0] == "factory" and parts[1] == "telemetry"

    def _is_gateway_topic(self, topic: str) -> bool:
        """判断是否为网关主题 - 支持格式后缀"""
        clean_topic = topic
        if topic.endswith("/msgpack") or topic.endswith("/json"):
            clean_topic = topic.rsplit("/", 1)[0]

        parts = clean_topic.split("/")
        return len(parts) >= 3 and parts[0] == "gateway"

    def _handle_gateway_message(
        self, topic: str, payload: bytes, qos: int, properties: dict = None
    ):
        """处理网关消息 - 支持格式后缀"""
        try:
            # 🔥 检查并处理网关消息的格式后缀
            clean_topic = topic
            content_format = "auto"

            if topic.endswith("/msgpack"):
                content_format = "msgpack"
                clean_topic = topic[:-8]
            elif topic.endswith("/json"):
                content_format = "json"
                clean_topic = topic[:-5]
            elif topic.endswith("/status") or topic.endswith("/config"):
                content_format = "text"  # 网关状态通常是文本

            parts = clean_topic.split("/")
            if len(parts) < 3:
                return

            gateway_id = parts[1]
            function = parts[2]

            # 🔥 根据格式解析网关消息
            message_data = self._parse_gateway_payload(payload, content_format)

            # 创建网关消息结果
            gateway_result = {
                "device_id": gateway_id,
                "device_type": "GATEWAY",
                "vendor": "SYSTEM",
                "topic": clean_topic,
                "original_topic": topic,  # 保留原始主题
                "function": function,
                "timestamp": time.time(),
                "qos": qos,
                "data_size": len(payload),
                "message_type": "gateway_message",
                **message_data,
            }

            # 发布到DataBus
            data_bus.publish(
                channel=DataChannel.DEVICE_EVENTS,
                source="mqtt_client",
                data=gateway_result,
                device_id=gateway_id,
            )

            logging.info(
                f"网关消息处理完成: {gateway_id}/{function} [{content_format}]"
            )

        except Exception as e:
            logging.error(f"处理网关消息失败 {topic}: {e}")

    def _handle_system_message(
        self, topic: str, payload: bytes, qos: int, properties: dict = None
    ):
        """处理系统消息"""
        try:
            parts = topic.split("/")
            message_type = parts[0] if parts else "unknown"

            # 简单记录系统消息
            logging.info(f"系统消息: {topic} | {len(payload)}字节")

            # 发布系统事件
            data_bus.publish(
                channel=DataChannel.DEVICE_EVENTS,
                source="mqtt_client",
                data={
                    "event_type": "system_message",
                    "topic": topic,
                    "message_type": message_type,
                    "payload_size": len(payload),
                    "timestamp": time.time(),
                },
            )

        except Exception as e:
            logging.error(f"处理系统消息失败 {topic}: {e}")

    def _parse_gateway_payload(self, payload: bytes, format_hint: str) -> dict:
        """根据格式提示解析网关载荷"""

        result = {
            "parse_success": False,
            "content_type": format_hint,
            "parsed_data": None,
        }

        try:
            if format_hint == "msgpack":
                # MessagePack格式
                data = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                result.update(
                    {
                        "parse_success": True,
                        "content_type": "msgpack",
                        "parsed_data": data,
                    }
                )
            elif format_hint == "json":
                # JSON格式
                data = json.loads(payload.decode("utf-8"))
                result.update(
                    {"parse_success": True, "content_type": "json", "parsed_data": data}
                )
            else:
                # 文本或自动检测
                try:
                    text = payload.decode("utf-8")
                    result.update(
                        {
                            "parse_success": True,
                            "content_type": "text",
                            "parsed_data": {"text": text, "length": len(text)},
                        }
                    )
                except UnicodeDecodeError:
                    # 二进制数据
                    result.update(
                        {
                            "parse_success": True,
                            "content_type": "binary",
                            "parsed_data": {
                                "size": len(payload),
                                "preview": str(payload[:50]),
                            },
                        }
                    )

        except Exception as e:
            result["parse_error"] = str(e)

        return result

    def _on_device_data_processing_failed(self, task_id: str, error: str):
        logging.error(f"[失败] 设备数据处理失败 {task_id}: {error}")
        self.connection_status.emit(f"数据处理失败: {error[:50]}...")
        try:
            data_bus.publish(
                channel=DataChannel.ERRORS,
                source="mqtt_client",
                data={
                    "error": error,
                    "task_id": task_id,
                    "error_type": "processing_failure",
                },
            )
        except Exception as e:
            logging.error(f"发布处理失败事件失败: {e}")

    def get_discovered_devices(self) -> Dict[str, dict]:
        """获取已发现的设备信息"""
        return {device_id: {"device_id": device_id} for device_id in self.known_devices}

    def is_connected(self) -> bool:
        """检查MQTT连接状态"""
        return self.connected


# 全局MQTT管理器
mqtt_manager = MqttManager()
