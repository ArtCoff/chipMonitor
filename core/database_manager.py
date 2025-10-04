import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, execute_values
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from config.database_config import database_config, DatabaseConfig, DatabaseStats
from .thread_pool import thread_pool, TaskType, TaskPriority


class DatabaseManager(QObject):
    """数据库管理器"""

    # 信号定义
    connection_changed = Signal(bool, str)
    stats_updated = Signal(object)
    batch_completed = Signal(str, dict)
    batch_failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("DatabaseManager")

        # 连接池和状态
        self._connection_pool: Optional[ThreadedConnectionPool] = None
        self._connected = False
        self._lock = threading.RLock()

        # 统计信息缓存
        self._cached_stats = DatabaseStats()
        self._last_stats_update = 0

        # 批量操作统计
        self.batch_stats = {
            "telemetry_batches": 0,
            "alerts_batches": 0,
            "events_batches": 0,
            "errors_batches": 0,
            "total_records": 0,
            "failed_batches": 0,
        }

        # 设置定时器
        self._setup_timers()

    def _setup_timers(self):
        """设置定时器"""
        # 统计更新定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats_async)
        self.stats_timer.start(30000)  # 30秒

        # 连接健康检查定时器
        self.health_timer = QTimer()
        self.health_timer.timeout.connect(self._health_check)
        self.health_timer.start(60000)  # 1分钟

    def test_connection(
        self, config: Optional[DatabaseConfig] = None
    ) -> Tuple[bool, str]:
        """测试数据库连接"""
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

            version_info = version.split()[0] + " " + version.split()[1]
            success_msg = f"连接成功: {version_info}"
            self.logger.info(success_msg)
            return True, success_msg

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    def connect(self, config: Optional[DatabaseConfig] = None) -> bool:
        """连接数据库"""
        with self._lock:
            try:
                connect_config = config or database_config

                # 关闭现有连接
                self.disconnect()

                # 创建连接池
                self._connection_pool = ThreadedConnectionPool(
                    minconn=connect_config.min_connections,
                    maxconn=connect_config.max_connections,
                    **connect_config.get_connection_params(),
                )

                # 测试连接并初始化表结构
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
        """断开数据库连接"""
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
        """初始化数据库表结构"""
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                CREATE TABLE IF NOT EXISTS telemetry_data (
                    id BIGSERIAL PRIMARY KEY,
                    device_id VARCHAR(100) NOT NULL,        -- 设备ID
                    device_type VARCHAR(100) NOT NULL,      -- 设备类型
                    channel INTEGER NOT NULL,               -- 通道
                    recipe VARCHAR(100),                    -- 工艺配方
                    step VARCHAR(100),                      -- 工艺步骤
                    lot_number VARCHAR(100),                -- 批次号
                    wafer_id VARCHAR(50),                   -- 晶圆号
                    pressure DECIMAL(10,3),                 -- 压力
                    temperature DECIMAL(10,3),              -- 温度
                    rf_power DECIMAL(10,3),                 -- RF功率
                    endpoint DECIMAL(10,4),                 -- 终点检测信号
                    gas JSONB,                              -- 气体流量
                    timestamp_us BIGINT NOT NULL,           -- 原始微秒时间戳
                    data_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- 解析后的时间
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry_data(device_id, timestamp_us DESC);
                CREATE INDEX IF NOT EXISTS idx_telemetry_lot ON telemetry_data(lot_number);
                CREATE INDEX IF NOT EXISTS idx_telemetry_wafer ON telemetry_data(wafer_id);
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
                    CREATE INDEX IF NOT EXISTS idx_alerts_severity
                    ON alerts(severity);
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

                # 🔥 错误日志表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS error_logs (
                        id BIGSERIAL PRIMARY KEY,
                        device_id VARCHAR(100),
                        error_type VARCHAR(100) NOT NULL,
                        error_code VARCHAR(50),
                        message TEXT NOT NULL,
                        error_data JSONB,
                        severity VARCHAR(20) DEFAULT 'error',
                        data_timestamp TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_errors_device_time 
                    ON error_logs(device_id, data_timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_errors_type
                    ON error_logs(error_type);
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS devices (
                        device_id VARCHAR(100) PRIMARY KEY,
                        device_type VARCHAR(100),
                        vendor VARCHAR(100),
                        first_seen TIMESTAMPTZ DEFAULT NOW(),
                        last_seen TIMESTAMPTZ,
                        description TEXT
                    );
                    """
                )
                conn.commit()
                self.logger.info("数据库表结构初始化完成")

        except Exception as e:
            conn.rollback()
            self.logger.error(f"初始化数据库表失败: {e}")
            raise

    # 批量插入方法
    def batch_insert_telemetry(self, messages: List) -> dict:
        """批量插入遥测数据"""
        if not self.is_connected():
            return {"success": False, "processed": 0, "errors": ["数据库未连接"]}

        values = []
        for msg in messages:
            raw_data = getattr(msg, "data", {})
            if not isinstance(raw_data, dict):
                self.logger.warning("遥测消息 data 不是 dict")
                continue

            # 从 sample_record 提取业务字段（这是 _map_fields 的结果）
            record = raw_data.get("sample_record")
            if not isinstance(record, dict):
                self.logger.warning("遥测数据缺少 sample_record 字段")
                continue

            # === 提取字段（使用映射后的键）===
            device_id = record.get("equipment_id") or raw_data.get("device_id")
            if not device_id:
                self.logger.warning("遥测数据缺少 device_id")
                continue

            device_type = raw_data.get("device_type", "UNKNOWN")
            channel = record.get("channel")
            recipe = record.get("recipe")
            step = record.get("step")
            lot_number = record.get("lot_number")
            wafer_id = record.get("wafer_id")
            pressure = record.get("pressure")
            temperature = record.get("temperature")
            rf_power = record.get("rf_power")
            endpoint = record.get("endpoint")

            # 重建 gas 字典（从展平字段还原）
            gas = {}
            for key, value in record.items():
                if key.startswith("gas_"):
                    gas_key = key[4:]
                    gas[gas_key] = value
            gas_json = json.dumps(gas) if gas else None

            # 时间戳：优先使用设备原始微秒时间戳
            timestamp_us = record.get("device_timestamp")
            if timestamp_us is not None:
                try:
                    timestamp_us = int(timestamp_us)
                    data_timestamp = datetime.fromtimestamp(timestamp_us / 1_000_000)
                except (ValueError, OSError, OverflowError):
                    self.logger.warning(f"无效设备时间戳: {timestamp_us}")
                    timestamp_us = None
                    data_timestamp = datetime.now()
            else:
                # 回退到主机解析时间
                host_ts = raw_data.get("timestamp")  # 秒
                data_timestamp = (
                    datetime.fromtimestamp(host_ts) if host_ts else datetime.now()
                )
                timestamp_us = int(data_timestamp.timestamp() * 1_000_000)

            # === 构造插入值（顺序必须与 telemetry_data 表列一致）===
            values.append(
                (
                    device_id,
                    device_type,
                    channel,
                    recipe,
                    step,
                    lot_number,
                    wafer_id,
                    pressure,
                    temperature,
                    rf_power,
                    endpoint,
                    gas_json,
                    timestamp_us,
                    data_timestamp,
                )
            )

        if not values:
            return {"success": True, "processed": 0, "errors": []}

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO telemetry_data (
                            device_id, device_type, channel, recipe, step,
                            lot_number, wafer_id, pressure, temperature,
                            rf_power, endpoint, gas, timestamp_us, data_timestamp
                        ) VALUES %s
                    """
                    execute_values(cursor, query, values, page_size=1000)
                conn.commit()
                result = {"success": True, "processed": len(values), "errors": []}
                self.batch_stats["telemetry_batches"] += 1
                self.batch_stats["total_records"] += len(values)
                self.batch_completed.emit("telemetry", result)
                return result
            finally:
                self._connection_pool.putconn(conn)
        except Exception as e:
            error_msg = f"批量插入遥测数据失败: {e}"
            self.logger.error(error_msg)
            self.batch_stats["failed_batches"] += 1
            self.batch_failed.emit("telemetry", error_msg)
            return {"success": False, "processed": 0, "errors": [error_msg]}

    def batch_insert_alerts(self, messages: List) -> dict:
        """批量插入告警数据"""
        if not self.is_connected():
            return {"success": False, "processed": 0, "errors": ["数据库未连接"]}

        try:
            values = []
            for msg in messages:
                data = msg.data if hasattr(msg, "data") else msg
                values.append(
                    (
                        getattr(msg, "device_id", "") or "",
                        (
                            data.get("alert_type", "unknown")
                            if isinstance(data, dict)
                            else "unknown"
                        ),
                        (
                            data.get("severity", "info")
                            if isinstance(data, dict)
                            else "info"
                        ),
                        (
                            data.get("message", str(data))
                            if isinstance(data, dict)
                            else str(data)
                        ),
                        json.dumps(data) if isinstance(data, dict) else None,
                        datetime.fromtimestamp(getattr(msg, "timestamp", time.time())),
                    )
                )

            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO alerts 
                        (device_id, alert_type, severity, message, alert_data, data_timestamp)
                        VALUES %s
                    """
                    execute_values(cursor, query, values, page_size=1000)
                conn.commit()

                result = {"success": True, "processed": len(messages), "errors": []}
                self.batch_stats["alerts_batches"] += 1
                self.batch_stats["total_records"] += len(messages)

                self.batch_completed.emit("alerts", result)
                return result

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            error_msg = f"批量插入告警数据失败: {e}"
            self.logger.error(error_msg)
            self.batch_stats["failed_batches"] += 1
            self.batch_failed.emit("alerts", error_msg)
            return {"success": False, "processed": 0, "errors": [error_msg]}

    def batch_insert_events(self, messages: List) -> dict:
        """批量插入事件数据"""
        if not self.is_connected():
            return {"success": False, "processed": 0, "errors": ["数据库未连接"]}

        try:
            values = []
            for msg in messages:
                data = msg.data if hasattr(msg, "data") else msg
                values.append(
                    (
                        getattr(msg, "device_id", "") or "",
                        (
                            data.get("event_type", "unknown")
                            if isinstance(data, dict)
                            else "unknown"
                        ),
                        json.dumps(data) if isinstance(data, dict) else None,
                        (
                            data.get("severity", "info")
                            if isinstance(data, dict)
                            else "info"
                        ),
                        datetime.fromtimestamp(getattr(msg, "timestamp", time.time())),
                    )
                )

            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO device_events 
                        (device_id, event_type, event_data, severity, data_timestamp)
                        VALUES %s
                    """
                    execute_values(cursor, query, values, page_size=1000)
                conn.commit()

                result = {"success": True, "processed": len(messages), "errors": []}
                self.batch_stats["events_batches"] += 1
                self.batch_stats["total_records"] += len(messages)

                self.batch_completed.emit("events", result)
                return result

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            error_msg = f"批量插入事件数据失败: {e}"
            self.logger.error(error_msg)
            self.batch_stats["failed_batches"] += 1
            self.batch_failed.emit("events", error_msg)
            return {"success": False, "processed": 0, "errors": [error_msg]}

    def batch_insert_errors(self, messages: List) -> dict:
        """批量插入错误数据"""
        if not self.is_connected():
            return {"success": False, "processed": 0, "errors": ["数据库未连接"]}

        try:
            values = []
            for msg in messages:
                data = msg.data if hasattr(msg, "data") else msg
                values.append(
                    (
                        getattr(msg, "device_id", "") or "",
                        (
                            data.get("error_type", "unknown")
                            if isinstance(data, dict)
                            else "unknown"
                        ),
                        data.get("error_code") if isinstance(data, dict) else None,
                        (
                            data.get("message", str(data))
                            if isinstance(data, dict)
                            else str(data)
                        ),
                        json.dumps(data) if isinstance(data, dict) else None,
                        (
                            data.get("severity", "error")
                            if isinstance(data, dict)
                            else "error"
                        ),
                        datetime.fromtimestamp(getattr(msg, "timestamp", time.time())),
                    )
                )

            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO error_logs 
                        (device_id, error_type, error_code, message, error_data, severity, data_timestamp)
                        VALUES %s
                    """
                    execute_values(cursor, query, values, page_size=1000)
                conn.commit()

                result = {"success": True, "processed": len(messages), "errors": []}
                self.batch_stats["errors_batches"] += 1
                self.batch_stats["total_records"] += len(messages)

                self.batch_completed.emit("errors", result)
                return result

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            error_msg = f"批量插入错误数据失败: {e}"
            self.logger.error(error_msg)
            self.batch_stats["failed_batches"] += 1
            self.batch_failed.emit("errors", error_msg)
            return {"success": False, "processed": 0, "errors": [error_msg]}

    # 查询方法
    def query_telemetry_data(
        self,
        device_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
        order_desc: bool = True,
    ) -> List[Dict]:
        """查询遥测数据"""
        if not self.is_connected():
            return []

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # 构建查询条件
                    conditions = []
                    params = []

                    if device_id:
                        conditions.append("device_id = %s")
                        params.append(device_id)

                    if start_time:
                        conditions.append("data_timestamp >= %s")
                        params.append(start_time)

                    if end_time:
                        conditions.append("data_timestamp <= %s")
                        params.append(end_time)

                    where_clause = (
                        " WHERE " + " AND ".join(conditions) if conditions else ""
                    )
                    order_clause = (
                        "ORDER BY data_timestamp DESC"
                        if order_desc
                        else "ORDER BY data_timestamp ASC"
                    )

                    query = f"""
                        SELECT * FROM telemetry_data
                        {where_clause}
                        {order_clause}
                        LIMIT %s
                    """
                    params.append(limit)

                    cursor.execute(query, params)
                    return [dict(row) for row in cursor.fetchall()]

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            self.logger.error(f"查询遥测数据失败: {e}")
            return []

    def query_alerts(
        self,
        device_id: Optional[str] = None,
        severity: Optional[str] = None,
        unresolved_only: bool = False,
        limit: int = 1000,
    ) -> List[Dict]:
        """查询告警数据"""
        if not self.is_connected():
            return []

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    conditions = []
                    params = []

                    if device_id:
                        conditions.append("device_id = %s")
                        params.append(device_id)

                    if severity:
                        conditions.append("severity = %s")
                        params.append(severity)

                    if unresolved_only:
                        conditions.append("resolved_at IS NULL")

                    where_clause = (
                        " WHERE " + " AND ".join(conditions) if conditions else ""
                    )

                    query = f"""
                        SELECT * FROM alerts
                        {where_clause}
                        ORDER BY data_timestamp DESC
                        LIMIT %s
                    """
                    params.append(limit)

                    cursor.execute(query, params)
                    return [dict(row) for row in cursor.fetchall()]

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            self.logger.error(f"查询告警数据失败: {e}")
            return []

    def query_device_events(
        self,
        device_id: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict]:
        """查询设备事件"""
        if not self.is_connected():
            return []

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    conditions = []
                    params = []

                    if device_id:
                        conditions.append("device_id = %s")
                        params.append(device_id)

                    if event_type:
                        conditions.append("event_type = %s")
                        params.append(event_type)

                    if start_time:
                        conditions.append("data_timestamp >= %s")
                        params.append(start_time)

                    if end_time:
                        conditions.append("data_timestamp <= %s")
                        params.append(end_time)

                    where_clause = (
                        " WHERE " + " AND ".join(conditions) if conditions else ""
                    )

                    query = f"""
                        SELECT * FROM device_events
                        {where_clause}
                        ORDER BY data_timestamp DESC
                        LIMIT %s
                    """
                    params.append(limit)

                    cursor.execute(query, params)
                    return [dict(row) for row in cursor.fetchall()]

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            self.logger.error(f"查询设备事件失败: {e}")
            return []

    def get_device_statistics(self, device_id: str, days: int = 7) -> Dict[str, Any]:
        """获取设备统计信息"""
        if not self.is_connected():
            return {}

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    end_time = datetime.now()
                    start_time = end_time - timedelta(days=days)

                    # 遥测数据统计
                    cursor.execute(
                        """
                        SELECT COUNT(*) as telemetry_count,
                               AVG(temperature) as avg_temperature,
                               AVG(pressure) as avg_pressure,
                               AVG(rf_power) as avg_rf_power
                        FROM telemetry_data 
                        WHERE device_id = %s AND data_timestamp BETWEEN %s AND %s
                    """,
                        (device_id, start_time, end_time),
                    )
                    telemetry_stats = dict(cursor.fetchone())

                    # 告警统计
                    cursor.execute(
                        """
                        SELECT severity, COUNT(*) as count
                        FROM alerts 
                        WHERE device_id = %s AND data_timestamp BETWEEN %s AND %s
                        GROUP BY severity
                    """,
                        (device_id, start_time, end_time),
                    )
                    alert_stats = {
                        row["severity"]: row["count"] for row in cursor.fetchall()
                    }

                    # 事件统计
                    cursor.execute(
                        """
                        SELECT event_type, COUNT(*) as count
                        FROM device_events 
                        WHERE device_id = %s AND data_timestamp BETWEEN %s AND %s
                        GROUP BY event_type
                    """,
                        (device_id, start_time, end_time),
                    )
                    event_stats = {
                        row["event_type"]: row["count"] for row in cursor.fetchall()
                    }

                    return {
                        "device_id": device_id,
                        "period_days": days,
                        "telemetry_stats": telemetry_stats,
                        "alert_stats": alert_stats,
                        "event_stats": event_stats,
                        "query_time": datetime.now(),
                    }

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            self.logger.error(f"获取设备统计失败: {e}")
            return {}

    def get_stats(self) -> DatabaseStats:
        """获取统计信息"""
        # 使用缓存
        current_time = time.time()
        if current_time - self._last_stats_update < 10:
            return self._cached_stats

        stats = DatabaseStats()
        stats.connected = self._connected
        stats.last_check_time = current_time

        if not self.is_connected():
            self._cached_stats = stats
            return stats

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # 获取记录数
                    cursor.execute("SELECT COUNT(*) as count FROM telemetry_data")
                    stats.telemetry_count = cursor.fetchone()["count"]

                    cursor.execute("SELECT COUNT(*) as count FROM alerts")
                    stats.alerts_count = cursor.fetchone()["count"]

                    cursor.execute("SELECT COUNT(*) as count FROM device_events")
                    stats.events_count = cursor.fetchone()["count"]

                    cursor.execute("SELECT COUNT(*) as count FROM error_logs")
                    stats.errors_count = cursor.fetchone()["count"]

                    stats.total_records = (
                        stats.telemetry_count
                        + stats.alerts_count
                        + stats.events_count
                        + stats.errors_count
                    )

                    # 获取数据库大小
                    cursor.execute(
                        "SELECT pg_database_size(current_database()) as size_bytes"
                    )
                    size_bytes = cursor.fetchone()["size_bytes"]
                    stats.database_size_mb = size_bytes / 1024 / 1024

                    # 添加批量统计
                    stats.batch_stats = self.batch_stats.copy()

            finally:
                self._connection_pool.putconn(conn)

            self._cached_stats = stats
            self._last_stats_update = current_time

        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")

        return stats

    def execute_query(
        self, query: str, params: tuple = None, fetch_all: bool = True
    ) -> List[Dict]:
        """执行自定义查询"""
        if not self.is_connected():
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
        if not self.is_connected():
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

    @Slot()
    def _update_stats_async(self):
        """异步更新统计信息"""
        if not self._connected:
            return

        try:
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
        """统计工作函数"""
        try:
            stats = self.get_stats()
            self.stats_updated.emit(stats)
            return {"success": True}
        except Exception as e:
            self.logger.error(f"获取统计失败: {e}")
            return {"success": False, "error": str(e)}

    @Slot()
    def _health_check(self):
        """健康检查"""
        if not self._connection_pool:
            return

        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                    cursor.fetchone()

                if not self._connected:
                    self._connected = True
                    self.connection_changed.emit(True, "数据库连接恢复")

            finally:
                self._connection_pool.putconn(conn)

        except Exception as e:
            if self._connected:
                self._connected = False
                error_msg = f"数据库连接检查失败: {e}"
                self.connection_changed.emit(False, error_msg)
                self.logger.error(error_msg)

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    def shutdown(self):
        """关闭"""
        try:
            self.logger.info("正在关闭数据库管理器...")

            # 停止定时器
            self.stats_timer.stop()
            self.health_timer.stop()

            # 断开连接
            self.disconnect()

            self.logger.info("数据库管理器已关闭")

        except Exception as e:
            self.logger.error(f"关闭数据库管理器失败: {e}")

    # 设备信息 upsert
    def upsert_device_info(self, info: dict) -> bool:
        """
        插入或更新设备信息（如已存在则更新last_seen、status等）
        """
        self.logger.debug(f"准备写入设备信息: {info}")
        if not self.is_connected():
            return False
        try:
            device_id = info.get("device_id")
            if not device_id:
                return False
            # 转换时间戳为 datetime
            last_update_ts = info.get("status", {}).get("last_update") or info.get(
                "timestamp"
            )
            last_seen = (
                datetime.fromtimestamp(last_update_ts)
                if last_update_ts
                else datetime.now()
            )
            conn = self._connection_pool.getconn()

            try:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO devices (device_id, device_type, vendor, first_seen, last_seen, description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                            device_type=EXCLUDED.device_type,
                            vendor=EXCLUDED.vendor,
                            last_seen=EXCLUDED.last_seen,
                            description=EXCLUDED.description
                    """
                    cursor.execute(
                        query,
                        (
                            info.get("device_id"),
                            info.get("device_type"),
                            info.get("vendor"),
                            info.get("first_seen") or datetime.now(),
                            last_seen,
                            info.get("description", ""),
                        ),
                    )
                conn.commit()
                return True
            finally:
                self._connection_pool.putconn(conn)
        except Exception as e:
            self.logger.error(f"upsert_device_info失败: {e}")
            return False

    # 查询所有设备信息
    def get_all_devices(self) -> list:
        """
        获取所有设备信息（返回list[dict]）
        """
        if not self.is_connected():
            return []
        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM devices ORDER BY device_id")
                    return [dict(row) for row in cursor.fetchall()]
            finally:
                self._connection_pool.putconn(conn)
        except Exception as e:
            self.logger.error(f"get_all_devices失败: {e}")
            return []

    # 可选：获取单个设备信息
    def get_device_info(self, device_id: str) -> Optional[dict]:
        if not self.is_connected():
            return None
        try:
            conn = self._connection_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM devices WHERE device_id=%s", (device_id,)
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None
            finally:
                self._connection_pool.putconn(conn)
        except Exception as e:
            self.logger.error(f"get_device_info失败: {e}")
            return None


# 全局实例
db_manager = DatabaseManager()
