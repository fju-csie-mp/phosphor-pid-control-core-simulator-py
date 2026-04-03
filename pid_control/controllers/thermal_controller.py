"""
溫度控制器

對應 C++ 原始碼: pid/thermalcontroller.hpp + pid/thermalcontroller.cpp

ThermalController 負責：
  1. 讀取溫度感測器的值（inputProc）
  2. 回傳自己的設定點（setptProc）
  3. 用 PID 計算出「需要多少 RPM」（process → calPIDOutput）
  4. 把算出的 RPM 目標值加到 Zone 的 setpoint 清單中（outputProc）

在整個控制迴圈中的位置：
  讀取溫度 → Thermal PID 算出目標 RPM → 交給 Fan PID → Fan PID 算出 PWM

Thermal PID 執行頻率較低（每 1 秒一次），因為溫度變化比較慢。
"""

from __future__ import annotations

import math
import sys
from typing import TYPE_CHECKING

from pid_control.conf import SensorInput, ThermalType, get_thermal_type
from pid_control.controllers.pid_controller import PIDController
from pid_control.ec.pid import PidConfig, PidInfo, initialize_pid_info

if TYPE_CHECKING:
    from pid_control.zone import Zone


class ThermalController(PIDController):
    """
    溫度 PID 控制器。

    對應 C++: pid_control::ThermalController (pid/thermalcontroller.hpp)

    三種計算模式（由 ThermalType 決定）：
      - MARGIN: 讀多個感測器 → 取最小值（最接近上限的那個）
      - ABSOLUTE: 讀多個感測器 → 取最大值（溫度最高的那個）
      - SUMMATION: 讀多個感測器 → 全部加總（用於功率計算）
    """

    def __init__(
        self,
        controller_id: str,
        inputs: list[SensorInput],
        thermal_type: ThermalType,
        owner: Zone,
    ):
        """
        Args:
            controller_id: 控制器名稱
            inputs: 輸入感測器清單（帶有額外裝飾資訊）
            thermal_type: 計算類型（MARGIN / ABSOLUTE / SUMMATION）
            owner: 所屬 Zone
        """
        super().__init__(controller_id, owner)
        self._inputs = inputs
        self._type = thermal_type

    @staticmethod
    def create(
        owner: Zone,
        controller_id: str,
        inputs: list[SensorInput],
        setpoint: float,
        pid_config: PidConfig,
        thermal_type: ThermalType,
    ) -> ThermalController:
        """
        工廠方法 — 建立 ThermalController 實例。

        對應 C++: ThermalController::createThermalPid() (thermalcontroller.cpp:50-69)
        """
        if not inputs:
            raise ValueError("ThermalController 至少需要一個輸入感測器")

        thermal = ThermalController(
            controller_id, inputs, thermal_type, owner
        )
        thermal.set_setpoint(setpoint)
        initialize_pid_info(thermal.get_pid_info(), pid_config)
        return thermal

    def input_proc(self) -> float:
        """
        讀取溫度感測器值，依照 ThermalType 進行彙總。

        對應 C++: ThermalController::inputProc() (thermalcontroller.cpp:72-171)

        三種彙總策略：
          - MARGIN: 取最小值
            「margin」= 離安全上限還有多遠，margin 越小越危險
            取最小 margin 等於「關注最危險的那個感測器」

          - ABSOLUTE: 取最大值
            取最高溫度，確保最熱的部件被照顧到

          - SUMMATION: 加總
            用於功率感測器，把所有功耗加起來

        Returns:
            彙總後的溫度/margin/功率值
        """
        if self._type == ThermalType.MARGIN:
            # Margin 模式：取最小值（最接近上限 = 最危險的）
            value = float("inf")  # 初始值設為正無窮大，任何值都比它小
            compare = min
        elif self._type == ThermalType.ABSOLUTE:
            # 絕對溫度模式：取最大值（最高溫的）
            value = float("-inf")  # 初始值設為負無窮大，任何值都比它大
            compare = max
        elif self._type == ThermalType.SUMMATION:
            # 加總模式
            value = 0.0
            compare = None  # 不用比較函數，直接加
        else:
            raise ValueError(f"無法識別的 ThermalType: {self._type}")

        acceptable = False  # 是否至少有一個有效的感測器值

        for sensor_input in self._inputs:
            cached_value = self._owner.get_cached_value(sensor_input.name)

            # 跳過無效值（NaN 或 inf）
            if not math.isfinite(cached_value):
                continue

            # --- TempToMargin 轉換 ---
            # 有些感測器提供的是「絕對溫度」，但控制器需要的是「margin」
            # margin = Tjmax - 溫度
            # 例如 CPU 的 Tjmax=100°C，目前 80°C → margin = 20°C
            if self._type == ThermalType.MARGIN:
                if sensor_input.convert_temp_to_margin:
                    if not math.isfinite(sensor_input.convert_margin_zero):
                        raise ValueError("TempToMargin 轉換的 Tjmax 無效")
                    margin_value = sensor_input.convert_margin_zero - cached_value
                    cached_value = margin_value

            # --- 彙總 ---
            if self._type == ThermalType.SUMMATION:
                value += cached_value
            else:
                value = compare(value, cached_value)

            acceptable = True

        if not acceptable:
            # 如果所有感測器都無效，用 setpoint 作為 input
            # 這樣 PID 的 error = 0，輸出不變（安全行為）
            value = self.setpt_proc()

        return value

    def setpt_proc(self) -> float:
        """
        回傳目標設定點。

        對應 C++: ThermalController::setptProc() (thermalcontroller.cpp:174-177)

        ThermalController 的 setpoint 是在配置檔中靜態設定的。
        例如「CPU 溫度不要超過 80°C」→ setpoint = 80
        """
        return self.get_setpoint()

    def output_proc(self, value: float) -> None:
        """
        把計算出的 RPM 設定點加到 Zone。

        對應 C++: ThermalController::outputProc() (thermalcontroller.cpp:180-191)

        多個 ThermalController 的輸出會被 Zone 收集起來，
        最後 Zone 會選出最大的 setpoint（最需要散熱的那個）給 Fan PID 使用。

        Args:
            value: PID 計算出的目標 RPM 值
        """
        self._owner.add_set_point(value, self._id)
