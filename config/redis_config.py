# config/redis_config.py
from dataclasses import dataclass
from typing import Dict, Any
import os
import json


@dataclass
class RedisConfig:
    """Redis配置类"""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    max_connections: int = 10
    socket_timeout: int = 5
    socket_connect_timeout: int = 5

    # 缓冲策略配置
    buffer_max_size: int = 10000
    batch_size: int = 100
    flush_interval: int = 30
    ttl: int = 3600

    @property
    def url(self) -> str:
        """生成Redis连接URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"

    @classmethod
    def from_env(cls) -> "RedisConfig":
        """从环境变量加载配置"""
        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD", ""),
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "10")),
        )

    @classmethod
    def from_file(cls, config_path: str) -> "RedisConfig":
        """从配置文件加载"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            return cls(**config_data.get("redis", {}))
        except (FileNotFoundError, json.JSONDecodeError):
            # 文件不存在或格式错误时返回默认配置
            return cls()


# 全局配置实例
redis_config = RedisConfig.from_env()
