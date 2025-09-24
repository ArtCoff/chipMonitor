import redis
import logging
import json
import time
import threading
from typing import Optional, Dict, Any, List
from collections import defaultdict, deque


class RedisManager:
    """Redis连接和操作管理器"""

    def __init__(self, redis_url: str = None):
        # 使用配置文件中的URL
        if redis_url is None:
            try:
                from config.redis_config import redis_config

                self.redis_url = getattr(
                    redis_config, "url", "redis://localhost:6379/0"
                )
            except (ImportError, AttributeError):
                self.redis_url = "redis://localhost:6379/0"
        else:
            self.redis_url = redis_url

        self.logger = logging.getLogger("RedisManager")

        # 🔥 同步Redis客户端（线程安全）
        self._sync_client: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None

        # 连接状态
        self._connected = False
        self._connection_attempts = 0
        self._max_retry_attempts = 3

        # 🔥 线程安全锁（用于连接状态检查）
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """建立Redis连接 - 线程池优化版本"""
        with self._lock:
            try:
                self.logger.info(f"正在连接Redis: {self.redis_url}")

                # 🔥 创建连接池，支持多线程并发
                self._connection_pool = redis.ConnectionPool.from_url(
                    self.redis_url,
                    decode_responses=True,
                    max_connections=20,  # 🔥 支持线程池并发
                    socket_connect_timeout=3,
                    socket_timeout=5,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    retry_on_timeout=True,
                    health_check_interval=30,
                )

                # 创建Redis客户端
                self._sync_client = redis.Redis(connection_pool=self._connection_pool)

                # 测试连接
                result = self._sync_client.ping()
                if result:
                    self._connected = True
                    self._connection_attempts = 0
                    self.logger.info(f"✅ Redis连接成功: {self.redis_url} (连接池: 20)")
                    return True
                else:
                    raise Exception("Redis ping 失败")

            except Exception as e:
                self._connected = False
                self._connection_attempts += 1

                self.logger.error(
                    f"❌ Redis连接失败 ({self._connection_attempts}/{self._max_retry_attempts}): {e}"
                )
                return False

    def get_client(self) -> Optional[redis.Redis]:
        """获取Redis客户端 - 线程安全"""
        # 🔥 无需加锁，Redis连接池自动处理线程安全
        if self._connected and self._sync_client:
            return self._sync_client
        return None

    def is_connected(self) -> bool:
        """检查连接状态 - 线程安全"""
        if not self._sync_client:
            return False

        try:
            # 🔥 轻量级连接检查
            self._sync_client.ping()
            return True
        except Exception:
            with self._lock:
                self._connected = False
            return False

    def reconnect(self) -> bool:
        """重连Redis - 线程安全"""
        with self._lock:
            try:
                self.logger.info("尝试重连Redis...")
                self.close()
                return self.connect()
            except Exception as e:
                self.logger.error(f"Redis重连失败: {e}")
                return False

    def close(self):
        """关闭连接 - 线程安全"""
        with self._lock:
            try:
                if self._connection_pool:
                    self._connection_pool.disconnect()

                self._sync_client = None
                self._connection_pool = None
                self._connected = False

                self.logger.info("Redis连接已关闭")
            except Exception as e:
                self.logger.error(f"关闭Redis连接失败: {e}")

    def get_info(self) -> Dict[str, Any]:
        """获取连接信息 - 线程安全"""
        with self._lock:
            return {
                "redis_url": self.redis_url,
                "connected": self._connected,
                "connection_attempts": self._connection_attempts,
                "max_retry_attempts": self._max_retry_attempts,
                "client_available": self._sync_client is not None,
                "pool_available": self._connection_pool is not None,
            }


