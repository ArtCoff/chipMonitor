"""MQTT配置文件"""

from dataclasses import dataclass
from typing import List


@dataclass
class MqttConfig:
    """MQTT配置类"""

    # 连接配置
    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "chipmonitor_client"

    # 连接参数
    keepalive: int = 60
    timeout: int = 30
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 5

    # 订阅主题
    subscribe_topics: List[str] = None
    qos: int = 1

    # 数据处理
    message_buffer_size: int = 1000
    batch_size: int = 50

    def __post_init__(self):
        if self.subscribe_topics is None:
            self.subscribe_topics = [
                "factory/telemetry/+/+/msgpack",
                "gateway/+/status",
                "gateway/+/info",
            ]


# 默认配置实例
default_mqtt_config = MqttConfig()


# 配置保存/加载函数
def save_config(config: MqttConfig, file_path: str = "mqtt_config.json"):
    """保存配置到文件"""
    import json
    from pathlib import Path

    try:
        config_dict = {
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "password": config.password,
            "client_id": config.client_id,
            "keepalive": config.keepalive,
            "timeout": config.timeout,
            "reconnect_delay": config.reconnect_delay,
            "max_reconnect_attempts": config.max_reconnect_attempts,
            "subscribe_topics": config.subscribe_topics,
            "qos": config.qos,
            "message_buffer_size": config.message_buffer_size,
            "batch_size": config.batch_size,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


def load_config(file_path: str = "mqtt_config.json") -> MqttConfig:
    """从文件加载配置"""
    import json
    from pathlib import Path

    try:
        if not Path(file_path).exists():
            return default_mqtt_config

        with open(file_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)

        return MqttConfig(**config_dict)
    except Exception as e:
        print(f"加载配置失败: {e}")
        return default_mqtt_config


# 获取当前配置
def get_current_config() -> MqttConfig:
    """获取当前配置"""
    return load_config()
