import psutil
import time
from datetime import datetime
from PySide6.QtCore import QObject, QTimer, Signal, Slot


class SystemMonitorWorker(QObject):
    """系统资源监控工作线程"""

    system_stats_updated = Signal(dict)
    network_stats_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.running = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)

    @Slot()
    def start_monitoring(self):
        """开始监控"""
        self.running = True
        self.timer.start(1000)  # 每秒更新

    @Slot()
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        self.timer.stop()

    def update_stats(self):
        """更新系统统计信息"""
        if not self.running:
            return

        try:
            # CPU信息
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            # 内存信息
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # 磁盘信息
            disk = psutil.disk_usage("/")

            # 网络信息
            net_io = psutil.net_io_counters()

            system_stats = {
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "cpu_freq": cpu_freq.current if cpu_freq else 0,
                "memory_total": memory.total,
                "memory_used": memory.used,
                "memory_percent": memory.percent,
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": swap.percent,
                "disk_total": disk.total,
                "disk_used": disk.used,
                "disk_percent": (disk.used / disk.total) * 100,
                "timestamp": datetime.now(),
            }

            network_stats = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "timestamp": datetime.now(),
            }

            self.system_stats_updated.emit(system_stats)
            self.network_stats_updated.emit(network_stats)

        except Exception as e:
            print(f"系统监控错误: {e}")
