import logging
import time
from typing import Dict, List, Optional, Callable, Any, Union
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
from PySide6.QtCore import QObject, Signal, QTimer
import threading
from weakref import WeakMethod, ref
from .redis_manager import redis_manager, redis_buffer


class DataChannel(Enum):
    """数据频道枚举"""

    # 核心业务频道
    TELEMETRY_DATA = "telemetry_data"  # 遥测数据
    ALERTS = "alerts"  # 告警信息
    ERRORS = "errors"  # 错误信息
    DEVICE_EVENTS = "device_events"  # 设备事件（连接/断开/发现）


@dataclass
class DataMessage:
    """数据消息"""

    channel: DataChannel
    source: str
    data: Any
    timestamp: float = None
    device_id: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class DataBus(QObject):
    """数据总线 - 弱引用 + 异步投递"""

    # 系统信号
    message_published = Signal(str, str)  # (channel, source)
    message_delivered = Signal(str, int)  # (channel, subscriber_count)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("DataBus")

        # 🔥 使用弱引用存储订阅者，避免内存泄漏
        self._subscribers: Dict[DataChannel, List[Union[WeakMethod, ref]]] = (
            defaultdict(list)
        )
        # 线程安全锁
        self._lock = threading.RLock()
        # 两种投递模式配置
        self._delivery_config = {
            # 需要立即响应的频道（同步投递）
            "sync_channels": {
                DataChannel.ALERTS,
                DataChannel.ERRORS,
                DataChannel.DEVICE_EVENTS,
            },
            # 可以延迟处理的频道（异步投递）
            "async_channels": {DataChannel.TELEMETRY_DATA},
        }
        # 统计信息
        self._stats = {
            "published": 0,
            "delivered": 0,
            "errors": 0,
            "auto_cleaned": 0,  # 自动清理的失效订阅者数量
        }

        self.logger.info("DataBus已初始化")

    def subscribe(
        self, channel: DataChannel, callback: Callable[[DataMessage], None]
    ) -> bool:
        """订阅频道 - 使用弱引用"""
        try:
            with self._lock:
                # 🔥 包装为弱引用，自动清理失效订阅者
                if hasattr(callback, "__self__"):
                    # 对象方法使用WeakMethod
                    weak_cb = WeakMethod(callback)
                else:
                    # 普通函数使用ref
                    weak_cb = ref(callback)

                # 检查是否已存在
                existing_callbacks = self._get_live_callbacks(channel)
                if any(cb == callback for cb in existing_callbacks):
                    self.logger.warning(
                        f"重复订阅: {callback.__name__} -> {channel.value}"
                    )
                    return False

                self._subscribers[channel].append(weak_cb)
                self.logger.info(f"订阅成功: {callback.__name__} -> {channel.value}")
                return True

        except Exception as e:
            self.logger.error(f"订阅失败: {e}")
            return False

    def unsubscribe(
        self, channel: DataChannel, callback: Callable[[DataMessage], None]
    ) -> bool:
        """取消订阅"""
        try:
            with self._lock:
                # 查找并移除对应的弱引用
                removed = False
                for weak_cb in self._subscribers[channel][
                    :
                ]:  # 复制列表以避免修改时的问题
                    cb = weak_cb() if hasattr(weak_cb, "__call__") else None
                    if cb == callback:
                        self._subscribers[channel].remove(weak_cb)
                        removed = True
                        break

                if removed:
                    self.logger.info(
                        f"取消订阅: {callback.__name__} -> {channel.value}"
                    )
                else:
                    self.logger.warning(
                        f"未找到订阅: {callback.__name__} -> {channel.value}"
                    )

                return removed

        except Exception as e:
            self.logger.error(f"取消订阅失败: {e}")
            return False

    def publish(
        self,
        channel: DataChannel,
        source: str,
        data: Any,
        device_id: Optional[str] = None,
    ) -> bool:
        """发布消息到频道"""
        try:
            # 创建消息
            message = DataMessage(
                channel=channel, source=source, data=data, device_id=device_id
            )

            with self._lock:
                # 🔥 获取活跃订阅者并自动清理失效的
                live_callbacks = self._get_live_callbacks(channel)

                if not live_callbacks:
                    self.logger.debug(f"频道 {channel.value} 没有订阅者")
                    return True

                # 根据频道选择投递方式
                if channel in self._delivery_config["sync_channels"]:
                    self._deliver_sync(live_callbacks, message)
                    delivery_mode = "同步"
                else:
                    self._deliver_async(live_callbacks, message)
                    delivery_mode = "异步"

                # 更新统计
                self._stats["published"] += 1
                self._stats["delivered"] += len(live_callbacks)

                # 发送信号
                self.message_published.emit(channel.value, source)
                self.message_delivered.emit(channel.value, len(live_callbacks))

                self.logger.debug(
                    f"消息已发布: {channel.value} -> {len(live_callbacks)}个订阅者"
                )
                return True

        except Exception as e:
            self.logger.error(f"发布消息失败: {channel.value} -> {e}")
            self._stats["errors"] += 1
            return False

    def _get_live_callbacks(self, channel: DataChannel) -> List[Callable]:
        """获取活跃的回调函数并清理失效的弱引用"""
        live_callbacks = []
        dead_refs = []

        for weak_cb in self._subscribers[channel]:
            # 尝试获取实际的回调函数
            if isinstance(weak_cb, WeakMethod):
                callback = weak_cb()
            elif isinstance(weak_cb, ref):
                callback = weak_cb()
            else:
                callback = None

            if callback is not None:
                live_callbacks.append(callback)
            else:
                # 记录需要清理的失效引用
                dead_refs.append(weak_cb)

        # 🔥 自动清理失效的弱引用
        if dead_refs:
            for dead_ref in dead_refs:
                self._subscribers[channel].remove(dead_ref)
            self._stats["auto_cleaned"] += len(dead_refs)
            self.logger.debug(f"自动清理了 {len(dead_refs)} 个失效订阅者")

        return live_callbacks

    def _deliver_sync(self, callbacks: List[Callable], message: DataMessage):
        """同步投递 - 立即执行"""
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                self.logger.error(f"同步回调失败: {callback.__name__} -> {e}")
                self._stats["errors"] += 1

    def _deliver_async(self, callbacks: List[Callable], message: DataMessage):
        """异步投递 - 使用QTimer延迟执行"""
        for callback in callbacks:
            # 🔥 使用QTimer.singleShot实现异步投递
            QTimer.singleShot(
                0, lambda cb=callback, msg=message: self._safe_async_call(cb, msg)
            )

    def _safe_async_call(self, callback: Callable, message: DataMessage):
        """安全的异步回调执行"""
        try:
            callback(message)
        except Exception as e:
            self.logger.error(f"异步回调失败: {callback.__name__} -> {e}")
            self._stats["errors"] += 1

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            # 计算活跃订阅者总数
            total_active = 0
            for channel in self._subscribers:
                total_active += len(self._get_live_callbacks(channel))

            return {
                **self._stats,
                "active_channels": len(
                    [ch for ch in self._subscribers if self._subscribers[ch]]
                ),
                "active_subscribers": total_active,
                "timestamp": time.time(),
            }

    def force_cleanup(self) -> int:
        """强制清理所有失效的弱引用"""
        cleaned_count = 0
        with self._lock:
            for channel in list(self._subscribers.keys()):
                self._get_live_callbacks(channel)  # 这会触发自动清理
            cleaned_count = self._stats["auto_cleaned"]

        if cleaned_count > 0:
            self.logger.info(f"强制清理完成，移除了 {cleaned_count} 个失效订阅者")

        return cleaned_count


# 全局数据总线实例
data_bus = DataBus()
