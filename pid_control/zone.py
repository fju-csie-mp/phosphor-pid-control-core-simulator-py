"""
Zone 區域管理

對應 C++ 原始碼: pid/zone.hpp + pid/zone.cpp + pid/zone_interface.hpp

Zone 是整個風扇控制系統的核心管理單元。

一個 Zone 代表一組「獨立控制」的風扇與感測器。
可以想像成一間獨立的機房，裡面有自己的溫度計和風扇，
自己決定風扇要轉多快，不受其他機房影響。

Zone 的職責：
  1. 管理感測器快取（讀取感測器值並快取，供所有 Controller 使用）
  2. 收集 Thermal PID 的輸出（setpoints），從中選出最大值
  3. 將最大 setpoint 提供給 Fan PID 使用
  4. 處理 failsafe 邏輯（感測器故障時的安全保護）
  5. 協調 Thermal PID 和 Fan PID 的執行順序

在 C++ 版本中，DbusPidZone 同時繼承了 ZoneInterface 和
ModeObject（D-Bus 物件），這裡我們只保留控制邏輯。
"""

from __future__ import annotations

import math
import queue
import sys
from datetime import datetime

from pid_control.conf import ValueCacheEntry
from pid_control.controllers.controller import Controller
from pid_control.sensors.sensor import Sensor, SensorManager


