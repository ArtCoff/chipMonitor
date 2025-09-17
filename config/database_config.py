import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class DatabaseConfig:
    """统一的数据库配置类"""

    host: str = "localhost"
    port: int = 5435
    database: str = "semiconductor_db"
    username: str = "app_user"
    password: str = "app_pass"

    # 连接配置
    connection_timeout: int = 10
    max_connections: int = 20

    # 存储配置
    batch_size: int = 500
    storage_interval: int = 300  # 5分钟

    # 高级配置
    min_connections: int = 5
    pool_recycle: int = 3600
    ssl_mode: str = "prefer"
    echo: bool = False

    @property
    def connection_url(self) -> str:
        """生成数据库连接URL"""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    def get_connection_params(self) -> dict:
        """获取连接参数"""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.username,
            "password": self.password,
            "connect_timeout": self.connection_timeout,
            "sslmode": self.ssl_mode,
        }

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DatabaseConfig":
        """从字典创建"""
        return cls(**data)

    def save_to_file(self, config_path: str = "config/database.json"):
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.getLogger(__name__).error(f"保存数据库配置失败: {e}")

    @classmethod
    def load_from_file(
        cls, config_path: str = "config/database.json"
    ) -> "DatabaseConfig":
        """从文件加载配置"""
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls.from_dict(data)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"加载数据库配置失败，使用默认配置: {e}"
            )

        return cls()


@dataclass
class DatabaseStats:
    """数据库统计信息"""

    connected: bool = False
    total_records: int = 0
    telemetry_count: int = 0
    alerts_count: int = 0
    events_count: int = 0
    database_size_mb: float = 0.0
    last_check_time: Optional[float] = None


# 🔥 全局配置实例
database_config = DatabaseConfig.load_from_file()
