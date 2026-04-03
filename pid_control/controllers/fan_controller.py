"""
風扇控制器

對應 C++ 原始碼: pid/fancontroller.hpp + pid/fancontroller.cpp

FanController 負責：
  1. 讀取所有風扇的當前 RPM（inputProc）
  2. 從 Zone 取得 Thermal PID 算出的目標 RPM（setptProc）
  3. 用 PID 計算需要的 PWM 百分比（process → calPIDOutput）
  4. 將 PWM 寫入每個風扇（outputProc）

在整個控制迴圈中的位置：
  Thermal PID 算出目標 RPM → Fan PID 把目標 RPM 轉成 PWM → 寫入風扇

Fan PID 執行頻率較高（每 0.1 秒一次），因為風扇的 RPM 回饋速度比較快。
"""

from __future__ import annotations

import math
import sys
from enum import Enum
from typing import TYPE_CHECKING

from pid_control.controllers.pid_controller import PIDController
from pid_control.ec.pid import PidConfig, PidInfo, initialize_pid_info

if TYPE_CHECKING:
    from pid_control.zone import Zone


class FanSpeedDirection(Enum):
    """
    風扇速度變化方向。

    對應 C++: FanSpeedDirection (fan.hpp)
    """
    DOWN = "down"       # 正在減速
    UP = "up"           # 正在加速
    NEUTRAL = "neutral" # 速度不變


class FanController(PIDController):
    """
    風扇 PID 控制器。

    對應 C++: pid_control::FanController (pid/fancontroller.hpp)

    控制邏輯：
      - input: 讀取所有風扇的當前 RPM，取最小值
        （原因：取最小值讓 PID 更穩定，避免平均值被高速風扇拉高）
      - setpoint: 從 Zone 取得「所有 Thermal PID 中最大的目標 RPM」
      - output: 把計算出的 PWM 百分比寫入每個風扇

    還包含 failsafe 邏輯：
      如果任何感測器進入 failsafe 模式，風扇 PWM 會被強制拉高到安全值。
    """

    def __init__(
        self,
        controller_id: str,
        inputs: list[str],
        owner: Zone,
    ):
        """
        Args:
            controller_id: 控制器名稱
            inputs: 此控制器管理的風扇名稱清單
            owner: 擁有此控制器的 Zone
        """
        super().__init__(controller_id, owner)
        self._inputs = inputs
        self._direction = FanSpeedDirection.NEUTRAL
        # 用於減少重複的 failsafe 狀態轉換訊息
        self._failsafe_transition = True
        self._failsafe_prev_state = False

    @staticmethod
    def create(
        owner: Zone,
        controller_id: str,
        inputs: list[str],
        pid_config: PidConfig,
    ) -> FanController | None:
        """
        工廠方法 — 建立 FanController 實例。

        對應 C++: FanController::createFanPid() (fancontroller.cpp:29-43)

        這是 **Factory Method Pattern**：
          把「物件建立」的邏輯封裝在靜態方法中，
          外部呼叫者不需要知道初始化的細節。

        Args:
            owner: 所屬的 Zone
            controller_id: 控制器名稱
            inputs: 風扇名稱清單
            pid_config: PID 參數

        Returns:
            建好的 FanController，或 None（如果沒有 inputs）
        """
        if not inputs:
            return None

        fan = FanController(controller_id, inputs, owner)
        initialize_pid_info(fan.get_pid_info(), pid_config)
        return fan

    def input_proc(self) -> float:
        """
        讀取所有風扇的 RPM，回傳最小值。

        對應 C++: FanController::inputProc() (fancontroller.cpp:45-97)

        為什麼取最小值？
          - 在多風扇系統中，如果取平均值，某個風扇很快另一個很慢，
            PID 看到的「平均值」可能接近目標，但慢的那個風扇其實還不夠快
          - 取最小值，PID 會根據「最慢的風扇」來調整，確保所有風扇都能達標

        Returns:
            所有風扇中最小的 RPM 值（忽略無效值和 0）
        """
        values: list[float] = []

        for name in self._inputs:
            # 從 Zone 的快取中讀取風扇 RPM（unscaled 是原始 RPM）
            cached = self._owner.get_cached_values(name)
            value = cached.unscaled

            # 跳過無效值（NaN, 無限大）
            if not math.isfinite(value):
                continue
            # 跳過 0 值（風扇可能故障或還沒開始轉）
            if value <= 0.0:
                continue

            values.append(value)

        if values:
            return min(values)  # 取最小值
        return 0.0

    def setpt_proc(self) -> float:
        """
        取得目標 RPM 設定點。

        對應 C++: FanController::setptProc() (fancontroller.cpp:99-122)

        從 Zone 取得「所有 Thermal PID 計算結果中最大的 RPM」。
        同時記錄風扇速度的變化方向。

        Returns:
            目標 RPM 值
        """
        max_rpm = self._owner.get_max_set_point_request()

        # 記錄速度方向（純粹用於 debug/log）
        prev = self.get_setpoint()
        if max_rpm > prev:
            self._direction = FanSpeedDirection.UP
        elif prev > max_rpm:
            self._direction = FanSpeedDirection.DOWN
        else:
            self._direction = FanSpeedDirection.NEUTRAL

        self.set_setpoint(max_rpm)
        return max_rpm

    def output_proc(self, value: float) -> None:
        """
        把計算出的 PWM 寫入所有風扇。

        對應 C++: FanController::outputProc() (fancontroller.cpp:124-220)

        包含 failsafe 邏輯：
          1. 如果 Zone 在 failsafe 模式，PWM 至少要是 failsafe 百分比
          2. 把百分比（例如 75%）轉成 0.0~1.0 再寫入風扇

        Args:
            value: PID 計算出的 PWM 百分比值
        """
        percent = value

        # --- Failsafe 保護 ---
        failsafe_curr = self._owner.get_failsafe_mode()

        # 偵測 failsafe 狀態轉換（進入或離開 failsafe）
        if self._failsafe_prev_state != failsafe_curr:
            self._failsafe_prev_state = failsafe_curr
            self._failsafe_transition = True

        if failsafe_curr:
            failsafe_pct = self._owner.get_failsafe_percent()
            # 確保 PWM 不低於 failsafe 百分比
            if percent < failsafe_pct:
                percent = failsafe_pct

        # 只在狀態轉換時印出訊息（避免刷屏）
        if self._failsafe_transition:
            self._failsafe_transition = False
            state_str = "進入 failsafe" if failsafe_curr else "回到正常"
            print(
                f"  [FanCtrl] Zone {self._owner.get_zone_id()} 風扇 "
                f"{state_str} 模式, PWM: {percent:.1f}%",
                file=sys.stderr,
            )

        # --- 寫入風扇 ---
        # PID 計算出的是百分比（例如 75 代表 75%），需要除以 100 變成 0.0~1.0
        percent_normalized = percent / 100.0

        for name in self._inputs:
            sensor = self._owner.get_sensor(name)
            raw_written = sensor.write(percent_normalized, force=self._owner.get_redundant_write())

            # 記錄輸出到快取（用於 logging）
            unscaled_written = float(raw_written) if raw_written is not None else 0.0
            from pid_control.conf import ValueCacheEntry
            self._owner.set_output_cache(
                sensor.get_name(),
                ValueCacheEntry(scaled=percent_normalized, unscaled=unscaled_written),
            )
