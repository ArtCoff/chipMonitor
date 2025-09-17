# core/database_manager.py
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from config.database_config import database_config, DatabaseConfig, DatabaseStats
from .thread_pool import thread_pool, TaskType, TaskPriority


class DatabaseManager(QObject):
    """简化的数据库管理器 - 确保组件协调"""

    # 🔥 信号定义 - 与控制面板匹配
    connection_changed = Signal(bool, str)  # 连接状态变化 (匹配控制面板)
    stats_updated = Signal(object)  # 统计信息更新 (DatabaseStats对象)
    migration_completed = Signal(dict)  # 迁移完成
    migration_failed = Signal(str)  # 迁移失败

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("DatabaseManager")

        # 🔥 连接池和状态
        self._connection_pool: Optional[ThreadedConnectionPool] = None
        self._connected = False
        self._lock = threading.RLock()

        # 🔥 统计信息缓存
        self._cached_stats = DatabaseStats()
        self._last_stats_update = 0

        # 🔥 迁移控制
        self._migration_running = False

        # 🔥 设置定时器
        self._setup_timers()

    def _setup_timers(self):
        """设置定时器"""
        # 统计更新定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats_async)
        self.stats_timer.start(30000)  # 30秒更新统计

        # 连接健康检查定时器
        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._health_check)
        self.health_timer.start(60000)  # 1分钟检查连接

        # 数据迁移定时器 (如果需要)
        self.migration_timer = QTimer()
        self.migration_timer.timeout.connect(self._scheduled_migration)
        # 默认不启动，可通过配置启用

    def test_connection(
        self, config: Optional[DatabaseConfig] = None
    ) -> Tuple[bool, str]:
        """测试数据库连接 - 与控制面板接口匹配"""
        test_config = config or database_config

        try:
            self.logger.info(f"测试数据库连接: {test_config.host}:{test_config.port}")

            # 创建测试连接
            test_conn = psycopg2.connect(**test_config.get_connection_params())

            # 测试查询
            with test_conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]

            test_conn.close()

            # 提取版本号
            version_info = version.split()[0] + " " + version.split()[1]
            success_msg = f"连接成功: {version_info}"
            self.logger.info(success_msg)
            return True, success_msg

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def connect(self, config: Optional[DatabaseConfig] = None) -> bool:
        """连接数据库 - 与控制面板接口匹配"""
        with self._lock:
            try:
                connect_config = config or database_config

                # 关闭现有连接
                self.disconnect()

                # 🔥 创建连接池
                self._connection_pool = ThreadedConnectionPool(
                    minconn=connect_config.min_connections,
                    maxconn=connect_config.max_connections,
                    **connect_config.get_connection_params(),
                )

                # 🔥 测试连接并初始化表结构
                conn = self._connection_pool.getconn()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1;")
                        cursor.fetchone()

                    # 初始化表结构
                    self._init_tables(conn)

                finally:
                    self._connection_pool.putconn(conn)

                self._connected = True
                self.connection_changed.emit(True, "数据库连接成功")

                self.logger.info("✅ 数据库连接成功")
                return True

            except Exception as e:
                self._connected = False
                error_msg = f"数据库连接失败: {e}"
                self.connection_changed.emit(False, error_msg)
                self.logger.error(error_msg)
                return False

    def disconnect(self):
        """断开数据库连接 - 与控制面板接口匹配"""
        with self._lock:
            try:
                if self._connection_pool:
                    self._connection_pool.closeall()
                    self._connection_pool = None

                self._connected = False
                self.connection_changed.emit(False, "数据库连接已断开")
                self.logger.info("数据库连接已断开")

            except Exception as e:
                self.logger.error(f"断开数据库连接失败: {e}")

    def _init_tables(self, conn):
        """初始化数据库表结构 - 简化版本"""
        try:
            with conn.cursor() as cursor:
                # 🔥 遥测数据表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_data (
                        id BIGSERIAL PRIMARY KEY,
                        device_id VARCHAR(100) NOT NULL,
                        channel VARCHAR(50) NOT NULL,
                        source VARCHAR(100) NOT NULL,
                        temperature DECIMAL(10,3),
                        pressure DECIMAL(10,3),
                        rf_power DECIMAL(10,3),
                        endpoint DECIMAL(10,3),
                        humidity DECIMAL(10,3),
                        vibration DECIMAL(10,3),
                        data_timestamp TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_telemetry_device_time 
                    ON telemetry_data(device_id, data_timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_telemetry_created 
                    ON telemetry_data(created_at DESC);
                """
                )

                # 🔥 告警数据表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        device_id VARCHAR(100),
                        alert_type VARCHAR(100) NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        message TEXT NOT NULL,
                        alert_data JSONB,
                        data_timestamp TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        resolved_at TIMESTAMPTZ
                    );
                    CREATE INDEX IF NOT EXISTS idx_alerts_device_time 
                    ON alerts(device_id, data_timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_alerts_unresolved 
                    ON alerts(resolved_at) WHERE resolved_at IS NULL;
                """
                )

                # 🔥 设备事件表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_events (
                        id BIGSERIAL PRIMARY KEY,
                        device_id VARCHAR(100) NOT NULL,
                        event_type VARCHAR(100) NOT NULL,
                        event_data JSONB,
                        severity VARCHAR(20) DEFAULT 'info',
                        data_timestamp TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_events_device_time 
                    ON device_events(device_id, data_timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_events_type 
                    ON device_events(event_type);
                """
                )

                conn.commit()
                self.logger.info("✅ 数据库表结构初始化完成")

        except Exception as e:
            conn.rollback()
            self.logger.error(f"初始化数据库表失败: {e}")
            raise

    def get_stats(self) -> DatabaseStats:
        """获取数据库统计信息 - 与控制面板接口匹配"""
        # 🔥 使用缓存避免频繁查询
        current_time = time.time()
        if current_time - self._last_stats_update < 10:  # 10秒缓存
            return self._cached_stats

        stats = DatabaseStats()
        stats.connected = self._connected
        stats.last_check_time = current_time

        if not self._connected or not self._connection_pool:
            self._cached_stats = stats
            return stats

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # 获取各表记录数
                    cursor.execute("SELECT COUNT(*) as count FROM telemetry_data")
                    stats.telemetry_count = cursor.fetchone()["count"]

                    cursor.execute("SELECT COUNT(*) as count FROM alerts")
                    stats.alerts_count = cursor.fetchone()["count"]

                    cursor.execute("SELECT COUNT(*) as count FROM device_events")
                    stats.events_count = cursor.fetchone()["count"]

                    stats.total_records = (
                        stats.telemetry_count + stats.alerts_count + stats.events_count
                    )

                    # 获取数据库大小
                    cursor.execute(
                        "SELECT pg_database_size(current_database()) as size_bytes"
                    )
                    size_bytes = cursor.fetchone()["size_bytes"]
                    stats.database_size_mb = size_bytes / 1024 / 1024

            finally:
                self._connection_pool.putconn(conn)

            self._cached_stats = stats
            self._last_stats_update = current_time

        except Exception as e:
            self.logger.error(f"获取数据库统计失败: {e}")

        return stats

    @Slot()
    def _update_stats_async(self):
        """异步更新统计信息"""
        if not self._connected:
            return

        try:
            # 🔥 使用线程池异步获取统计
            task_id = thread_pool.submit(
                task_type=TaskType.DATA_PROCESSING,
                func=self._get_stats_worker,
                task_id=f"stats_{int(time.time())}",
                priority=TaskPriority.LOW,
                timeout=30.0,
            )

        except Exception as e:
            self.logger.error(f"提交统计任务失败: {e}")

    def _get_stats_worker(self) -> dict:
        """获取统计信息的工作函数"""
        try:
            stats = self.get_stats()

            # 🔥 发射信号到主线程
            self.stats_updated.emit(stats)

            return {
                "success": True,
                "total_records": stats.total_records,
                "database_size_mb": stats.database_size_mb,
            }

        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {"success": False, "error": str(e)}

    @Slot()
    def _health_check(self):
        """数据库连接健康检查"""
        if not self._connection_pool:
            return

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                    cursor.fetchone()

                # 连接正常，如果之前断开则发送恢复信号
                if not self._connected:
                    self._connected = True
                    self.connection_changed.emit(True, "数据库连接恢复")

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            # 连接异常，如果之前正常则发送断开信号
            if self._connected:
                self._connected = False
                error_msg = f"数据库连接检查失败: {e}"
                self.connection_changed.emit(False, error_msg)
                self.logger.error(error_msg)

    @Slot()
    def _scheduled_migration(self):
        """定时数据迁移 - 简化版本"""
        if not self._connected or self._migration_running:
            return

        try:
            # 🔥 使用线程池异步执行迁移
            task_id = thread_pool.submit(
                task_type=TaskType.BATCH_PROCESSING,
                func=self._migration_worker,
                task_id=f"migration_{int(time.time())}",
                priority=TaskPriority.LOW,
                timeout=300.0,
            )

            if task_id:
                self._migration_running = True
                self.logger.debug(f"数据迁移任务已提交: {task_id}")

        except Exception as e:
            self.logger.error(f"提交数据迁移任务失败: {e}")

    def _migration_worker(self) -> dict:
        """数据迁移工作函数 - 从Redis迁移到PostgreSQL"""
        start_time = time.time()
        result = {
            "total_processed": 0,
            "total_success": 0,
            "total_failed": 0,
            "execution_time": 0,
            "errors": [],
        }

        try:
            # 🔥 这里可以添加从Redis获取数据并迁移到PostgreSQL的逻辑
            # 由于redis_buffer可能不存在，先跳过具体实现

            # 示例代码结构：
            # if hasattr(self, 'redis_buffer'):
            #     messages = self.redis_buffer.get_pending_messages()
            #     result = self._process_migration_messages(messages)

            result["execution_time"] = (time.time() - start_time) * 1000

            if result["total_processed"] > 0:
                self.logger.info(
                    f"数据迁移完成: {result['total_success']}/{result['total_processed']} 条"
                )
                self.migration_completed.emit(result)

            return result

        except Exception as e:
            error_msg = f"数据迁移失败: {e}"
            result["errors"].append(error_msg)
            self.logger.error(error_msg)
            self.migration_failed.emit(error_msg)
            return result

        finally:
            self._migration_running = False

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    def execute_query(
        self, query: str, params: tuple = None, fetch_all: bool = True
    ) -> List[Dict]:
        """执行查询 - 提供给其他组件使用"""
        if not self._connected or not self._connection_pool:
            raise Exception("数据库未连接")

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)

                    if fetch_all:
                        return [dict(row) for row in cursor.fetchall()]
                    else:
                        result = cursor.fetchone()
                        return [dict(result)] if result else []

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            self.logger.error(f"执行查询失败: {e}")
            raise

    def execute_insert(self, table: str, data: Dict[str, Any]) -> bool:
        """执行插入操作"""
        if not self._connected or not self._connection_pool:
            return False

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    columns = list(data.keys())
                    values = list(data.values())
                    placeholders = ", ".join(["%s"] * len(values))

                    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                    cursor.execute(query, values)

                conn.commit()
                return True

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            self.logger.error(f"插入数据失败: {e}")
            return False

    def manual_migration(self) -> dict:
        """手动触发数据迁移"""
        if self._migration_running:
            return {"error": "迁移任务正在运行中"}

        try:
            task_id = thread_pool.submit(
                task_type=TaskType.BATCH_PROCESSING,
                func=self._migration_worker,
                task_id=f"manual_migration_{int(time.time())}",
                priority=TaskPriority.NORMAL,
                timeout=300.0,
            )

            if task_id:
                return {"success": True, "task_id": task_id}
            else:
                return {"error": "任务提交失败"}

        except Exception as e:
            return {"error": str(e)}

    def enable_migration(self, interval_seconds: int = 300):
        """启用定时迁移"""
        try:
            if not self.migration_timer.isActive():
                self.migration_timer.start(interval_seconds * 1000)
                self.logger.info(f"数据迁移已启用，间隔: {interval_seconds}秒")
                return True
        except Exception as e:
            self.logger.error(f"启用数据迁移失败: {e}")
            return False

    def disable_migration(self):
        """禁用定时迁移"""
        try:
            if self.migration_timer.isActive():
                self.migration_timer.stop()
                self.logger.info("数据迁移已禁用")
                return True
        except Exception as e:
            self.logger.error(f"禁用数据迁移失败: {e}")
            return False

    def shutdown(self):
        """关闭数据库管理器"""
        try:
            self.logger.info("正在关闭数据库管理器...")

            # 停止定时器
            self.stats_timer.stop()
            self.health_timer.stop()
            self.migration_timer.stop()

            # 等待迁移任务完成
            if self._migration_running:
                self.logger.info("等待数据迁移任务完成...")
                time.sleep(2)

            # 断开数据库连接
            self.disconnect()

            self.logger.info("数据库管理器已关闭")

        except Exception as e:
            self.logger.error(f"关闭数据库管理器时发生错误: {e}")


# 全局数据库管理器实例
db_manager = DatabaseManager()
