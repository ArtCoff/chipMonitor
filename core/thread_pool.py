from typing import Callable, Any, Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from enum import Enum
from queue import PriorityQueue
import threading
import time
import logging
from PySide6.QtCore import QObject, Signal, QTimer, Qt


class TaskType(Enum):
    """任务类型"""

    DATA_PROCESSING = "data"
    EVENT_HANDLING = "event"
    MQTT_PROCESSING = "mqtt"
    BATCH_PROCESSING = "batch"
    HISTORY_DATA_QUERY = "history_data"
    ANALYTICS = "analytics"


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    REALTIME = 5


@dataclass
class Task:
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    func: Callable
    args: tuple = ()
    kwargs: dict = None
    # callback: Optional[Callable] = None
    timeout: Optional[float] = None
    created_time: float = None
    max_retries: int = 0
    retry_count: int = 0

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}
        if self.created_time is None:
            self.created_time = time.time()

    def __lt__(self, other):
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.created_time < other.created_time


class ThreadPool(QObject):
    """线程池，支持优先级、重试、超时、指标监控、任务取消"""

    task_completed = Signal(str, dict)
    task_failed = Signal(str, dict)
    task_started = Signal(str, str)
    task_retried = Signal(str, int)
    pool_stats_updated = Signal(dict)

    def __init__(self, max_workers: int = None, parent: Optional[QObject] = None):
        super().__init__()

        if max_workers is None:
            import os

            max_workers = min(32, (os.cpu_count() or 1) + 4)

        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="ChipM"
        )

        # 任务管理
        self.active_tasks: Dict[str, Future] = {}
        self.task_type_map: Dict[str, TaskType] = {}
        self.completed_tasks: List[str] = []
        self.failed_tasks: List[str] = []

        # 统计数据
        self.stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "queue_size": 0,
            "active_workers": 0,
            "avg_execution_time": 0,
            "max_execution_time": 0,
            "min_execution_time": float("inf"),
            "total_execution_time": 0,
            "tasks_by_type": {
                t.value: {
                    "submitted": 0,
                    "completed": 0,
                    "failed": 0,
                    "avg_time": 0,
                    "total_time": 0,
                }
                for t in TaskType
            },
            "tasks_by_priority": {
                p.value: {"submitted": 0, "completed": 0, "failed": 0}
                for p in TaskPriority
            },
        }

        self.stats_lock = threading.Lock()
        self.worker_lock = threading.Lock()
        self.active_worker_count = 0

        # 定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._emit_stats)
        self.stats_timer.start(5000)  # 5秒更新一次统计

        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_completed_tasks)
        self.cleanup_timer.start(30000)  # 30秒清理一次历史记录

        logging.info(f"线程池初始化完成，最大线程数: {max_workers}")

    def submit(
        self,
        task_type: TaskType,
        func: Callable,
        *args,
        task_id: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        # callback: Optional[Callable] = None,
        timeout: Optional[float] = None,
        max_retries: int = 0,
        **kwargs,
    ) -> str:
        """提交任务"""
        try:
            if task_id is None:
                task_id = f"{task_type.value}_{int(time.time() * 1000000)}"

            task = Task(
                task_id=task_id,
                task_type=task_type,
                priority=priority,
                func=func,
                args=args,
                kwargs=kwargs,
                # callback=callback,
                timeout=timeout,
                max_retries=max_retries,
            )

            # 更新统计
            with self.stats_lock:
                self.stats["total_submitted"] += 1
                self.stats["tasks_by_type"][task_type.value]["submitted"] += 1
                self.stats["tasks_by_priority"][priority.value]["submitted"] += 1

            # 提交执行
            future = self.executor.submit(self._execute_task, task)
            self.active_tasks[task_id] = future
            self.task_type_map[task_id] = task_type

            # 通知开始
            # self.task_started.emit(task_id, task_type.value)

            logging.debug(
                f"任务提交: {task_id} ({task_type.value}, 优先级: {priority.value})"
            )
            return task_id

        except Exception as e:
            error_msg = f"任务提交失败: {e}"
            logging.error(error_msg)
            self.task_failed.emit(task_id or "unknown", error_msg)
            return ""

    def _execute_task(self, task: Task):
        """执行任务（在子线程中运行）"""
        start_time = time.time()

        # 增加活跃线程计数
        with self.worker_lock:
            self.active_worker_count += 1

        try:
            # 执行用户函数
            result = task.func(*task.args, **task.kwargs)
            execution_time = time.time() - start_time
            if task.task_type == TaskType.MQTT_PROCESSING:
                logging.debug(f"线程池解析完成(device_id:{result.get("device_id")})")
            self._update_success_stats(task, execution_time)
            # 不使用Qtimer执行回调，直接使用信号槽机制
            # 安全执行回调（在主线程）
            # if task.callback:
            #     try:
            #         QTimer.singleShot(0, lambda: task.callback(result))
            #     except Exception as e:
            #         logging.error(f"回调执行失败 {task.task_id}: {e}")
            #

            self.task_completed.emit(
                task.task_id,
                {
                    "success": True,
                    "data": result,
                    "task_type": task.task_type.value,
                    "execution_time": execution_time,
                },
            )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = {
                "success": False,
                "error": str(e),
                "message": f"任务执行失败: {e}",
                "task_type": task.task_type.value,
                "execution_time": execution_time,
            }
            self.task_failed.emit(task.task_id, error_msg)

        finally:
            # 清理资源
            self._cleanup_task_resources(task.task_id)
            with self.worker_lock:
                self.active_worker_count -= 1

    def _update_success_stats(self, task: Task, execution_time: float):
        """更新成功任务统计"""
        with self.stats_lock:
            self.stats["total_completed"] += 1
            self.stats["tasks_by_type"][task.task_type.value]["completed"] += 1
            self.stats["tasks_by_priority"][task.priority.value]["completed"] += 1

            # 更新时间指标
            self._update_time_stats(execution_time, task.task_type)

    def _update_failure_stats(self, task: Task):
        """更新失败任务统计"""
        with self.stats_lock:
            self.stats["total_failed"] += 1
            self.stats["tasks_by_type"][task.task_type.value]["failed"] += 1
            self.stats["tasks_by_priority"][task.priority.value]["failed"] += 1

    def _update_time_stats(self, execution_time: float, task_type: TaskType):
        """更新执行时间相关统计"""
        self.stats["total_execution_time"] += execution_time
        self.stats["max_execution_time"] = max(
            self.stats["max_execution_time"], execution_time
        )
        self.stats["min_execution_time"] = min(
            self.stats["min_execution_time"], execution_time
        )

        if self.stats["total_completed"] > 0:
            self.stats["avg_execution_time"] = (
                self.stats["total_execution_time"] / self.stats["total_completed"]
            )

        type_stats = self.stats["tasks_by_type"][task_type.value]
        type_stats["total_time"] += execution_time
        if type_stats["completed"] > 0:
            type_stats["avg_time"] = type_stats["total_time"] / type_stats["completed"]

    def _cleanup_task_resources(self, task_id: str):
        """清理任务相关资源"""
        self.active_tasks.pop(task_id, None)
        self.task_type_map.pop(task_id, None)
        if len(self.completed_tasks) < 10000:  # 避免无限增长
            self.completed_tasks.append(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """取消单个任务"""
        if task_id not in self.active_tasks:
            logging.warning(f"任务不存在或已完成: {task_id}")
            return False

        future = self.active_tasks[task_id]
        if future.cancel():
            self._cleanup_task_resources(task_id)
            logging.info(f"任务已取消: {task_id}")
            return True
        else:
            logging.warning(f"任务无法取消（可能已在执行）: {task_id}")
            return False

    def cancel_all_tasks_by_type(self, task_type: TaskType) -> int:
        """取消指定类型的所有活跃任务"""
        cancelled = 0
        try:
            # 使用 task_type_map 精准匹配
            for task_id in list(self.task_type_map.keys()):
                if (
                    self.task_type_map.get(task_id) == task_type
                    and task_id in self.active_tasks
                ):
                    if self.cancel_task(task_id):
                        cancelled += 1
        except Exception as e:
            logging.error(f"批量取消失败: {e}")
        return cancelled

    def get_active_workers(self) -> int:
        """获取活跃工作线程数（高效）"""
        with self.worker_lock:
            return self.active_worker_count

    def get_queue_size(self) -> int:
        """获取活跃任务数"""
        return len(self.active_tasks)

    def get_metrics(self) -> Dict[str, Any]:
        """获取当前指标快照"""
        with self.stats_lock:
            current = self.stats.copy()

        current.update(
            {
                "queue_size": self.get_queue_size(),
                "active_workers": self.get_active_workers(),
                "max_workers": self.max_workers,
                "completed_tasks_count": len(self.completed_tasks),
                "failed_tasks_count": len(self.failed_tasks),
            }
        )
        return current

    def _emit_stats(self):
        """定时发射统计信号"""
        try:
            self.pool_stats_updated.emit(self.get_metrics())
        except Exception as e:
            logging.error(f"发射统计失败: {e}")

    def _cleanup_completed_tasks(self):
        """定期清理历史记录"""
        try:
            if len(self.completed_tasks) > 1000:
                self.completed_tasks = self.completed_tasks[-1000:]
            if len(self.failed_tasks) > 1000:
                self.failed_tasks = self.failed_tasks[-1000:]
            logging.debug(
                f"清理完成: 保留 {len(self.completed_tasks)} 成功, {len(self.failed_tasks)} 失败记录"
            )
        except Exception as e:
            logging.error(f"清理历史记录失败: {e}")

    def shutdown(
        self, wait: bool = True, cancel_active: bool = False, timeout: float = 30.0
    ):
        """关闭线程池"""
        try:
            logging.info("正在关闭线程池...")
            self.stats_timer.stop()
            self.cleanup_timer.stop()

            if cancel_active:
                for tid in list(self.active_tasks.keys()):
                    self.cancel_task(tid)

            self.executor.shutdown(wait=wait, timeout=timeout)
            self.active_tasks.clear()
            self.task_type_map.clear()

            logging.info("线程池已安全关闭")
        except Exception as e:
            logging.error(f"关闭线程池异常: {e}")


# 全局线程池实例
# thread_pool = ThreadPool()
_thread_pool = None


def get_thread_pool() -> ThreadPool:
    global _thread_pool
    if _thread_pool is None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication not created!")
        _thread_pool = ThreadPool(parent=app)
    return _thread_pool
