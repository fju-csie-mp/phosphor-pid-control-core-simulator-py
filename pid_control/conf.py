"""
配置資料結構定義

對應 C++ 原始碼: conf.hpp + interfaces.hpp

這個模組定義了系統中所有的設定資料結構。
整個系統的運作流程是：
  JSON 設定檔 → 解析成這些 dataclass → 傳給 builder 去建立實際物件

這些結構只負責「攜帶資料」，不包含任何邏輯。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pid_control.ec.pid import PidConfig
from pid_control.ec.stepwise import StepwiseInfo


# =============================================================================
# 介面定義 (對應 C++ interfaces.hpp)
# =============================================================================
# Python 用 Protocol 來定義介面（類似 C++ 的純虛擬類別 / Java 的 interface）
# 任何類別只要實作了這些方法，就算是「符合介面」，不需要明確繼承


@dataclass
class ReadReturn:
    """
    感測器讀取的回傳值。

    對應 C++: ReadReturn (interfaces.hpp)

    Attributes:
        value: 讀到的數值（例如溫度 45.5°C 或風扇轉速 3000 RPM）
        updated: 最後更新的時間戳記
        unscaled: 未經縮放的原始值（有些感測器會做 0~1 的正規化，
                  這裡保留原始值方便 debug）
    """
    value: float = float("nan")
    updated: datetime = field(default_factory=datetime.now)
    unscaled: float = float("nan")

    def __post_init__(self):
        # 如果 unscaled 沒有特別指定，就跟 value 一樣
        if math.isnan(self.unscaled) and not math.isnan(self.value):
            self.unscaled = self.value


@dataclass
class ValueCacheEntry:
    """
    快取中存放的感測器值，同時保留縮放後和原始值。

    對應 C++: ValueCacheEntry (interfaces.hpp)

    Attributes:
        scaled: 正規化到 (0.0, 1.0) 範圍的值（用於 PWM 輸出時）
        unscaled: 原始值（例如實際的 RPM 數字）
    """
    scaled: float = 0.0
    unscaled: float = 0.0


@runtime_checkable
class ReadInterface(Protocol):
    """
    感測器讀取介面 — 任何能「讀取數值」的東西都要實作這個。

    對應 C++: ReadInterface (interfaces.hpp)

    C++ 原始碼中有多種實作：
      - DbusPassive: 從 D-Bus 讀取（OpenBMC 專用）
      - SysFsRead: 從 Linux sysfs 檔案讀取
    我們的模擬版會用 SimulatedSensor 來實作。
    """
    def read(self) -> ReadReturn:
        """讀取當前感測器值"""
        ...

    def get_failed(self) -> bool:
        """回傳此感測器是否已經故障"""
        ...

    def get_fail_reason(self) -> str:
        """回傳故障原因的描述文字"""
        ...


@runtime_checkable
class WriteInterface(Protocol):
    """
    感測器寫入介面 — 任何能「寫入控制值」的東西都要實作這個。

    對應 C++: WriteInterface (interfaces.hpp)

    C++ 原始碼中的實作：
      - SysFsWrite: 寫入 Linux sysfs（控制實際風扇 PWM）
      - DbusWrite: 透過 D-Bus 寫入
    我們的模擬版會用 SimulatedFan 來實作。
    """
    def write(self, value: float, force: bool = False) -> int | None:
        """
        寫入控制值。

        Args:
            value: 要寫入的值（通常是 0.0~1.0 的 PWM 百分比）
            force: 是否強制寫入（即使值沒有變化）

        Returns:
            實際寫入的原始值（可選）
        """
        ...

    def get_min(self) -> int:
        """回傳寫入值的最小限制"""
        ...

    def get_max(self) -> int:
        """回傳寫入值的最大限制"""
        ...


# =============================================================================
# 配置資料結構 (對應 C++ conf.hpp)
# =============================================================================


@dataclass
class SensorConfig:
    """
    單一感測器的設定。

    對應 C++: conf::SensorConfig

    Attributes:
        type: 感測器類型（"fan" = 風扇, "temp" = 溫度, "margin" = 溫度裕度）
        read_path: 讀取路徑（在模擬中不使用，但保留結構完整性）
        write_path: 寫入路徑
        min: 最小值
        max: 最大值
        timeout: 超時秒數（超過這個時間沒更新就視為故障）
    """
    type: str = ""
    read_path: str = ""
    write_path: str = ""
    min: int = 0
    max: int = 0
    timeout: int = 0


@dataclass
class SensorInput:
    """
    控制器配置中，對一個輸入感測器的額外裝飾資訊。

    對應 C++: conf::SensorInput

    這些資訊來自 PID 控制器的設定，而不是感測器本身的設定。
    用途是讓同一個感測器在不同控制器中可以有不同的處理方式。

    Attributes:
        name: 感測器的名稱（用來在快取中查找）
        convert_margin_zero: TempToMargin 轉換的零點（Tjmax 值）
        convert_temp_to_margin: 是否要把溫度轉換成 margin
                                （margin = Tjmax - 溫度，代表離上限還有多遠）
        missing_is_acceptable: 如果這個感測器遺失，是否可以忽略（不觸發 failsafe）
    """
    name: str = ""
    convert_margin_zero: float = float("nan")
    convert_temp_to_margin: bool = False
    missing_is_acceptable: bool = False


class ThermalType(Enum):
    """
    溫度控制器的計算類型。

    對應 C++: ThermalType (thermalcontroller.hpp)

    不同類型決定了多個感測器值如何彙總成一個代表值：
      - MARGIN: 取最小值（最接近上限的那個感測器）
      - ABSOLUTE: 取最大值（溫度最高的那個感測器）
      - SUMMATION: 加總（用於功率累加的場景）
    """
    MARGIN = "margin"
    ABSOLUTE = "absolute"
    SUMMATION = "summation"


def get_thermal_type(type_string: str) -> ThermalType:
    """
    把設定檔中的字串轉成 ThermalType 列舉。

    對應 C++: getThermalType() (thermalcontroller.cpp)

    Args:
        type_string: "margin", "temp", "power", 或 "powersum"

    Returns:
        對應的 ThermalType
    """
    if type_string == "margin":
        return ThermalType.MARGIN
    if type_string in ("temp", "power"):
        return ThermalType.ABSOLUTE
    if type_string == "powersum":
        return ThermalType.SUMMATION
    raise ValueError(f"無法識別的 thermal 類型: {type_string}")


def is_thermal_type(type_string: str) -> bool:
    """判斷字串是否為合法的 thermal 類型"""
    return type_string in ("temp", "margin", "power", "powersum")


@dataclass
class ControllerInfo:
    """
    單一控制器（PID 或 Stepwise）的設定。

    對應 C++: conf::ControllerInfo

    Attributes:
        type: 控制器類型 ("fan", "temp", "margin", "power", "powersum", "stepwise")
        inputs: 此控制器使用的輸入感測器清單
        setpoint: 初始設定點（目標值）
        pid_info: PID 參數（如果是 PID 類型的控制器）
        stepwise_info: Stepwise 參數（如果是 Stepwise 類型的控制器）
        failsafe_percent: 這個控制器的 failsafe PWM 百分比
    """
    type: str = ""
    inputs: list[SensorInput] = field(default_factory=list)
    setpoint: float = 0.0
    pid_info: PidConfig = field(default_factory=PidConfig)
    stepwise_info: StepwiseInfo = field(default_factory=StepwiseInfo)
    failsafe_percent: float = 0.0


@dataclass
class CycleTime:
    """
    控制迴圈的時間設定。

    對應 C++: conf::CycleTime

    Attributes:
        cycle_interval_ms: 每次迴圈的間隔（毫秒），預設 100ms = 0.1 秒
                           → Fan PID 每 0.1 秒執行一次
        update_thermals_ms: 溫度更新的間隔（毫秒），預設 1000ms = 1 秒
                            → Thermal PID 每 1 秒執行一次
    """
    cycle_interval_ms: int = 100
    update_thermals_ms: int = 1000


@dataclass
class ZoneConfig:
    """
    一個控制區域（Zone）的設定。

    對應 C++: conf::ZoneConfig

    一個 Zone 代表一組獨立控制的風扇和感測器。
    例如一台伺服器可能有兩個 zone：
      - Zone 0: 前方風扇，負責 CPU 散熱
      - Zone 1: 後方風扇，負責 PCIe 散熱

    Attributes:
        min_thermal_output: 最低溫度輸出設定點（RPM），
                            即使溫度很低也不會讓風扇低於這個值
        failsafe_percent: failsafe 模式下的風扇 PWM 百分比
        cycle_time: 迴圈時間設定
        accumulate_set_point: 是否累加不同控制器的輸出
    """
    min_thermal_output: float = 0.0
    failsafe_percent: float = 0.0
    cycle_time: CycleTime = field(default_factory=CycleTime)
    accumulate_set_point: bool = False


# 整個 Zone 的 PID 設定，key = 控制器名稱, value = 控制器資訊
PIDConf = dict[str, ControllerInfo]
