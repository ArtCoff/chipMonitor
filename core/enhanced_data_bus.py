import time
import logging
from typing import Optional, Any
from PySide6.QtCore import QTimer, Qt, Slot
from .data_bus import DataBus, DataChannel, DataMessage
from .redis_manager import redis_manager, redis_buffer
from .thread_pool import thread_pool, TaskType, TaskPriority


class EnhancedDataBus(DataBus):
    """增强版数据总线 - 集成Redis缓冲 + 线程池协调"""

    def __init__(self, enable_redis_buffer: bool = True):
        super().__init__()
        self.redis_buffer_enabled = enable_redis_buffer
        self.logger = logging.getLogger("EnhancedDataBus")

        # 🔥 线程池集成
        self.thread_pool = thread_pool

        # 🔥 连接线程池信号 - 使用正确的信号名称
        self.thread_pool.task_completed.connect(
            self._on_redis_task_completed, Qt.QueuedConnection
        )
        self.thread_pool.task_failed.connect(
            self._on_redis_task_failed, Qt.QueuedConnection
        )

        # 初始化Redis连接
        if self.redis_buffer_enabled:
            self._init_redis_connection()

        # 🔥 缓冲统计 - 简化版本
        self._buffer_stats = {
            "buffered_messages": 0,
            "buffer_errors": 0,
            "redis_connected": False,
            "pending_redis_tasks": 0,
        }

        # 🔥 定时统计和批量刷新
        self._setup_timers()

    def _init_redis_connection(self):
        """初始化Redis连接"""
        try:
            if redis_manager.connect():
                self._buffer_stats["redis_connected"] = True
                self.logger.info("✅ Enhanced DataBus Redis缓冲已启用")
            else:
                self.redis_buffer_enabled = False
                self.logger.warning("⚠️ Redis连接失败，禁用缓冲功能")
        except Exception as e:
            self.redis_buffer_enabled = False
            self.logger.error(f"❌ Redis初始化失败: {e}")

    def _setup_timers(self):
        """设置定时器 - 批量刷新和统计更新"""
        # 🔥 批量刷新定时器 - 强制刷新批量队列
        self.flush_timer = QTimer()
        self.flush_timer.timeout.connect(self._force_flush_batches)
        self.flush_timer.start(30000)  # 30秒强制刷新一次

        # 🔥 连接状态检查定时器
        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._health_check)
        self.health_timer.start(60000)  # 60秒检查一次Redis连接

    def publish(
        self,
        channel: DataChannel,
        source: str,
        data: Any,
        device_id: Optional[str] = None,
    ) -> bool:
        """发布消息 - DataBus实时 + Redis异步缓冲"""

        # 1. 🔥 立即发布到内存DataBus（保证实时性）
        success = super().publish(channel, source, data, device_id)

        # 2. 🔥 异步提交Redis缓冲任务（保证持久化，不阻塞UI）
        if success and self.redis_buffer_enabled:
            self._submit_redis_buffer_task(channel, source, data, device_id)

        return success

    def _submit_redis_buffer_task(
        self, channel: DataChannel, source: str, data: Any, device_id: Optional[str]
    ):
        """提交Redis缓冲任务到线程池 - 修复参数传递"""
        try:
            message = DataMessage(
                channel=channel, source=source, data=data, device_id=device_id
            )

            # 🔥 修复：正确传递参数给线程池
            task_id = self.thread_pool.submit(
                TaskType.DATA_PROCESSING,
                self._redis_buffer_worker,
                message,
                task_id=f"redis_{channel.value}_{int(time.time()*1000000)}",
                priority=TaskPriority.NORMAL,
                timeout=10.0,
                max_retries=1,  # 🔥 允许1次重试
            )

            if task_id:
                self._buffer_stats["pending_redis_tasks"] += 1
                self.logger.debug(f"Redis缓冲任务已提交: {task_id}")
            else:
                self._buffer_stats["buffer_errors"] += 1

        except Exception as e:
            self._buffer_stats["buffer_errors"] += 1
            self.logger.error(f"提交Redis任务失败: {e}")

    def _redis_buffer_worker(self, message: DataMessage) -> dict:
        """Redis缓冲工作函数 - 在线程池中执行"""
        start_time = time.time()
        result = {
            "success": False,
            "channel": message.channel.value,
            "device_id": message.device_id,
            "execution_time": 0,
            "error": None,
        }

        try:
            # 🔥 在子线程中执行Redis缓冲操作，启用批量模式
            success = redis_buffer.buffer_message(message, enable_batching=True)

            result.update(
                {
                    "success": success,
                    "execution_time": (time.time() - start_time) * 1000,  # 毫秒
                }
            )

            return result

        except Exception as e:
            result.update(
                {
                    "success": False,
                    "execution_time": (time.time() - start_time) * 1000,
                    "error": str(e),
                }
            )
            return result

    @Slot(str, object)
    def _on_redis_task_completed(self, task_id: str, result: dict):
        """Redis任务完成处理 - 主线程回调"""
        try:
            # 🔥 只处理Redis相关任务
            if not task_id.startswith("redis_"):
                return

            self._buffer_stats["pending_redis_tasks"] = max(
                0, self._buffer_stats["pending_redis_tasks"] - 1
            )

            if result.get("success"):
                self._buffer_stats["buffered_messages"] += 1
                execution_time = result.get("execution_time", 0)
                self.logger.debug(
                    f"Redis缓冲成功: {result.get('channel')} ({execution_time:.1f}ms)"
                )
            else:
                self._buffer_stats["buffer_errors"] += 1
                error_msg = result.get("error", "未知错误")
                self.logger.error(f"Redis缓冲失败: {error_msg}")

        except Exception as e:
            self.logger.error(f"处理Redis任务完成回调失败: {e}")

    @Slot(str, str)
    def _on_redis_task_failed(self, task_id: str, error: str):
        """Redis任务失败处理 - 主线程回调"""
        try:
            if not task_id.startswith("redis_"):
                return

            self._buffer_stats["pending_redis_tasks"] = max(
                0, self._buffer_stats["pending_redis_tasks"] - 1
            )
            self._buffer_stats["buffer_errors"] += 1

            self.logger.error(f"Redis缓冲任务失败 {task_id}: {error}")

        except Exception as e:
            self.logger.error(f"处理Redis任务失败回调失败: {e}")

    @Slot()
    def _force_flush_batches(self):
        """定时强制刷新批量队列 - 确保数据最终写入Redis"""
        if not self.redis_buffer_enabled:
            return

        try:
            # 🔥 使用线程池异步执行批量刷新，避免阻塞主线程
            task_id = self.thread_pool.submit(
                task_type=TaskType.BATCH_PROCESSING,
                func=redis_buffer.force_flush_all_batches,
                task_id=f"flush_batches_{int(time.time())}",
                priority=TaskPriority.NORMAL,
                timeout=30.0,
            )

            if task_id:
                self.logger.debug(f"批量刷新任务已提交: {task_id}")

        except Exception as e:
            self.logger.error(f"提交批量刷新任务失败: {e}")

    @Slot()
    def _health_check(self):
        """Redis连接健康检查"""
        if not self.redis_buffer_enabled:
            return

        try:
            # 🔥 快速检查Redis连接状态
            is_connected = redis_manager.is_connected()
            self._buffer_stats["redis_connected"] = is_connected

            if not is_connected:
                self.logger.warning("⚠️ Redis连接断开，尝试重连...")

                # 🔥 异步重连，避免阻塞主线程
                task_id = self.thread_pool.submit(
                    task_type=TaskType.DATA_PROCESSING,
                    func=redis_manager.reconnect,
                    task_id=f"redis_reconnect_{int(time.time())}",
                    priority=TaskPriority.HIGH,
                    timeout=10.0,
                )

                if task_id:
                    self.logger.info("Redis重连任务已提交")

        except Exception as e:
            self.logger.error(f"Redis健康检查失败: {e}")

    def get_buffer_stats(self) -> dict:
        """获取缓冲统计信息 - 增强版本"""
        # 🔥 获取基础DataBus统计
        stats = super().get_stats()

        # 🔥 添加Redis缓冲统计
        if self.redis_buffer_enabled:
            try:
                # 获取Redis缓冲区统计
                redis_stats = redis_buffer.get_buffer_stats()

                # 合并统计信息
                enhanced_stats = self._buffer_stats.copy()
                enhanced_stats.update(
                    {
                        "redis_manager_info": redis_manager.get_info(),
                        "buffer_efficiency": self._calculate_buffer_efficiency(),
                    }
                )

                stats.update(
                    {
                        "redis_buffer": enhanced_stats,
                        "redis_detailed": redis_stats,
                    }
                )

            except Exception as e:
                stats["redis_buffer_error"] = str(e)

        # 🔥 添加线程池统计
        try:
            thread_stats = self.thread_pool.get_metrics()
            stats["thread_pool"] = {
                "active_workers": thread_stats.get("active_workers", 0),
                "queue_size": thread_stats.get("queue_size", 0),
                "total_completed": thread_stats.get("total_completed", 0),
                "total_failed": thread_stats.get("total_failed", 0),
            }
        except Exception as e:
            stats["thread_pool_error"] = str(e)

        return stats

    def _calculate_buffer_efficiency(self) -> float:
        """计算缓冲效率"""
        try:
            total_attempts = (
                self._buffer_stats["buffered_messages"]
                + self._buffer_stats["buffer_errors"]
            )
            if total_attempts == 0:
                return 100.0

            return (self._buffer_stats["buffered_messages"] / total_attempts) * 100.0

        except Exception:
            return 0.0

    def force_flush_buffers(self) -> dict:
        """强制刷新所有缓冲区 - 用于调试和关闭前清理"""
        if not self.redis_buffer_enabled:
            return {"error": "Redis缓冲未启用"}

        try:
            # 🔥 同步执行批量刷新（用于关闭前的最终清理）
            flush_results = redis_buffer.force_flush_all_batches()

            # 获取Redis中的数据统计
            buffer_counts = {}
            for channel in DataChannel:
                count = redis_buffer.get_buffered_count(channel)
                if count > 0:
                    buffer_counts[channel.value] = count

            flush_results.update({"final_buffer_counts": buffer_counts})

            self.logger.info(f"强制刷新缓冲区完成: {flush_results}")
            return flush_results

        except Exception as e:
            error_msg = f"强制刷新缓冲区失败: {e}"
            self.logger.error(error_msg)
            return {"error": error_msg}

    def clear_all_buffers(self) -> dict:
        """清空所有缓冲区 - 包括内存队列和Redis"""
        if not self.redis_buffer_enabled:
            return {"error": "Redis缓冲未启用"}

        try:
            clear_results = {}

            # 🔥 逐个清空每个频道的缓冲区
            for channel in DataChannel:
                success = redis_buffer.clear_buffer(channel)
                clear_results[channel.value] = "success" if success else "failed"

            self.logger.info(f"清空所有缓冲区: {clear_results}")
            return clear_results

        except Exception as e:
            error_msg = f"清空缓冲区失败: {e}"
            self.logger.error(error_msg)
            return {"error": error_msg}

    def reconnect_redis(self) -> bool:
        """重新连接Redis - 提供给外部调用"""
        try:
            if redis_manager.reconnect():
                self.redis_buffer_enabled = True
                self._buffer_stats["redis_connected"] = True
                self.logger.info("✅ Redis重连成功")
                return True
            else:
                self.redis_buffer_enabled = False
                self._buffer_stats["redis_connected"] = False
                self.logger.error("❌ Redis重连失败")
                return False
        except Exception as e:
            self.logger.error(f"Redis重连异常: {e}")
            return False

    def shutdown(self):
        """优雅关闭 - 清理资源"""
        try:
            self.logger.info("正在关闭Enhanced DataBus...")

            # 🔥 停止定时器
            if hasattr(self, "flush_timer"):
                self.flush_timer.stop()
            if hasattr(self, "health_timer"):
                self.health_timer.stop()

            # 🔥 强制刷新所有待处理的批量数据
            if self.redis_buffer_enabled:
                self.force_flush_buffers()

            # 🔥 等待Redis任务完成
            pending_tasks = self._buffer_stats.get("pending_redis_tasks", 0)
            if pending_tasks > 0:
                self.logger.info(f"等待 {pending_tasks} 个Redis任务完成...")
                # 给一些时间让任务完成
                import time

                time.sleep(2)

            self.logger.info("Enhanced DataBus已关闭")

        except Exception as e:
            self.logger.error(f"关闭Enhanced DataBus时发生错误: {e}")


# 🔥 全局增强数据总线实例
enhanced_data_bus = EnhancedDataBus()