class RedisDataBuffer:
    """Redis数据缓冲器 - 线程安全 + 批量优化"""

    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.logger = logging.getLogger("RedisDataBuffer")
        self._data_channel_enum = None
        self._buffer_strategies = None

        # 🔥 批量缓冲支持（线程安全）
        self._batch_queues = defaultdict(lambda: deque())
        self._batch_locks = defaultdict(lambda: threading.Lock())
        self._last_flush_time = defaultdict(lambda: time.time())

    @property
    def buffer_strategies(self):
        """延迟初始化缓冲策略"""
        if self._buffer_strategies is None:
            try:
                from .data_bus import DataChannel

                self._data_channel_enum = DataChannel

                self._buffer_strategies = {
                    DataChannel.TELEMETRY_DATA: {
                        "redis_type": "stream",
                        "key": "telemetry_stream",
                        "max_length": 10000,
                        "batch_size": 100,  # 🔥 优化批次大小
                        "flush_interval": 5,  # 🔥 优化刷新间隔
                        "ttl": 3600,
                    },
                    DataChannel.ALERTS: {
                        "redis_type": "list",
                        "key": "alerts_queue",
                        "max_length": 1000,
                        "batch_size": 20,  # 🔥 优化批次大小
                        "flush_interval": 2,  # 🔥 优化刷新间隔
                        "ttl": 86400,
                    },
                    DataChannel.ERRORS: {
                        "redis_type": "list",
                        "key": "errors_queue",
                        "max_length": 1000,
                        "batch_size": 20,
                        "flush_interval": 2,
                        "ttl": 86400,
                    },
                    DataChannel.DEVICE_EVENTS: {
                        "redis_type": "list",
                        "key": "device_events_queue",
                        "max_length": 2000,
                        "batch_size": 50,
                        "flush_interval": 3,
                        "ttl": 86400,
                    },
                }
            except ImportError as e:
                self.logger.warning(f"无法导入DataChannel: {e}")
                self._buffer_strategies = {}

        return self._buffer_strategies

    def buffer_message(self, message, enable_batching: bool = True) -> bool:
        """缓冲消息到Redis - 支持批量和单条"""
        client = self.redis_manager.get_client()
        if not client:
            self.logger.debug("Redis未连接，跳过缓冲")
            return False

        try:
            strategy = self.buffer_strategies.get(message.channel)
            if not strategy:
                self.logger.debug(f"频道 {message.channel.value} 未配置缓冲策略")
                return True

            # 🔥 支持批量缓冲（在线程池中调用时推荐）
            if enable_batching:
                return self._batch_buffer_message(client, message, strategy)
            else:
                return self._single_buffer_message(client, message, strategy)

        except Exception as e:
            self.logger.error(f"缓冲消息失败: {e}")
            return False

    def _batch_buffer_message(
        self, client: redis.Redis, message, strategy: dict
    ) -> bool:
        """批量缓冲消息 - 线程安全"""
        try:
            channel_key = message.channel.value

            # 🔥 线程安全的批量操作
            with self._batch_locks[channel_key]:
                # 添加到批量队列
                self._batch_queues[channel_key].append(message)

                # 检查是否需要刷新
                should_flush = (
                    len(self._batch_queues[channel_key]) >= strategy["batch_size"]
                    or (time.time() - self._last_flush_time[channel_key])
                    >= strategy["flush_interval"]
                )

                if should_flush:
                    return self._flush_batch_messages(client, message.channel, strategy)

            return True

        except Exception as e:
            self.logger.error(f"批量缓冲失败: {e}")
            return False

    def _single_buffer_message(
        self, client: redis.Redis, message, strategy: dict
    ) -> bool:
        """单条消息缓冲 - 立即写入"""
        try:
            # 准备消息数据
            message_data = {
                "channel": message.channel.value,
                "source": message.source,
                "data": (
                    json.dumps(message.data, ensure_ascii=False)
                    if not isinstance(message.data, str)
                    else message.data
                ),
                "timestamp": message.timestamp,
                "device_id": message.device_id or "",
            }

            # 根据策略选择Redis数据结构
            if strategy["redis_type"] == "stream":
                return self._buffer_to_stream(client, strategy, message_data)
            elif strategy["redis_type"] == "list":
                return self._buffer_to_list(client, strategy, message_data)

        except Exception as e:
            self.logger.error(f"单条缓冲失败: {e}")
            return False

    def _flush_batch_messages(
        self, client: redis.Redis, channel, strategy: dict
    ) -> bool:
        """刷新批量消息 - 使用Pipeline"""
        try:
            channel_key = channel.value

            # 获取待刷新的消息
            messages = list(self._batch_queues[channel_key])
            self._batch_queues[channel_key].clear()
            self._last_flush_time[channel_key] = time.time()

            if not messages:
                return True

            # 🔥 使用Pipeline批量操作，提高性能
            pipe = client.pipeline()

            for message in messages:
                message_data = {
                    "channel": message.channel.value,
                    "source": message.source,
                    "data": (
                        json.dumps(message.data, ensure_ascii=False)
                        if not isinstance(message.data, str)
                        else message.data
                    ),
                    "timestamp": message.timestamp,
                    "device_id": message.device_id or "",
                }

                if strategy["redis_type"] == "stream":
                    pipe.xadd(
                        strategy["key"],
                        message_data,
                        maxlen=strategy["max_length"],
                        approximate=True,
                    )
                elif strategy["redis_type"] == "list":
                    pipe.lpush(
                        strategy["key"], json.dumps(message_data, ensure_ascii=False)
                    )

            # 限制长度（对于list类型）
            if strategy["redis_type"] == "list":
                pipe.ltrim(strategy["key"], 0, strategy["max_length"] - 1)

            # 🔥 执行批量操作
            results = pipe.execute()

            success_count = sum(1 for r in results if r)
            self.logger.debug(
                f"批量刷新: {channel_key} ({success_count}/{len(messages)}条)"
            )

            return success_count > 0

        except Exception as e:
            self.logger.error(f"批量刷新失败: {e}")
            return False

    def _buffer_to_stream(
        self, client: redis.Redis, strategy: dict, message_data: dict
    ) -> bool:
        """缓冲到Redis Stream"""
        try:
            result = client.xadd(
                strategy["key"],
                message_data,
                maxlen=strategy["max_length"],
                approximate=True,
            )
            return bool(result)
        except Exception as e:
            self.logger.error(f"Stream缓冲失败: {e}")
            return False

    def _buffer_to_list(
        self, client: redis.Redis, strategy: dict, message_data: dict
    ) -> bool:
        """缓冲到Redis List"""
        try:
            pipe = client.pipeline()
            pipe.lpush(strategy["key"], json.dumps(message_data, ensure_ascii=False))
            pipe.ltrim(strategy["key"], 0, strategy["max_length"] - 1)

            if strategy.get("ttl"):
                pipe.expire(strategy["key"], strategy["ttl"])

            results = pipe.execute()
            return bool(results[0])  # LPUSH结果
        except Exception as e:
            self.logger.error(f"List缓冲失败: {e}")
            return False

    # 🔥 新增：强制刷新所有批量队列
    def force_flush_all_batches(self) -> Dict[str, int]:
        """强制刷新所有批量队列"""
        flush_results = {}
        client = self.redis_manager.get_client()

        if not client:
            return {"error": "Redis未连接"}

        try:
            for channel in self.buffer_strategies.keys():
                channel_key = channel.value
                strategy = self.buffer_strategies[channel]

                with self._batch_locks[channel_key]:
                    if self._batch_queues[channel_key]:
                        success = self._flush_batch_messages(client, channel, strategy)
                        flush_results[channel_key] = {
                            "success": success,
                            "messages_flushed": len(self._batch_queues[channel_key]),
                        }

        except Exception as e:
            flush_results["error"] = str(e)

        return flush_results

    # 保持其他现有方法不变...
    def get_buffered_count(self, channel) -> int:
        """获取缓冲区中的消息数量"""
        client = self.redis_manager.get_client()
        if not client:
            return 0

        try:
            strategy = self.buffer_strategies.get(channel)
            if not strategy:
                return 0

            if strategy["redis_type"] == "stream":
                return client.xlen(strategy["key"])
            elif strategy["redis_type"] == "list":
                return client.llen(strategy["key"])

        except Exception as e:
            self.logger.error(f"获取缓冲数量失败: {e}")

        return 0

    def clear_buffer(self, channel) -> bool:
        """清空指定频道的缓冲区"""
        client = self.redis_manager.get_client()
        if not client:
            return False

        try:
            strategy = self.buffer_strategies.get(channel)
            if not strategy:
                return True

            # 🔥 同时清空内存批量队列
            channel_key = channel.value
            with self._batch_locks[channel_key]:
                self._batch_queues[channel_key].clear()

            # 清空Redis中的数据
            result = client.delete(strategy["key"])
            self.logger.info(f"✅ 已清空频道 {channel.value} 的缓冲区")
            return True

        except Exception as e:
            self.logger.error(f"❌ 清空缓冲区失败: {e}")
            return False

    def get_buffer_stats(self) -> Dict[str, Any]:
        """获取缓冲统计信息"""
        stats = {
            "redis_connected": self.redis_manager.is_connected(),
            "buffer_counts": {},
            "batch_queue_sizes": {},
            "total_buffered": 0,
            "total_queued": 0,
        }

        if not self.redis_manager.is_connected():
            return stats

        try:
            for channel in self.buffer_strategies.keys():
                # Redis中的数量
                redis_count = self.get_buffered_count(channel)
                stats["buffer_counts"][channel.value] = redis_count
                stats["total_buffered"] += redis_count

                # 内存队列中的数量
                channel_key = channel.value
                queue_size = len(self._batch_queues[channel_key])
                stats["batch_queue_sizes"][channel_key] = queue_size
                stats["total_queued"] += queue_size

        except Exception as e:
            stats["error"] = str(e)

        return stats


# 🔥 全局Redis管理器实例（线程安全）
redis_manager = RedisManager()
redis_buffer = RedisDataBuffer(redis_manager)
