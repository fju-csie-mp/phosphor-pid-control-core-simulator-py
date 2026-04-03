"""
Stepwise 階梯控制器

對應 C++ 原始碼: pid/stepwisecontroller.hpp + pid/stepwisecontroller.cpp

StepwiseController 是 PID 控制的替代方案：
  - PID: 連續計算，輸出值平滑變化
  - Stepwise: 查表，輸出值是離散的（只有幾個固定級別）

適用場景：
  - 不需要精確連續控制的場合
  - 例如：溫度 < 30°C → 低速, 30~50°C → 中速, > 50°C → 高速

注意：StepwiseController 直接繼承 Controller（不是 PIDController），
因為它不需要 PID 的計算邏輯。
"""

from __future__ import annotations

import math
import sys
from typing import TYPE_CHECKING

from pid_control.controllers.controller import Controller
from pid_control.ec.stepwise import StepwiseInfo, stepwise

if TYPE_CHECKING:
    from pid_control.zone import Zone


class StepwiseController(Controller):
    """
    階梯控制器。

    對應 C++: pid_control::StepwiseController (pid/stepwisecontroller.hpp)

    與 PIDController 的差異：
      - 不使用 PID 數學，只用查表
      - 直接繼承 Controller，不經過 PIDController
      - 自己實作 process()，不是 Template Method

    Attributes:
        _stepwise_info: Stepwise 的設定資料（查表）
        _last_input: 上一次的輸入值（用於遲滯判斷）
        _last_output: 上一次的輸出值（遲滯區間內維持不變）
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
            inputs: 輸入感測器名稱清單
            owner: 所屬 Zone
        """
        super().__init__(controller_id, owner)
        self._inputs = inputs
        self._stepwise_info = StepwiseInfo()
        self._last_input: float = float("nan")
        self._last_output: float = float("nan")

    @staticmethod
    def create(
        owner: Zone,
        controller_id: str,
        inputs: list[str],
        stepwise_info: StepwiseInfo,
    ) -> StepwiseController:
        """
        工廠方法 — 建立 StepwiseController 實例。

        對應 C++: StepwiseController::createStepwiseController()
                  (stepwisecontroller.cpp:70-84)
        """
        if not inputs:
            raise ValueError("StepwiseController 至少需要一個輸入感測器")

        ctrl = StepwiseController(controller_id, inputs, owner)
        ctrl._stepwise_info = stepwise_info
        return ctrl

    def get_stepwise_info(self) -> StepwiseInfo:
        return self._stepwise_info

    def input_proc(self) -> float:
        """
        讀取所有感測器，取最大值。

        對應 C++: StepwiseController::inputProc() (stepwisecontroller.cpp:86-101)

        取最大值的邏輯：關注最熱的那個感測器。

        Returns:
            所有輸入感測器中的最大值
        """
        value = float("-inf")
        for name in self._inputs:
            value = max(value, self._owner.get_cached_value(name))
        return value

    def output_proc(self, value: float) -> None:
        """
        把查表結果加到 Zone 的 setpoint。

        對應 C++: StepwiseController::outputProc() (stepwisecontroller.cpp:103-118)

        如果 is_ceiling=True，結果作為 RPM 上限（而不是 setpoint）。

        Args:
            value: Stepwise 查表得到的輸出值
        """
        if self._stepwise_info.is_ceiling:
            # 作為 RPM 上限，用於限制風扇最大轉速
            self._owner.add_rpm_ceiling(value)
        else:
            # 作為 setpoint，會跟其他 controller 的 setpoint 一起比較
            self._owner.add_set_point(value, self._id)

    def process(self) -> None:
        """
        執行 Stepwise 控制計算。

        對應 C++: StepwiseController::process() (stepwisecontroller.cpp:37-68)

        流程：
          1. 讀取輸入值（取所有感測器的最大值）
          2. 檢查遲滯：如果變化量沒超過遲滯閾值，維持上次輸出
          3. 如果變化量超過遲滯，重新查表計算
          4. 輸出結果
        """
        # 步驟 1: 讀取輸入
        input_val = self.input_proc()

        info = self._stepwise_info
        output = self._last_output

        # 步驟 2: 遲滯判斷
        if math.isnan(output):
            # 第一次執行，沒有上次輸出，直接查表
            output = stepwise(info, input_val)
            self._last_input = input_val
        elif (input_val - self._last_input) > info.positive_hysteresis:
            # 溫度上升超過正向遲滯 → 重新查表
            output = stepwise(info, input_val)
            self._last_input = input_val
        elif (self._last_input - input_val) > info.negative_hysteresis:
            # 溫度下降超過負向遲滯 → 重新查表
            output = stepwise(info, input_val)
            self._last_input = input_val
        # else: 在遲滯區間內，output 維持上次的值不變

        self._last_output = output

        # 步驟 3: 輸出
        self.output_proc(output)
