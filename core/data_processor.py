"""
高性能数据处理器
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
from datetime import datetime
from PySide6.QtCore import QObject, Signal

from .event_bus import event_bus, EventType, EventPriority
from .thread_pool import thread_pool, TaskType, TaskPriority


class HighPerformanceProcessor(QObject):
    data_processed = Signal(str, dict)  # device_id, processed_data
    batch_completed = Signal(int)  # batch_size
    error_occurred = Signal(str, str)  # device_id, error

    def __init__(self):
        super().__init__()

        # 数据缓冲区
        self.device_buffers = defaultdict(lambda: deque(maxlen=1000))
        self.batch_buffer = deque(maxlen=10000)

        # 处理统计
        self.stats = {
            "total_processed": 0,
            "processing_rate": 0,
            "error_count": 0,
            "device_counts": defaultdict(int),
        }

        # 连接事件总线
        event_bus.subscribe(
            EventType.MQTT_MESSAGE_RECEIVED,
            self.handle_mqtt_message,
            priority=EventPriority.HIGH,
        )

        self.running = False
        logging.info("高性能数据处理器已初始化")

    def start_processing(self):
        """启动处理"""
        self.running = True

        # 启动批处理任务
        thread_pool.submit(
            TaskType.DATA_PROCESSING, self._batch_processor, priority=TaskPriority.HIGH
        )

        logging.info("数据处理器已启动")

    def handle_mqtt_message(self, event):
        """处理MQTT消息事件"""
        try:
            data = event.data
            device_id = data.get("device_id")
            payload = data.get("payload", "{}")

            if not device_id:
                return

            # 异步处理单条消息
            thread_pool.submit(
                TaskType.DATA_PROCESSING,
                self._process_single_message,
                device_id,
                payload,
                priority=TaskPriority.NORMAL,
                callback=lambda result: self._on_message_processed(device_id, result),
            )

        except Exception as e:
            logging.error(f"处理MQTT消息失败: {e}")

    def _process_single_message(self, device_id: str, payload: str) -> Dict[str, Any]:
        """处理单条消息"""
        try:
            # 解析JSON
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload

            # 数据验证和清洗
            processed_data = self._validate_and_clean_data(data)

            # 添加元数据
            processed_data.update(
                {
                    "device_id": device_id,
                    "processed_timestamp": datetime.now().isoformat(),
                    "processor_version": "1.0",
                }
            )

            return processed_data

        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {e}")
        except Exception as e:
            raise RuntimeError(f"数据处理失败: {e}")

    def _validate_and_clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """数据验证和清洗"""
        cleaned_data = {}

        for key, value in data.items():
            # 基本类型验证
            if isinstance(value, (str, int, float, bool)):
                cleaned_data[key] = value
            elif isinstance(value, dict):
                cleaned_data[key] = self._validate_and_clean_data(value)
            elif isinstance(value, list):
                cleaned_data[key] = [
                    item for item in value if isinstance(item, (str, int, float, bool))
                ]

        return cleaned_data

    def _on_message_processed(self, device_id: str, result: Dict[str, Any]):
        """消息处理完成回调"""
        try:
            # 更新统计
            self.stats["total_processed"] += 1
            self.stats["device_counts"][device_id] += 1

            # 添加到设备缓冲区
            self.device_buffers[device_id].append(result)

            # 添加到批处理缓冲区
            self.batch_buffer.append(result)

            # 发送处理完成信号
            self.data_processed.emit(device_id, result)

            # 发布事件
            event_bus.publish(
                EventType.DATA_PROCESSED,
                source="HighPerformanceProcessor",
                data={
                    "device_id": device_id,
                    "data": result,
                    "processing_time": time.time(),
                },
            )

        except Exception as e:
            logging.error(f"处理完成回调失败: {e}")
            self.error_occurred.emit(device_id, str(e))

    def _batch_processor(self):
        """批处理器"""
        batch_size = 100
        batch_timeout = 5.0  # 5秒超时

        while self.running:
            try:
                start_time = time.time()
                batch_data = []

                # 收集批处理数据
                while (
                    len(batch_data) < batch_size
                    and (time.time() - start_time) < batch_timeout
                ):
                    try:
                        if self.batch_buffer:
                            batch_data.append(self.batch_buffer.popleft())
                        else:
                            time.sleep(0.1)
                    except IndexError:
                        break

                if batch_data:
                    self._process_batch(batch_data)
                    self.batch_completed.emit(len(batch_data))

            except Exception as e:
                logging.error(f"批处理失败: {e}")
                time.sleep(1)

    def _process_batch(self, batch_data: List[Dict[str, Any]]):
        """处理批数据"""
        try:
            # 发布批处理完成事件
            event_bus.publish(
                EventType.DATA_BATCH_COMPLETED,
                source="HighPerformanceProcessor",
                data={
                    "batch_size": len(batch_data),
                    "processing_timestamp": datetime.now().isoformat(),
                    "device_summary": self._generate_device_summary(batch_data),
                },
            )

        except Exception as e:
            logging.error(f"批处理失败: {e}")

    def _generate_device_summary(
        self, batch_data: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """生成设备汇总"""
        summary = defaultdict(int)
        for data in batch_data:
            device_id = data.get("device_id", "unknown")
            summary[device_id] += 1
        return dict(summary)

    def get_device_data(self, device_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取设备数据"""
        if device_id in self.device_buffers:
            buffer = self.device_buffers[device_id]
            return list(buffer)[-limit:]
        return []

    def get_statistics(self) -> Dict[str, Any]:
        """获取处理统计"""
        return {
            **self.stats,
            "buffer_sizes": {
                device_id: len(buffer)
                for device_id, buffer in self.device_buffers.items()
            },
            "batch_buffer_size": len(self.batch_buffer),
        }


# 全局数据处理器
data_processor = HighPerformanceProcessor()
