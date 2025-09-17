# data/device_data_manager.py
from collections import defaultdict, deque
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class DeviceData:
    device_id: str
    device_type: str = "UNKNOWN"
    recipe: str = ""
    step: str = ""
    lot_id: str = ""
    wafer_id: str = ""
    temperature: deque = None
    pressure: deque = None
    rf_power: deque = None
    endpoint: deque = None
    timestamps: deque = None
    last_update: Optional[float] = None

    def __post_init__(self):
        if self.temperature is None:
            self.temperature = deque(maxlen=300)
        if self.pressure is None:
            self.pressure = deque(maxlen=300)
        # ... 其他字段初始化


class DeviceDataManager:
    """设备数据管理器 - 纯数据操作，无UI依赖"""

    def __init__(self):
        self.devices: Dict[str, DeviceData] = {}

    def update_device_data(self, device_id: str, data_item: Dict[str, Any]):
        """更新设备数据"""
        if device_id not in self.devices:
            self.devices[device_id] = DeviceData(device_id=device_id)

        device = self.devices[device_id]
        current_time = time.time()

        # 更新数据
        device.device_type = data_item.get("device_type", device.device_type)
        device.recipe = data_item.get("rt", data_item.get("recipe", device.recipe))
        device.last_update = current_time

        # 添加传感器数据
        device.timestamps.append(current_time)
        device.temperature.append(data_item.get("t", 0.0))
        device.pressure.append(data_item.get("p", 0.0))
        # ... 其他传感器数据

    def get_device_data(self, device_id: str) -> Optional[DeviceData]:
        """获取设备数据"""
        return self.devices.get(device_id)

    def get_active_devices(self, timeout: float = 30.0) -> list[str]:
        """获取活跃设备列表"""
        current_time = time.time()
        return [
            device_id
            for device_id, device in self.devices.items()
            if device.last_update and (current_time - device.last_update) < timeout
        ]
