import time
import logging
import threading
from typing import Dict, List, Any
from collections import deque, defaultdict
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from core.data_bus import get_data_bus, DataChannel, DataMessage
from core.database_manager import get_db_manager
from core.thread_pool import get_thread_pool, TaskType, TaskPriority


class DatabasePersistenceService(QObject):
    """数据库持久化服务 - 独立服务，订阅DataBus并批量写入数据库"""

    # 服务状态信号
    service_started = Signal()
    service_stopped = Signal()
    batch_processed = Signal(str, dict)  # (channel, result)
    batch_failed = Signal(str, str)  # (channel, error)
    stats_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("DatabasePersistenceService")
        self.data_bus = get_data_bus()
        self.db_manager = get_db_manager()
        self.thread_pool = get_thread_pool()
        # 🔥 服务状态
        self._running = False
        self._subscribed = False

        # 🔥 批量策略配置
        self.batch_strategies = {
            DataChannel.TELEMETRY_DATA: {
                "batch_size": 50,
                "flush_interval": 10,  # 秒
                "enable_persistence": True,
            },
            DataChannel.ALERTS: {
                "batch_size": 20,
                "flush_interval": 5,
                "enable_persistence": True,
            },
            DataChannel.DEVICE_EVENTS: {
                "batch_size": 30,
                "flush_interval": 8,
                "enable_persistence": True,
            },
            DataChannel.ERRORS: {
                "batch_size": 10,
                "flush_interval": 3,
                "enable_persistence": True,
            },
        }

        # 🔥 批量队列（线程安全）
        self.batch_queues = defaultdict(lambda: deque())
        self.batch_locks = defaultdict(lambda: threading.Lock())
        self.last_flush_time = defaultdict(lambda: time.time())

        # 🔥 统计信息
        self.stats = {
            "service_uptime": 0,
            "messages_received": 0,
            "messages_batched": 0,
            "messages_persisted": 0,
            "batch_flushes": 0,
            "batch_errors": 0,
            "channels_active": 0,
        }
        self._start_time = 0

        # 定时器
        self.flush_timer = QTimer()
        self.stats_timer = QTimer()

        self.logger.info("数据库持久化服务已初始化")

    def start(self) -> bool:
        """启动持久化服务"""
        try:
            if self._running:
                self.logger.warning("持久化服务已在运行中")
                return True

            # 检查数据库连接
            if not self.db_manager.is_connected():
                self.logger.error("数据库未连接，无法启动持久化服务")
                return False

            # 订阅所有数据频道
            self._subscribe_channels()

            # 启动定时器
            self.flush_timer.timeout.connect(self._scheduled_flush)
            self.flush_timer.start(30000)  # 30秒强制刷新

            self.stats_timer.timeout.connect(self._update_stats)
            self.stats_timer.start(10000)  # 10秒更新统计

            self._running = True
            self._start_time = time.time()

            self.service_started.emit()
            self.logger.info("数据库持久化服务已启动")
            return True

        except Exception as e:
            self.logger.error(f"启动持久化服务失败: {e}")
            return False

    def stop(self) -> bool:
        """停止持久化服务"""
        try:
            if not self._running:
                self.logger.warning("持久化服务未在运行")
                return True

            self.logger.info("正在停止数据库持久化服务...")

            # 🔥 停止定时器
            self.flush_timer.stop()
            self.stats_timer.stop()

            # 🔥 强制刷新所有待处理数据
            self._flush_all_batches_sync()

            # 🔥 取消订阅
            self._unsubscribe_channels()

            self._running = False

            self.service_stopped.emit()
            self.logger.info("数据库持久化服务已停止")
            return True

        except Exception as e:
            self.logger.error(f"停止持久化服务失败: {e}")
            return False

    def _subscribe_channels(self):
        """订阅所有数据频道"""
        try:
            for channel in DataChannel:
                success = self.data_bus.subscribe(channel, self._on_message_received)
                if success:
                    self.logger.debug(f"已订阅频道: {channel.value}")
                else:
                    self.logger.error(f"订阅频道失败: {channel.value}")

            self._subscribed = True

        except Exception as e:
            self.logger.error(f"订阅频道失败: {e}")

    def _unsubscribe_channels(self):
        """取消订阅所有频道"""
        try:
            for channel in DataChannel:
                self.data_bus.unsubscribe(channel, self._on_message_received)
                self.logger.debug(f"已取消订阅: {channel.value}")

            self._subscribed = False

        except Exception as e:
            self.logger.error(f"取消订阅失败: {e}")

    @Slot()
    def _on_message_received(self, message: DataMessage):
        """接收到数据总线消息"""
        try:
            if not self._running:
                return

            # 检查是否启用持久化
            strategy = self.batch_strategies.get(message.channel)
            if not strategy or not strategy.get("enable_persistence", True):
                return

            # 🔥 添加到批量队列
            self._add_to_batch(message, strategy)

            self.stats["messages_received"] += 1

        except Exception as e:
            self.logger.error(f"处理接收消息失败: {e}")

    def _add_to_batch(self, message: DataMessage, strategy: dict):
        """添加消息到批量队列"""
        channel_key = message.channel.value

        with self.batch_locks[channel_key]:
            self.batch_queues[channel_key].append(message)
            self.stats["messages_batched"] += 1

            # 检查是否需要刷新
            should_flush = (
                len(self.batch_queues[channel_key]) >= strategy["batch_size"]
                or (time.time() - self.last_flush_time[channel_key])
                >= strategy["flush_interval"]
            )

            if should_flush:
                self._flush_batch_async(message.channel, strategy)

    def _flush_batch_async(self, channel: DataChannel, strategy: dict):
        """异步刷新批量数据"""
        try:
            submit_kwargs = {
                "task_type": TaskType.BATCH_PROCESSING,
                "func": self._batch_worker,
                "task_id": f"db_batch_{channel.value}_{int(time.time())}",
                "priority": TaskPriority.NORMAL,
                "timeout": 30.0,
            }
            task_id = self.thread_pool.submit(
                TaskType.BATCH_PROCESSING,
                self._batch_worker,
                channel,
                strategy,
                task_id=f"db_batch_{channel.value}_{int(time.time())}",
                priority=TaskPriority.NORMAL,
                timeout=30.0,
            )

            if task_id:
                self.logger.debug(f"数据库批量任务已提交: {task_id}")

        except Exception as e:
            self.logger.error(f"提交批量任务失败: {e}")
            self.stats["batch_errors"] += 1

    def _batch_worker(self, channel: DataChannel, strategy: dict) -> dict:
        """批量写入工作函数"""
        start_time = time.time()
        result = {"success": False, "processed": 0, "errors": []}

        try:
            channel_key = channel.value

            # 获取待处理消息
            with self.batch_locks[channel_key]:
                messages = list(self.batch_queues[channel_key])
                self.batch_queues[channel_key].clear()
                self.last_flush_time[channel_key] = time.time()

            if not messages:
                return {"success": True, "processed": 0}

            # 🔥 根据频道类型调用数据库管理器的批量插入
            if self.db_manager.is_connected():
                if channel == DataChannel.TELEMETRY_DATA:
                    result = self.db_manager.batch_insert_telemetry(messages)
                elif channel == DataChannel.ALERTS:
                    result = self.db_manager.batch_insert_alerts(messages)
                elif channel == DataChannel.DEVICE_EVENTS:
                    result = self.db_manager.batch_insert_events(messages)
                elif channel == DataChannel.ERRORS:
                    result = self.db_manager.batch_insert_errors(messages)

                if result["success"]:
                    self.stats["messages_persisted"] += result.get("processed", 0)
                    self.stats["batch_flushes"] += 1
                    self.batch_processed.emit(channel.value, result)
                else:
                    self.stats["batch_errors"] += 1
                    self.batch_failed.emit(channel.value, str(result.get("errors")))
            else:
                result = {"success": False, "processed": 0, "errors": ["数据库未连接"]}
                self.stats["batch_errors"] += 1
                self.batch_failed.emit(channel.value, "数据库未连接")

            result["execution_time"] = (time.time() - start_time) * 1000

            if result["success"]:
                self.logger.info(
                    f"数据库批量写入完成: {channel.value} "
                    f"({result['processed']}条, {result['execution_time']:.1f}ms)"
                )

            return result

        except Exception as e:
            error_msg = f"批量写入失败: {e}"
            result["errors"].append(error_msg)
            self.logger.error(error_msg)
            self.stats["batch_errors"] += 1
            self.batch_failed.emit(channel.value, error_msg)
            return result

    @Slot()
    def _scheduled_flush(self):
        """定时强制刷新所有批量队列"""
        try:
            if not self._running:
                return

            flushed_channels = []

            for channel, strategy in self.batch_strategies.items():
                channel_key = channel.value

                with self.batch_locks[channel_key]:
                    queue_size = len(self.batch_queues[channel_key])

                if queue_size > 0:
                    self._flush_batch_async(channel, strategy)
                    flushed_channels.append(f"{channel.value}({queue_size})")

            if flushed_channels:
                self.logger.info(f"定时刷新批量队列: {', '.join(flushed_channels)}")

        except Exception as e:
            self.logger.error(f"定时刷新失败: {e}")

    def _flush_all_batches_sync(self):
        """同步刷新所有批量队列（用于停止服务时）"""
        try:
            for channel, strategy in self.batch_strategies.items():
                channel_key = channel.value

                with self.batch_locks[channel_key]:
                    messages = list(self.batch_queues[channel_key])
                    self.batch_queues[channel_key].clear()

                if messages and self.db_manager.is_connected():
                    if channel == DataChannel.TELEMETRY_DATA:
                        self.db_manager.batch_insert_telemetry(messages)
                    elif channel == DataChannel.ALERTS:
                        self.db_manager.batch_insert_alerts(messages)
                    elif channel == DataChannel.DEVICE_EVENTS:
                        self.db_manager.batch_insert_events(messages)
                    elif channel == DataChannel.ERRORS:
                        self.db_manager.batch_insert_errors(messages)

                    self.logger.info(
                        f"同步刷新 {channel.value}: {len(messages)} 条记录"
                    )

        except Exception as e:
            self.logger.error(f"同步刷新失败: {e}")

    @Slot()
    def _update_stats(self):
        """更新统计信息"""
        try:
            if self._running:
                self.stats["service_uptime"] = time.time() - self._start_time
                self.stats["channels_active"] = len(
                    [ch for ch, queue in self.batch_queues.items() if queue]
                )

                self.stats_updated.emit(self.stats.copy())

        except Exception as e:
            self.logger.error(f"更新统计失败: {e}")

    def get_service_stats(self) -> dict:
        """获取服务统计信息"""
        stats = self.stats.copy()

        # 添加队列状态
        queue_stats = {}
        for channel_key, queue in self.batch_queues.items():
            with self.batch_locks[channel_key]:
                queue_stats[channel_key] = len(queue)

        stats.update(
            {
                "running": self._running,
                "subscribed": self._subscribed,
                "queue_sizes": queue_stats,
                "database_connected": self.db_manager.is_connected(),
                "batch_strategies": {
                    ch.value: strategy for ch, strategy in self.batch_strategies.items()
                },
            }
        )

        return stats

    def manual_flush_channel(self, channel: DataChannel) -> bool:
        """手动刷新指定频道"""
        try:
            if not self._running:
                return False

            strategy = self.batch_strategies.get(channel)
            if not strategy:
                return False

            self._flush_batch_async(channel, strategy)
            return True

        except Exception as e:
            self.logger.error(f"手动刷新频道失败: {e}")
            return False

    def update_batch_strategy(
        self,
        channel: DataChannel,
        batch_size: int = None,
        flush_interval: int = None,
        enable_persistence: bool = None,
    ):
        """更新批量策略"""
        try:
            if channel not in self.batch_strategies:
                return False

            strategy = self.batch_strategies[channel]

            if batch_size is not None:
                strategy["batch_size"] = max(1, batch_size)
            if flush_interval is not None:
                strategy["flush_interval"] = max(1, flush_interval)
            if enable_persistence is not None:
                strategy["enable_persistence"] = enable_persistence

            self.logger.info(f"已更新 {channel.value} 批量策略: {strategy}")
            return True

        except Exception as e:
            self.logger.error(f"更新批量策略失败: {e}")
            return False


# 🔥 全局数据库持久化服务实例
database_persistence_service = DatabasePersistenceService()