class Zone:
    """
    控制區域。

    對應 C++: pid_control::DbusPidZone (pid/zone.hpp)

    簡化版：移除了 D-Bus、logging、tuning 等 OpenBMC 專用功能，
    保留核心的控制邏輯。

    Attributes:
        _zone_id: Zone 的 ID（例如 0, 1, 2）
        _fans: Fan PID 控制器清單
        _thermals: Thermal PID / Stepwise 控制器清單
        _cached_values: 感測器值快取 {名稱: ValueCacheEntry}
        _fail_safe_sensors: 處於 failsafe 狀態的感測器 {名稱: (原因, 百分比)}
    """

    def __init__(
        self,
        zone_id: int,
        min_thermal_output: float,
        failsafe_percent: float,
        cycle_interval_ms: int,
        update_thermals_ms: int,
        sensor_manager: SensorManager,
        accumulate_set_point: bool = False,
    ):
        """
        Args:
            zone_id: Zone 編號
            min_thermal_output: 最低 RPM 設定點（即使溫度很低也不會低於這個值）
            failsafe_percent: failsafe 模式的風扇百分比
            cycle_interval_ms: 風扇 PID 迴圈間隔（毫秒）
            update_thermals_ms: 溫度 PID 迴圈間隔（毫秒）
            sensor_manager: 感測器管理器
            accumulate_set_point: 是否累加不同控制器的 setpoint
        """
        self._zone_id = zone_id
        self._min_thermal_output = min_thermal_output
        self._zone_failsafe_percent = failsafe_percent
        self._cycle_interval_ms = cycle_interval_ms
        self._update_thermals_ms = update_thermals_ms
        self._mgr = sensor_manager
        self._accumulate_set_point = accumulate_set_point

        # --- 運行狀態 ---
        self._maximum_set_point: float = 0.0
        self._maximum_set_point_name: str = ""
        self._manual_mode: bool = False
        self._redundant_write: bool = False

        # 感測器值快取: {感測器名稱: ValueCacheEntry}
        self._cached_values: dict[str, ValueCacheEntry] = {}
        # 風扇輸出快取（用於 logging）
        self._cached_fan_outputs: dict[str, ValueCacheEntry] = {}

        # Failsafe 相關
        # key=感測器名稱, value=(故障原因, failsafe 百分比)
        self._fail_safe_sensors: dict[str, tuple[str, float]] = {}
        self._missing_acceptable: set[str] = set()
        self._sensor_failsafe_percent: dict[str, float] = {}

        # Setpoint 收集
        self._set_points: dict[str, float] = {}
        self._rpm_ceilings: list[float] = []

        # 輸入感測器名稱清單
        self._fan_inputs: list[str] = []
        self._thermal_inputs: list[str] = []

        # 控制器清單
        self._fans: list[Controller] = []
        self._thermals: list[Controller] = []

        # Queue（用於 threading 模式，接收 SensorThread 的感測器更新）
        # 在直接呼叫模式（BDD 測試）下不使用
        self._sensor_queue: queue.Queue = queue.Queue()

    # =========================================================================
    # Zone 基本資訊
    # =========================================================================

    def get_zone_id(self) -> int:
        return self._zone_id

    def get_manual_mode(self) -> bool:
        """是否在手動模式（手動模式下 PID 不計算，風扇維持手動設定值）"""
        return self._manual_mode

    def set_manual_mode(self, mode: bool) -> None:
        self._manual_mode = mode
        if not mode:
            # 回到自動模式時，需要強制寫一次風扇值，確保同步
            self._redundant_write = True

    def get_redundant_write(self) -> bool:
        return self._redundant_write

    def get_failsafe_mode(self) -> bool:
        """
        Zone 是否處於 failsafe 模式。

        只要有任何一個感測器在 fail_safe_sensors 中，就算是 failsafe。
        """
        return len(self._fail_safe_sensors) > 0

    def get_failsafe_percent(self) -> float:
        """
        取得 failsafe 百分比。

        如果有多個感測器各自設定了不同的 failsafe 百分比，
        取最大的那個（最保守的策略）。
        """
        if not self._fail_safe_sensors:
            return self._zone_failsafe_percent

        max_pct = max(pct for _, pct in self._fail_safe_sensors.values())
        return max_pct if max_pct > 0 else self._zone_failsafe_percent

    def get_failsafe_sensors(self) -> dict[str, tuple[str, float]]:
        return self._fail_safe_sensors.copy()

    def get_cycle_interval_time(self) -> int:
        """風扇 PID 迴圈間隔（毫秒）"""
        return self._cycle_interval_ms

    def get_update_thermals_cycle(self) -> int:
        """溫度 PID 迴圈間隔（毫秒）"""
        return self._update_thermals_ms

    def get_acc_set_point(self) -> bool:
        return self._accumulate_set_point

    # =========================================================================
    # 感測器快取操作
    # =========================================================================

    def get_sensor(self, name: str) -> Sensor:
        """根據名稱取得感測器實例"""
        return self._mgr.get_sensor(name)

    def get_cached_value(self, name: str) -> float:
        """取得感測器的快取值（scaled）"""
        return self._cached_values[name].scaled

    def get_cached_values(self, name: str) -> ValueCacheEntry:
        """取得感測器的快取值（含 scaled 和 unscaled）"""
        return self._cached_values[name]

    def set_output_cache(self, name: str, values: ValueCacheEntry) -> None:
        """設定風扇輸出快取（用於 logging）"""
        self._cached_fan_outputs[name] = values

    def initialize_cache(self) -> None:
        """
        初始化所有感測器的快取值為 NaN，並標記為 failsafe。

        對應 C++: DbusPidZone::initializeCache() (zone.cpp:503-523)

        啟動時，所有感測器都被視為「遺失」，進入 failsafe 模式。
        等到感測器開始回報有效數值後，才會逐一從 failsafe 中移除。
        """
        nan = float("nan")
        for f in self._fan_inputs:
            self._cached_values[f] = ValueCacheEntry(nan, nan)
            self._cached_fan_outputs[f] = ValueCacheEntry(nan, nan)
            self._mark_sensor_missing(f, "初始化")

        for t in self._thermal_inputs:
            self._cached_values[t] = ValueCacheEntry(nan, nan)
            self._mark_sensor_missing(t, "初始化")

    # =========================================================================
    # 感測器更新（從模擬感測器讀取新值到快取）
    # =========================================================================

    def _process_sensor_inputs(self, sensor_names: list[str]) -> None:
        """
        讀取一組感測器的值到快取，並檢查超時/故障。

        對應 C++: DbusPidZone::processSensorInputs<>() (zone.hpp:144-223)

        這是 Zone 中很關鍵的方法：
          1. 從感測器讀取最新值
          2. 存入快取
          3. 檢查感測器是否故障或超時
          4. 如果故障 → 加入 failsafe 清單
          5. 如果恢復 → 從 failsafe 清單中移除

        Args:
            sensor_names: 要處理的感測器名稱清單
        """
        now = datetime.now()
        for name in sensor_names:
            sensor = self._mgr.get_sensor(name)
            r = sensor.read()
            self._cached_values[name] = ValueCacheEntry(
                scaled=r.value, unscaled=r.unscaled
            )

            timeout = sensor.get_timeout()
            # 檢查時間差（秒）
            duration = (now - r.updated).total_seconds()

            # --- 檢查感測器是否故障 ---
            if sensor.get_failed():
                self._mark_sensor_missing(name, sensor.get_fail_reason())
            elif timeout != 0 and duration >= timeout:
                self._mark_sensor_missing(name, "感測器超時")
            else:
                # 感測器正常 → 如果之前在 failsafe 中，移除它
                if name in self._fail_safe_sensors:
                    del self._fail_safe_sensors[name]

    def update_fan_telemetry(self) -> None:
        """
        更新所有風扇感測器的快取。

        對應 C++: DbusPidZone::updateFanTelemetry() (zone.cpp:465-493)
        """
        self._process_sensor_inputs(self._fan_inputs)

    def update_sensors(self) -> None:
        """
        更新所有溫度感測器的快取。

        對應 C++: DbusPidZone::updateSensors() (zone.cpp:495-501)
        """
        self._process_sensor_inputs(self._thermal_inputs)

    # =========================================================================
    # Queue 模式的感測器更新（用於 threading 模式）
    # =========================================================================

    def get_sensor_queue(self) -> queue.Queue:
        """取得此 Zone 的感測器更新 Queue（供 SensorThread 使用）"""
        return self._sensor_queue

    def drain_queue(self) -> None:
        """
        從 Queue 取出所有感測器更新，寫入快取並檢查 failsafe。

        對應原始架構: DbusPassive 收到 D-Bus signal 後更新快取。

        這是 threading 模式下取代 update_sensors() / update_fan_telemetry()
        的方法。SensorThread 把感測器值 put 到 Queue，Zone Thread 用
        drain_queue() 一次取出所有累積的值。

        Observer Pattern 的「通知處理」就在這裡：
          - SensorThread publish（put）→ Zone subscribe（drain_queue）
        """
        from pid_control.sensor_thread import SensorUpdate

        while True:
            try:
                update: SensorUpdate = self._sensor_queue.get_nowait()
            except queue.Empty:
                break

            # 更新快取
            self._cached_values[update.name] = ValueCacheEntry(
                scaled=update.value, unscaled=update.unscaled
            )

            # 檢查感測器是否故障
            if update.failed:
                self._mark_sensor_missing(update.name, update.fail_reason)
            else:
                # 檢查超時
                sensor = self._mgr.get_sensor(update.name)
                timeout = sensor.get_timeout()
                if timeout != 0:
                    duration = (datetime.now() - update.timestamp).total_seconds()
                    if duration >= timeout:
                        self._mark_sensor_missing(update.name, "感測器超時")
                    elif update.name in self._fail_safe_sensors:
                        del self._fail_safe_sensors[update.name]
                else:
                    if update.name in self._fail_safe_sensors:
                        del self._fail_safe_sensors[update.name]

    # =========================================================================
    # Setpoint 管理
    # =========================================================================

    def add_set_point(self, set_point: float, name: str) -> None:
        """
        加入一個 RPM setpoint 值。

        對應 C++: DbusPidZone::addSetPoint() (zone.cpp:132-167)

        每個 Thermal/Stepwise Controller 計算完後都會呼叫這個方法。
        Zone 會收集所有的 setpoint，最後取最大值給 Fan PID 使用。

        Args:
            set_point: 目標 RPM 值
            name: 提交此 setpoint 的控制器名稱
        """
        profile_name = name
        if self._accumulate_set_point:
            # 累加模式：同名 profile 的 setpoint 加總
            profile_name = name.split("_", 1)[-1] if "_" in name else name
            self._set_points[profile_name] = (
                self._set_points.get(profile_name, 0.0) + set_point
            )
        else:
            # 非累加模式：取同名 profile 中最大的
            if self._set_points.get(profile_name, 0.0) < set_point:
                self._set_points[profile_name] = set_point

        # 追蹤全域最大值
        if self._maximum_set_point < self._set_points.get(profile_name, 0.0):
            self._maximum_set_point = self._set_points[profile_name]
            self._maximum_set_point_name = profile_name

    def add_rpm_ceiling(self, ceiling: float) -> None:
        """加入 RPM 上限值（由 is_ceiling=True 的 Stepwise 提交）"""
        self._rpm_ceilings.append(ceiling)

    def clear_set_points(self) -> None:
        """清除所有 setpoint（每次 thermal cycle 開始前呼叫）"""
        self._set_points.clear()
        self._maximum_set_point = 0.0
        self._maximum_set_point_name = ""

    def clear_rpm_ceilings(self) -> None:
        """清除所有 RPM 上限"""
        self._rpm_ceilings.clear()

    def determine_max_set_point_request(self) -> None:
        """
        計算最終的最大 RPM setpoint。

        對應 C++: DbusPidZone::determineMaxSetPointRequest() (zone.cpp:335-423)

        考慮因素：
          1. RPM 上限（ceiling）：如果最大 setpoint 超過上限，降到上限
          2. 最低 RPM 門檻：即使溫度很低，也不會讓風扇低於此值
        """
        # 如果有 RPM 上限，取最小的上限值
        if self._rpm_ceilings:
            min_ceiling = min(self._rpm_ceilings)
            if min_ceiling < self._maximum_set_point:
                self._maximum_set_point = min_ceiling
                self._maximum_set_point_name = "Ceiling"

        # 如果低於最低門檻，用最低門檻
        if self._min_thermal_output >= self._maximum_set_point:
            self._maximum_set_point = self._min_thermal_output
            self._maximum_set_point_name = "Minimum"

    def get_max_set_point_request(self) -> float:
        """取得最終的最大 RPM setpoint（Fan PID 會用這個值）"""
        return self._maximum_set_point

    # =========================================================================
    # 控制器管理
    # =========================================================================

    def add_fan_pid(self, controller: Controller) -> None:
        """加入一個 Fan PID 控制器"""
        self._fans.append(controller)

    def add_thermal_pid(self, controller: Controller) -> None:
        """加入一個 Thermal PID / Stepwise 控制器"""
        self._thermals.append(controller)

    def add_fan_input(self, fan: str, missing_acceptable: bool = False) -> None:
        """註冊一個風扇輸入感測器"""
        self._fan_inputs.append(fan)
        if missing_acceptable:
            self._missing_acceptable.add(fan)

    def add_thermal_input(
        self, therm: str, missing_acceptable: bool = False
    ) -> None:
        """註冊一個溫度輸入感測器（避免重複）"""
        if therm not in self._thermal_inputs:
            self._thermal_inputs.append(therm)
        if missing_acceptable:
            self._missing_acceptable.add(therm)

    # =========================================================================
    # 控制迴圈的執行
    # =========================================================================

    def process_fans(self) -> None:
        """
        執行所有 Fan PID 控制器。

        對應 C++: DbusPidZone::processFans() (zone.cpp:542-554)
        """
        for controller in self._fans:
            controller.process()

        if self._redundant_write:
            self._redundant_write = False

    def process_thermals(self) -> None:
        """
        執行所有 Thermal PID / Stepwise 控制器。

        對應 C++: DbusPidZone::processThermals() (zone.cpp:556-562)
        """
        for controller in self._thermals:
            controller.process()

    # =========================================================================
    # Failsafe 機制
    # =========================================================================

    def _mark_sensor_missing(self, name: str, reason: str) -> None:
        """
        標記一個感測器為遺失（進入 failsafe）。

        對應 C++: DbusPidZone::markSensorMissing() (zone.cpp:97-125)

        如果感測器在 missing_acceptable 清單中，不會觸發 failsafe。

        Args:
            name: 感測器名稱
            reason: 遺失原因
        """
        if name in self._missing_acceptable:
            return

        pct = self._sensor_failsafe_percent.get(name, 0.0)
        if pct == 0:
            pct = self._zone_failsafe_percent
        self._fail_safe_sensors[name] = (reason, pct)

    def add_pid_failsafe_percent(
        self, inputs: list[str], percent: float
    ) -> None:
        """為特定感測器設定個別的 failsafe 百分比"""
        for name in inputs:
            current = self._sensor_failsafe_percent.get(name, 0.0)
            self._sensor_failsafe_percent[name] = max(current, percent)
