"""
PID 控制器基底類別

對應 C++ 原始碼: pid/pidcontroller.hpp + pid/pidcontroller.cpp

PIDController 是 FanController 和 ThermalController 的共同基底。
它實作了 **Template Method Pattern**：

  process() 方法定義了固定的執行骨架：
    1. setpt_proc()  → 取得設定點（子類別實作）
    2. input_proc()  → 取得輸入值（子類別實作）
    3. cal_pid_output() → 計算 PID 輸出（本類別實作）
    4. output_proc() → 輸出結果（子類別實作）

  子類別只需要覆寫 setpt_proc / input_proc / output_proc，
  不需要管 PID 的計算邏輯。
"""

from __future__ import annotations

import math
from abc import abstractmethod
from typing import TYPE_CHECKING

from pid_control.controllers.controller import Controller
from pid_control.ec.pid import PidConfig, PidInfo, initialize_pid_info, pid

if TYPE_CHECKING:
    from pid_control.zone import Zone


class PIDController(Controller):
    """
    PID 控制器基底類別。

    對應 C++: pid_control::PIDController (pid/pidcontroller.hpp)

    使用 Template Method Pattern:
      - process() 定義骨架（不可覆寫的流程）
      - setpt_proc() / input_proc() / output_proc() 是可覆寫的步驟

    Attributes:
        _pid_info: PID 的完整狀態（包含運行中的積分值等）
        _setpoint: 當前的目標設定點
        _last_input: 上一次的輸入值（用於遲滯判斷）
    """

    def __init__(self, controller_id: str, owner: Zone):
        super().__init__(controller_id, owner)
        self._pid_info = PidInfo()
        self._setpoint: float = 0.0
        self._last_input: float = float("nan")

    @abstractmethod
    def setpt_proc(self) -> float:
        """
        取得設定點值（目標值）。

        對應 C++: setptProc()

        - FanController: 從 Zone 取得最大 RPM setpoint
        - ThermalController: 回傳自己的 setpoint（從配置檔來）

        Returns:
            設定點值
        """
        ...

    def get_pid_info(self) -> PidInfo:
        """取得 PID 狀態物件（可用來檢查或修改 PID 參數）"""
        return self._pid_info

    def get_setpoint(self) -> float:
        return self._setpoint

    def set_setpoint(self, setpoint: float) -> None:
        self._setpoint = setpoint

    def get_last_input(self) -> float:
        return self._last_input

    def cal_pid_output(
        self, setpt: float, input_val: float, info: PidInfo
    ) -> float:
        """
        計算 PID 輸出，包含遲滯（hysteresis）邏輯。

        對應 C++: PIDController::calPIDOutput() (pidcontroller.cpp:13-86)

        遲滯的目的：避免在邊界值附近頻繁開關（抖動）。
        想像一下冷氣的恆溫器：
          - 設定 25°C，如果沒有遲滯，溫度在 24.9↔25.1 之間跳動時，
            冷氣會不斷開關
          - 有遲滯的話，例如 ±1°C，必須超過 26°C 才開機，低於 24°C 才關機
          - 在 24~26°C 之間維持上一次的狀態，不做改變

        這裡有兩種遲滯模式：
          1. check_hyster_with_setpt=True: 用 setpoint 作為遲滯的中心
          2. check_hyster_with_setpt=False: 用上次 input 作為遲滯的中心

        Args:
            setpt: 目標設定點
            input_val: 當前輸入值
            info: PID 狀態

        Returns:
            PID 計算出的輸出值
        """
        if info.check_hyster_with_setpt:
            # === 模式 1: 以 setpoint 為中心的遲滯 ===
            if input_val > (setpt + info.positive_hysteresis):
                # 輸入超過 setpoint + 正向遲滯 → 正常 PID 計算
                output = pid(info, input_val, setpt)
                self._last_input = input_val
            elif input_val < (setpt - info.negative_hysteresis):
                # 輸入低於 setpoint - 負向遲滯 → 重置 PID，輸出 0
                self._last_input = setpt
                info.integral = 0
                output = 0.0
            else:
                # 在遲滯區間內 → 維持上次輸出，不做改變
                self._last_input = input_val
                output = info.last_output
            info.last_output = output
        else:
            # === 模式 2: 以上次 input 為中心的遲滯 ===
            if info.positive_hysteresis == 0 and info.negative_hysteresis == 0:
                # 沒有遲滯設定 → 直接計算 PID
                output = pid(info, input_val, setpt)
                self._last_input = input_val
            else:
                # 有遲滯設定
                if not math.isfinite(self._last_input):
                    # 第一次執行，初始化 last_input
                    self._last_input = input_val
                elif (input_val - self._last_input) > info.positive_hysteresis:
                    # 上升幅度超過正向遲滯 → 更新 input
                    self._last_input = input_val
                elif (self._last_input - input_val) > info.negative_hysteresis:
                    # 下降幅度超過負向遲滯 → 更新 input
                    self._last_input = input_val
                # 用 last_input（可能沒更新）做 PID 計算
                # 這樣在遲滯區間內，PID 看到的 input 不會變，輸出也不會變
                output = pid(info, self._last_input, setpt)

        return output

    def process(self) -> None:
        """
        執行完整的 PID 控制流程。

        對應 C++: PIDController::process() (pidcontroller.cpp:88-111)

        這是 **Template Method Pattern** 的核心：
          固定的骨架流程，子類別只需實作個別步驟。

        流程:
          1. setpt_proc() → 取得目標值 (由子類別決定怎麼取)
          2. input_proc()  → 取得輸入值 (由子類別決定怎麼讀)
          3. calPIDOutput() → 用 PID 數學算出輸出
          4. output_proc()  → 把結果輸出 (由子類別決定送去哪)
        """
        # 步驟 1: 取得設定點
        setpt = self.setpt_proc()

        # 步驟 2: 取得輸入值
        input_val = self.input_proc()

        # 步驟 3: PID 計算
        info = self.get_pid_info()
        output = self.cal_pid_output(setpt, input_val, info)
        info.last_output = output

        # 步驟 4: 輸出結果
        self.output_proc(output)
