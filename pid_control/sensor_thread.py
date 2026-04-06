"""
Sensor Thread — 模擬 phosphor-hwmon daemon

對應原始 C++ 架構中的 phosphor-hwmon daemon + D-Bus signal publish。

在原始 OpenBMC 中，phosphor-hwmon 是一個獨立的 daemon，
它定期讀取硬體感測器（透過 sysfs），然後透過 D-Bus signal
把感測器值廣播出去。swampd（PID 控制 daemon）訂閱這些 signal，
收到後更新自己的快取。

這裡我們用 threading.Thread + queue.Queue 模擬這個架構：
  - SensorThread 扮演 phosphor-hwmon，定期讀取 SimulatedSensor
  - 把值透過 Queue 送給各個 Zone Thread
  - Queue 取代了 D-Bus signal 的角色

這就是 Observer Pattern 的實現：
  - SensorThread 是 Subject（發布者）
  - Zone 是 Observer（訂閱者）
  - Queue 是通訊通道
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from pid_control.sensors.sensor import SensorManager


@dataclass
class SensorUpdate:
    """
    透過 Queue 傳遞的感測器更新訊息。

    Attributes:
        name: 感測器名稱（例如 "temp_cpu0", "fan0"）
        value: 讀到的數值
        unscaled: 未縮放的原始值
        timestamp: 讀取時間
        failed: 感測器是否故障
        fail_reason: 故障原因
    """
    name: str
    value: float
    unscaled: float
    timestamp: datetime
    failed: bool = False
    fail_reason: str = ""


class SensorThread:
    """
    感測器執行緒 — 定期讀取感測器並透過 Queue 發送更新。

    對應原始架構: phosphor-hwmon daemon 透過 D-Bus signal 發布感測器值。

    使用方式:
        sensor_thread = SensorThread(sensor_manager, zone_queues, interval=1.0)
        thread = threading.Thread(target=sensor_thread.run, args=(stop_event,))
        thread.start()

    Attributes:
        _sensor_manager: 管理所有感測器的 SensorManager
        _zone_queues: Zone ID → Queue 的對應，每個 Zone 一個 Queue
        _zone_sensors: Zone ID → 該 Zone 關心的感測器名稱清單
        _interval: 讀取感測器的間隔（秒）
    """

    def __init__(
        self,
        sensor_manager: SensorManager,
        zone_queues: dict[int, queue.Queue[SensorUpdate]],
        zone_sensors: dict[int, list[str]],
        interval: float = 1.0,
    ):
        """
        Args:
            sensor_manager: 感測器管理器
            zone_queues: {zone_id: Queue} — 每個 Zone 的接收佇列
            zone_sensors: {zone_id: [sensor_names]} — 每個 Zone 訂閱的感測器
            interval: 讀取間隔（秒）
        """
        self._sensor_manager = sensor_manager
        self._zone_queues = zone_queues
        self._zone_sensors = zone_sensors
        self._interval = interval

    def run(self, stop_event: threading.Event) -> None:
        """
        主迴圈：定期讀取所有感測器，把值透過 Queue 發送給各 Zone。

        Args:
            stop_event: 收到此 event 時停止迴圈（用於優雅關閉）
        """
        while not stop_event.is_set():
            self._read_and_publish()
            # 用 wait 而不是 sleep，這樣 stop_event 被 set 時能立即醒來
            stop_event.wait(timeout=self._interval)

    def _read_and_publish(self) -> None:
        """讀取所有感測器並發送更新到對應的 Zone Queue"""
        # 收集所有需要讀取的感測器（去重）
        all_sensor_names: set[str] = set()
        for names in self._zone_sensors.values():
            all_sensor_names.update(names)

        # 讀取每個感測器一次，快取結果
        readings: dict[str, SensorUpdate] = {}
        for name in all_sensor_names:
            sensor = self._sensor_manager.get_sensor(name)
            r = sensor.read()
            readings[name] = SensorUpdate(
                name=name,
                value=r.value,
                unscaled=r.unscaled,
                timestamp=r.updated,
                failed=sensor.get_failed(),
                fail_reason=sensor.get_fail_reason(),
            )

        # 把讀數發送到對應的 Zone Queue
        for zone_id, sensor_names in self._zone_sensors.items():
            q = self._zone_queues[zone_id]
            for name in sensor_names:
                if name in readings:
                    q.put(readings[name])
