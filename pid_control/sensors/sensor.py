"""
感測器基底類別與模擬實作

對應 C++ 原始碼:
  - sensors/sensor.hpp (Sensor 基底類別)
  - dbus/dbuspassive.cpp (DbusPassive — 我們用 SimulatedSensor 取代)
  - sysfs/sysfswrite.cpp (SysFsWrite — 我們用 SimulatedFan 取代)

在原始的 OpenBMC 版本中，感測器透過 D-Bus 或 sysfs 跟真實硬體溝通。
這裡我們用模擬的方式取代，讓程式可以在任何電腦上執行。
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime

from pid_control.conf import ReadReturn, ValueCacheEntry


class Sensor:
    """
    感測器基底類別。

    對應 C++: pid_control::Sensor (sensors/sensor.hpp)

    所有感測器（溫度感測器、風扇轉速感測器）都繼承自這個類別。
    提供統一的介面：read() 讀值、write() 寫值、getName() 取名稱。
    """

    def __init__(self, name: str, timeout: int = 0):
        """
        Args:
            name: 感測器名稱（例如 "temp_cpu0", "fan0"）
            timeout: 超時秒數，超過這個時間沒有新讀數就視為故障。
                     0 表示不檢查超時（風扇預設為 0）
        """
        self._name = name
        self._timeout = timeout

    def read(self) -> ReadReturn:
        """讀取感測器當前值（子類別必須覆寫）"""
        raise NotImplementedError

    def write(self, value: float, force: bool = False) -> int | None:
        """寫入控制值（子類別必須覆寫）"""
        raise NotImplementedError

    def get_failed(self) -> bool:
        """此感測器是否故障（預設為 False，子類別可覆寫）"""
        return False

    def get_fail_reason(self) -> str:
        """故障原因（預設為空字串）"""
        return ""

    def get_name(self) -> str:
        return self._name

    def get_timeout(self) -> int:
        return self._timeout


class SimulatedSensor(Sensor):
    """
    模擬溫度感測器 — 用數學函數產生溫度值。

    取代 C++ 中的 DbusPassive（從 D-Bus 讀取真實感測器值）。

    預設行為：產生一個在 base_temp 附近波動的溫度值。
    波動方式：正弦波 + 隨機噪音，模擬真實環境中溫度的緩慢變化。
    """

    def __init__(
        self,
        name: str,
        timeout: int = 2,
        base_temp: float = 40.0,
        amplitude: float = 10.0,
        noise: float = 1.0,
        period: float = 30.0,
    ):
        """
        Args:
            name: 感測器名稱
            timeout: 超時秒數
            base_temp: 基礎溫度（中心溫度）
            amplitude: 正弦波振幅（溫度波動範圍）
            noise: 隨機噪音大小
            period: 正弦波週期（秒），模擬溫度變化的快慢
        """
        super().__init__(name, timeout)
        self._base_temp = base_temp
        self._amplitude = amplitude
        self._noise = noise
        self._period = period
        self._start_time = time.time()
        self._failed = False

    def read(self) -> ReadReturn:
        """
        讀取模擬溫度值。

        公式: temp = base + amplitude * sin(2π * t / period) + random_noise
        """
        elapsed = time.time() - self._start_time
        # 正弦波模擬溫度的緩慢升降
        sine_component = self._amplitude * math.sin(
            2 * math.pi * elapsed / self._period
        )
        # 隨機噪音模擬感測器的微小抖動
        noise_component = random.uniform(-self._noise, self._noise)

        value = self._base_temp + sine_component + noise_component
        return ReadReturn(value=value, updated=datetime.now(), unscaled=value)

    def get_failed(self) -> bool:
        return self._failed

    def set_failed(self, failed: bool, reason: str = "Simulated failure"):
        """手動設定感測器為故障狀態（用於測試 failsafe）"""
        self._failed = failed
        self._fail_reason = reason

    def get_fail_reason(self) -> str:
        return getattr(self, "_fail_reason", "")


class SimulatedFan(Sensor):
    """
    模擬風扇 — 印出 PWM 值並追蹤當前轉速。

    取代 C++ 中的 SysFsWrite（寫入 Linux sysfs 控制實際風扇 PWM）
    和 SysFsRead（讀取實際風扇轉速）。

    模擬行為：
      - write() 收到 PWM 百分比後，模擬計算對應的 RPM
      - read() 回傳當前模擬的 RPM
      - RPM 不會瞬間到達目標，會有一個簡單的延遲模擬
    """

    def __init__(
        self,
        name: str,
        timeout: int = 0,
        max_rpm: float = 10000.0,
        min_pwm: int = 0,
        max_pwm: int = 255,
    ):
        """
        Args:
            name: 風扇名稱（例如 "fan0"）
            timeout: 超時秒數（風扇通常設為 0 = 不檢查超時）
            max_rpm: 100% PWM 對應的最大 RPM
            min_pwm: PWM 最小原始值
            max_pwm: PWM 最大原始值
        """
        super().__init__(name, timeout)
        self._max_rpm = max_rpm
        self._min_pwm = min_pwm
        self._max_pwm = max_pwm
        self._current_pwm = 0.0  # 當前 PWM (0.0 ~ 1.0)
        self._current_rpm = 0.0  # 當前模擬 RPM
        self._last_written_raw: int | None = None

    def read(self) -> ReadReturn:
        """
        讀取風扇當前轉速（模擬 RPM）。

        模擬：RPM = PWM 百分比 × 最大 RPM + 一些隨機噪音
        """
        # 模擬 RPM：根據當前 PWM 線性計算，加一點噪音
        target_rpm = self._current_pwm * self._max_rpm
        noise = random.uniform(-50, 50) if target_rpm > 0 else 0
        self._current_rpm = max(0, target_rpm + noise)

        return ReadReturn(
            value=self._current_rpm,
            updated=datetime.now(),
            unscaled=self._current_rpm,
        )

    def write(self, value: float, force: bool = False) -> int | None:
        """
        寫入 PWM 值到風扇。

        Args:
            value: PWM 百分比 (0.0 ~ 1.0)
            force: 是否強制寫入

        Returns:
            實際寫入的原始 PWM 值（0 ~ max_pwm）
        """
        # 把 0.0~1.0 的百分比轉成原始 PWM 值（例如 0~255）
        raw = int(value * (self._max_pwm - self._min_pwm) + self._min_pwm)
        raw = max(self._min_pwm, min(raw, self._max_pwm))

        self._current_pwm = value
        self._last_written_raw = raw
        return raw

    def get_min(self) -> int:
        return self._min_pwm

    def get_max(self) -> int:
        return self._max_pwm

    @property
    def current_pwm_percent(self) -> float:
        """取得當前 PWM 百分比（0~100 的格式，方便顯示）"""
        return self._current_pwm * 100.0

    @property
    def current_rpm(self) -> float:
        """取得當前模擬 RPM"""
        return self._current_rpm


class SensorManager:
    """
    感測器管理器 — 集中管理所有感測器實例。

    對應 C++: SensorManager (sensors/manager.hpp)

    用途：其他元件（Zone、Controller）透過名稱來查找感測器。
    """

    def __init__(self):
        self._sensors: dict[str, Sensor] = {}

    def add_sensor(self, name: str, sensor: Sensor) -> None:
        """註冊一個感測器"""
        self._sensors[name] = sensor

    def get_sensor(self, name: str) -> Sensor:
        """
        根據名稱取得感測器。

        Raises:
            KeyError: 如果找不到該感測器
        """
        return self._sensors[name]

    def get_all_names(self) -> list[str]:
        """取得所有已註冊的感測器名稱"""
        return list(self._sensors.keys())
