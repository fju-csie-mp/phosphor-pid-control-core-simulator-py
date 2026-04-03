"""
控制器基底類別

對應 C++ 原始碼: pid/controller.hpp

Controller 是所有控制器的最上層抽象。
它定義了三個核心步驟：
  1. inputProc() — 讀取輸入（從感測器快取中取值）
  2. process()   — 執行控制計算（PID 或 Stepwise）
  3. outputProc() — 寫出結果（設定風扇 PWM 或提交 setpoint）

不同的控制器子類別會覆寫這三個方法來實現不同的行為。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

# TYPE_CHECKING 用來避免循環 import（只在型別檢查時 import）
if TYPE_CHECKING:
    from pid_control.zone import Zone


class Controller(ABC):
    """
    控制器抽象基底類別。

    對應 C++: pid_control::Controller (pid/controller.hpp)

    所有控制器（FanController, ThermalController, StepwiseController）
    都必須繼承這個類別並實作以下三個方法。

    在 Design Pattern 中，這是 **Strategy Pattern** 的介面角色：
      - 定義了統一的「process()」介面
      - 不同的子類別提供不同的演算法實作
      - Zone 持有一組 Controller，統一呼叫 process()
    """

    def __init__(self, controller_id: str, owner: Zone):
        """
        Args:
            controller_id: 控制器的唯一名稱（例如 "fan_pid_0", "thermal_cpu"）
            owner: 擁有此控制器的 Zone（控制器需要從 Zone 讀取快取值）
        """
        self._id = controller_id
        self._owner = owner

    @abstractmethod
    def input_proc(self) -> float:
        """
        讀取輸入值。

        子類別實作此方法來決定「從哪裡讀、怎麼彙總」：
          - FanController: 讀取所有風扇的 RPM，取最小值
          - ThermalController: 讀取所有溫度感測器，依類型取最小/最大/加總
          - StepwiseController: 讀取所有感測器，取最大值

        Returns:
            彙總後的輸入值
        """
        ...

    @abstractmethod
    def output_proc(self, value: float) -> None:
        """
        輸出計算結果。

        子類別實作此方法來決定「把結果送去哪裡」：
          - FanController: 把 PWM 寫入每個風扇
          - ThermalController: 把目標 RPM 加到 Zone 的 setpoint 列表
          - StepwiseController: 把值加到 setpoint 或設為 RPM 上限

        Args:
            value: 控制計算得出的輸出值
        """
        ...

    @abstractmethod
    def process(self) -> None:
        """
        執行完整的控制計算流程。

        整合 input_proc → 計算 → output_proc 的完整流程。
        PIDController 中，這是 **Template Method Pattern**。
        """
        ...

    def get_id(self) -> str:
        """取得控制器名稱"""
        return self._id
