"""
Stepwise 階梯控制演算法

對應 C++ 原始碼: pid/ec/stepwise.hpp + pid/ec/stepwise.cpp

Stepwise 是一種比 PID 更簡單的控制方式：
  - 不做任何數學計算（沒有 P、I、D）
  - 而是用一張「查表」來決定輸出
  - 給定一個輸入值，在表中找到對應的區間，直接輸出該區間的值

舉例：溫度 → 風扇轉速的對照表
  溫度 < 30°C → 風扇 20%
  溫度 30~40°C → 風扇 40%
  溫度 40~50°C → 風扇 60%
  溫度 > 50°C → 風扇 80%

適合用在不需要精確控制、只需要分段反應的場景。
"""

import math
from dataclasses import dataclass, field

# 最大支援的階梯點數（與 C++ 版本一致）
MAX_STEPWISE_POINTS = 20


@dataclass
class StepwiseInfo:
    """
    Stepwise 控制的設定資料。

    對應 C++: ec::StepwiseInfo

    reading[] 和 output[] 是一對一對應的陣列：
      - reading[i] 是閾值（例如溫度）
      - output[i] 是對應的輸出值（例如風扇轉速百分比）

    規則：
      - reading[] 必須遞增排列
      - 如果 input < reading[0]，輸出 output[0]
      - 如果 input >= reading[i]，輸出 output[i]
      - reading[i] 為 NaN 表示該點之後不再使用

    Attributes:
        ts: 取樣時間（秒），與 PID 的 ts 概念一樣
        reading: 輸入閾值陣列（溫度門檻值）
        output: 對應的輸出值陣列（風扇輸出）
        positive_hysteresis: 正向遲滯量（輸入值上升時的濾波）
        negative_hysteresis: 負向遲滯量（輸入值下降時的濾波）
        is_ceiling: 如果為 True，輸出作為 RPM 上限；否則作為 setpoint
    """
    ts: float = 0.0
    reading: list[float] = field(
        default_factory=lambda: [float("nan")] * MAX_STEPWISE_POINTS
    )
    output: list[float] = field(
        default_factory=lambda: [float("nan")] * MAX_STEPWISE_POINTS
    )
    positive_hysteresis: float = 0.0
    negative_hysteresis: float = 0.0
    is_ceiling: bool = False


def stepwise(info: StepwiseInfo, input_val: float) -> float:
    """
    執行一次 Stepwise 查表計算。

    對應 C++: ec::stepwise() (pid/ec/stepwise.cpp)

    演算法非常簡單：
      1. 預設輸出 = output[0]（最低級）
      2. 從 reading[1] 開始往後掃
      3. 如果 reading[i] > input，停止（找到區間了）
      4. 如果 reading[i] 是 NaN，停止（表結束了）
      5. 否則更新輸出為 output[i]

    Args:
        info: Stepwise 的設定資料（查表）
        input_val: 當前的輸入值（例如溫度）

    Returns:
        查表得到的輸出值
    """
    # 預設取第一個輸出值（如果 input 比所有 reading 都低）
    value = info.output[0]

    for i in range(1, MAX_STEPWISE_POINTS):
        # 遇到 NaN 表示表已經結束，不再往後看
        if math.isnan(info.reading[i]):
            break
        # 如果這個閾值已經大於 input，代表上一個就是答案，停止
        if info.reading[i] > input_val:
            break
        # input 超過了 reading[i]，所以輸出值升級到 output[i]
        value = info.output[i]

    return value
