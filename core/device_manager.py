import time
import logging
from typing import Dict, Any, Optional, List
from PySide6.QtCore import QObject, Signal, Slot, QTimer
from core.data_bus import data_bus, DataChannel, DataMessage
from core.database_manager import db_manager


class DeviceManager(QObject):
    """
    统一设备管理器：负责设备的注册、状态维护、缓存、持久化与UI联动
    """

    device_list_updated = Signal(list)  # 设备列表变更
    device_statistics_updated = Signal(str, dict)  # 单设备统计变更
    device_discovered = Signal(str, dict)  # 新设备发现

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("DeviceManager")
        self.device_data_dict: Dict[str, Dict[str, Any]] = {}
        self.device_stats: Dict[str, dict] = {}

        # 定时器：定期刷新设备在线状态并持久化
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_all_device_status)
        self.status_timer.start(10000)  # 10秒

        # 从数据库加载设备（仅基本信息，状态默认离线）
        self.load_devices_from_db()

        # 订阅 DataBus 遥测数据和设备事件
        data_bus.subscribe(DataChannel.TELEMETRY_DATA, self._on_data_received)
        data_bus.subscribe(DataChannel.DEVICE_EVENTS, self._on_data_received)

    @Slot()
    def _on_data_received(self, msg: DataMessage):
        """任何遥测或事件数据到达 = 设备活跃 = 在线"""
        device_id = msg.device_id
        if not device_id:
            return

        now = time.time()
        if device_id not in self.device_data_dict:
            # 首次发现设备
            self.device_data_dict[device_id] = {
                "device_id": device_id,
                "device_type": msg.data.get("device_type", "UNKNOWN"),
                "vendor": msg.data.get("vendor", "UNKNOWN"),
                "first_seen": now,
                "last_update": now,
                "online": True,
            }
            self.device_discovered.emit(device_id, self.device_data_dict[device_id])
        else:
            # 更新最后活跃时间，设为在线
            self.device_data_dict[device_id]["last_update"] = now
            self.device_data_dict[device_id]["online"] = True

        self.device_list_updated.emit(list(self.device_data_dict.keys()))

    def refresh_all_device_status(self):
        """定时刷新所有设备的在线/离线状态，并持久化在线设备的 last_seen"""
        now = time.time()
        for device_id, info in self.device_data_dict.items():
            # 超过30秒无数据 → 离线
            if info["online"] and (now - info["last_update"]) >= 30:
                info["online"] = False
                self.logger.info(f"设备自动离线: {device_id}")

        # 仅持久化当前在线的设备（更新 last_seen = now）
        for device_id, info in self.device_data_dict.items():
            if info["online"]:
                db_info = {
                    "device_id": device_id,
                    "device_type": info["device_type"],
                    "vendor": info["vendor"],
                    "first_seen": info.get("first_seen"),
                    "status": {"last_update": now},  # 用于 last_seen
                }
                self.persist_device_info(db_info)

        self.device_list_updated.emit(list(self.device_data_dict.keys()))

    def get_device_info(self, device_id: str) -> Optional[dict]:
        return self.device_data_dict.get(device_id)

    def get_all_devices(self) -> List[str]:
        return list(self.device_data_dict.keys())

    def clear_all(self):
        self.device_data_dict.clear()
        self.device_stats.clear()
        self.device_list_updated.emit([])

    def persist_device_info(self, info: dict):
        """将设备信息写入数据库（仅更新 last_seen）"""
        success = db_manager.upsert_device_info(info)
        if success:
            self.logger.debug(f"设备 last_seen 已更新: {info['device_id']}")
        else:
            self.logger.error(f"设备持久化失败: {info['device_id']}")

    def load_devices_from_db(self):
        """从数据库加载设备信息（仅基本信息，状态默认离线）"""
        devices = db_manager.get_all_devices()
        for info in devices:
            device_id = info["device_id"]
            self.device_data_dict[device_id] = {
                "device_id": device_id,
                "device_type": info.get("device_type", "UNKNOWN"),
                "vendor": info.get("vendor", "UNKNOWN"),
                "first_seen": info.get("first_seen"),
                "last_update": 0,
                "online": False,
            }
        self.device_list_updated.emit(list(self.device_data_dict.keys()))


# 全局实例
device_manager = DeviceManager()
