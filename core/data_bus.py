import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Any, Union
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
from PySide6.QtCore import QObject, Signal, QTimer
from weakref import WeakMethod, ref


class DataChannel(Enum):
    """数据频道枚举"""

    TELEMETRY_DATA = "telemetry_data"
    ALERTS = "alerts"
    ERRORS = "errors"
    DEVICE_EVENTS = "device_events"


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
    """统一数据总线 - 仅负责消息分发"""

    # 系统信号
    message_published = Signal(str, str)  # (channel, source)
    message_delivered = Signal(str, int)  # (channel, subscriber_count)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("DataBus")

        # 🔥 使用弱引用存储订阅者
        self._subscribers: Dict[DataChannel, List[Union[WeakMethod, ref]]] = (
            defaultdict(list)
        )
        self._lock = threading.RLock()

        # 🔥 简化配置 - 所有消息都同步投递
        self._stats = {"published": 0, "delivered": 0, "errors": 0, "auto_cleaned": 0}

        self.logger.info("DataBus已初始化")

    def subscribe(
        self, channel: DataChannel, callback: Callable[[DataMessage], None]
    ) -> bool:
        """订阅频道"""
        try:
            with self._lock:
                # 使用弱引用
                if hasattr(callback, "__self__"):
                    weak_cb = WeakMethod(callback)
                else:
                    weak_cb = ref(callback)

                # 检查重复订阅
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
                removed = False
                for weak_cb in self._subscribers[channel][:]:
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
        """发布消息 - 纯消息分发，不处理持久化"""
        try:
            message = DataMessage(
                channel=channel, source=source, data=data, device_id=device_id
            )

            with self._lock:
                # 获取活跃订阅者
                live_callbacks = self._get_live_callbacks(channel)

                if not live_callbacks:
                    self.logger.debug(f"频道 {channel.value} 没有订阅者")
                    return True

                # 同步投递所有消息
                self._deliver_sync(live_callbacks, message)

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
        """获取活跃回调并清理失效引用"""
        live_callbacks = []
        dead_refs = []

        for weak_cb in self._subscribers[channel]:
            if isinstance(weak_cb, WeakMethod):
                callback = weak_cb()
            elif isinstance(weak_cb, ref):
                callback = weak_cb()
            else:
                callback = None

            if callback is not None:
                live_callbacks.append(callback)
            else:
                dead_refs.append(weak_cb)

        # 清理失效引用
        if dead_refs:
            for dead_ref in dead_refs:
                self._subscribers[channel].remove(dead_ref)
            self._stats["auto_cleaned"] += len(dead_refs)
            self.logger.debug(f"自动清理了 {len(dead_refs)} 个失效订阅者")

        return live_callbacks

    def _deliver_sync(self, callbacks: List[Callable], message: DataMessage):
        """同步投递"""
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                self.logger.error(f"回调失败: {callback.__name__} -> {e}")
                self._stats["errors"] += 1

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
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
        """强制清理失效引用"""
        cleaned_count = 0
        with self._lock:
            for channel in list(self._subscribers.keys()):
                self._get_live_callbacks(channel)
            cleaned_count = self._stats["auto_cleaned"]

        if cleaned_count > 0:
            self.logger.info(f"强制清理完成，移除了 {cleaned_count} 个失效订阅者")

        return cleaned_count


# 全局数据总线实例
data_bus = DataBus()
