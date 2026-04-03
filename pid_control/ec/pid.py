"""
PID 核心數學運算模組

對應 C++ 原始碼: pid/ec/pid.hpp + pid/ec/pid.cpp

這個模組實作了 PID (Proportional-Integral-Derivative) 控制演算法。
PID 是工業控制中最常見的回饋控制方法：
  - P (比例): 根據「目前的誤差」調整輸出，誤差越大調整越多
  - I (積分): 根據「過去累積的誤差」調整輸出，解決穩態誤差
  - D (微分): 根據「誤差的變化速度」調整輸出，預測趨勢、減少超調

在風扇控制的場景中：
  - 輸入 (input): 感測器的讀數（溫度、風扇轉速等）
  - 設定點 (setpoint): 我們希望達到的目標值
  - 輸出 (output): 控制信號（例如風扇的 PWM 佔空比或目標轉速）
"""

from dataclasses import dataclass, field


@dataclass
class Limits:
    """
    上下限範圍，用來限制（clamp）某個數值不超出合理範圍。

    對應 C++: ec::limits_t
    """
    min: float = 0.0
    max: float = 0.0


@dataclass
class PidInfo:
    """
    PID 控制器的完整狀態，包含所有參數和運行時的中間變數。

    對應 C++: ec::pid_info_t

    分成兩類欄位：
    1. 設定參數（由 JSON 配置檔決定，初始化後通常不變）
    2. 運行狀態（每次計算都會更新）
    """

    # === 運行狀態 ===
    initialized: bool = False
    """PID 是否已經初始化（第一次執行後設為 True）"""

    integral: float = 0.0
    """積分項的累積值（I 項的記憶）"""

    last_output: float = 0.0
    """上一次的輸出值（用於 slew rate 限制）"""

    last_error: float = 0.0
    """上一次的誤差值（用於 D 項計算）"""

    # === PID 係數設定 ===
    ts: float = 0.0
    """取樣時間（秒），每次控制迴圈的間隔。例如 0.1 表示每 0.1 秒算一次"""

    proportional_coeff: float = 0.0
    """P 項係數 (Kp)：越大代表對誤差的反應越強烈"""

    integral_coeff: float = 0.0
    """I 項係數 (Ki)：越大代表累積誤差的修正越快"""

    derivative_coeff: float = 0.0
    """D 項係數 (Kd)：越大代表對誤差變化的反應越敏感"""

    feed_fwd_offset: float = 0.0
    """前饋偏移量：在 PID 輸出上額外加的常數偏移"""

    feed_fwd_gain: float = 0.0
    """前饋增益：將 setpoint 乘以此增益後加到輸出上，用於加速響應"""

    # === 限制設定 ===
    integral_limit: Limits = field(default_factory=Limits)
    """積分項的上下限，防止積分飽和（integral windup）"""

    out_lim: Limits = field(default_factory=Limits)
    """最終輸出的上下限"""

    slew_neg: float = 0.0
    """負向 slew rate（每秒最大允許的下降量），0 表示不限制"""

    slew_pos: float = 0.0
    """正向 slew rate（每秒最大允許的上升量），0 表示不限制"""

    # === 遲滯設定 ===
    check_hyster_with_setpt: bool = False
    """是否用 setpoint 來判斷遲滯（而不是用上次 input 來判斷）"""

    positive_hysteresis: float = 0.0
    """正向遲滯量：input 必須超過上次值加上這個量才算「有變化」"""

    negative_hysteresis: float = 0.0
    """負向遲滯量：input 必須低於上次值減去這個量才算「有變化」"""


@dataclass
class PidConfig:
    """
    PID 的配置參數（精簡版），用於從 JSON 設定檔讀入後傳給控制器。

    對應 C++: ec::pidinfo

    跟 PidInfo 的差別：這個只有「設定參數」，沒有「運行狀態」。
    建立控制器時，會用 PidConfig 來初始化 PidInfo。
    """
    check_hyster_with_setpt: bool = False
    ts: float = 0.0
    proportional_coeff: float = 0.0
    integral_coeff: float = 0.0
    derivative_coeff: float = 0.0
    feed_fwd_offset: float = 0.0
    feed_fwd_gain: float = 0.0
    integral_limit: Limits = field(default_factory=Limits)
    out_lim: Limits = field(default_factory=Limits)
    slew_neg: float = 0.0
    slew_pos: float = 0.0
    positive_hysteresis: float = 0.0
    negative_hysteresis: float = 0.0


def initialize_pid_info(info: PidInfo, config: PidConfig) -> None:
    """
    用配置參數初始化 PID 運行狀態。

    對應 C++: initializePIDStruct() (pid/util.cpp)

    Args:
        info: 要被初始化的 PidInfo（會被修改）
        config: 設定參數來源
    """
    info.check_hyster_with_setpt = config.check_hyster_with_setpt
    info.ts = config.ts
    info.proportional_coeff = config.proportional_coeff
    info.integral_coeff = config.integral_coeff
    info.derivative_coeff = config.derivative_coeff
    info.feed_fwd_offset = config.feed_fwd_offset
    info.feed_fwd_gain = config.feed_fwd_gain
    info.integral_limit = Limits(config.integral_limit.min,
                                 config.integral_limit.max)
    info.out_lim = Limits(config.out_lim.min, config.out_lim.max)
    info.slew_neg = config.slew_neg
    info.slew_pos = config.slew_pos
    info.negative_hysteresis = config.negative_hysteresis
    info.positive_hysteresis = config.positive_hysteresis


def _clamp(x: float, min_val: float, max_val: float) -> float:
    """
    將數值限制在 [min_val, max_val] 範圍內。

    例如: _clamp(150, 0, 100) → 100
          _clamp(-10, 0, 100) → 0
          _clamp(50, 0, 100)  → 50
    """
    if x < min_val:
        return min_val
    if x > max_val:
        return max_val
    return x


def pid(info: PidInfo, input_val: float, setpoint: float) -> float:
    """
    執行一次 PID 計算，回傳控制輸出值。

    對應 C++: ec::pid() (pid/ec/pid.cpp)

    這是整個系統最核心的函數。每次控制迴圈都會呼叫它一次。

    計算流程:
      1. error = setpoint - input（目標值減去實際值）
      2. P 項 = Kp * error
      3. I 項 = 上次累積值 + Ki * error * ts（取樣時間）
      4. D 項 = Kd * (error - 上次error) / ts
      5. FF 項 = (setpoint + offset) * gain（前饋項）
      6. output = P + I + D + FF
      7. 套用輸出上下限 (clamp)
      8. 套用 slew rate 限制（不能升太快/降太快）
      9. 反算積分項（避免積分飽和）

    Args:
        info: PID 狀態（會被修改，因為要記住上次的誤差、積分等）
        input_val: 感測器讀到的當前值
        setpoint: 目標值

    Returns:
        計算出的控制輸出值
    """
    # ---- 步驟 1: 計算誤差 ----
    # 誤差 = 目標值 - 實際值
    # 正的誤差表示實際值低於目標（需要加大輸出）
    # 負的誤差表示實際值高於目標（需要減小輸出）
    error = setpoint - input_val

    # ---- 步驟 2: P 項（比例項）----
    # 直接乘上比例係數，誤差越大輸出越大
    proportional_term = info.proportional_coeff * error

    # ---- 步驟 3: I 項（積分項）----
    # 把歷史誤差累積起來，解決 P 項無法消除的穩態誤差
    # 公式: I(t) = I(t-1) + Ki * error * dt
    integral_term = 0.0
    if info.integral_coeff != 0.0:
        integral_term = info.integral  # 拿上次的累積值
        integral_term += error * info.integral_coeff * info.ts  # 加上本次的貢獻
        # 限制積分值的範圍，防止「積分飽和」
        # （積分飽和 = 積分累積太大，導致系統反應遲鈍）
        integral_term = _clamp(integral_term,
                               info.integral_limit.min,
                               info.integral_limit.max)

    # ---- 步驟 4: D 項（微分項）----
    # 根據誤差的「變化速度」來調整
    # 如果誤差正在快速增大 → 提前加大輸出（預測性）
    # 如果誤差正在快速減小 → 提前減小輸出（避免超調）
    derivative_term = info.derivative_coeff * (
        (error - info.last_error) / info.ts
    )

    # ---- 步驟 5: FF 項（前饋項）----
    # 直接根據目標值來加一個額外的偏移，加速系統響應
    # 例如目標溫度越高，前饋就越大，讓風扇提前加速
    feed_fwd_term = (setpoint + info.feed_fwd_offset) * info.feed_fwd_gain

    # ---- 步驟 6: 加總所有項 ----
    output = proportional_term + integral_term + derivative_term + feed_fwd_term

    # ---- 步驟 7: 限制輸出範圍 ----
    output = _clamp(output, info.out_lim.min, info.out_lim.max)

    # ---- 步驟 8: Slew Rate 限制 ----
    # 避免輸出值變化太快（例如風扇轉速不能瞬間從 0 跳到 100%）
    # slew_neg: 每秒最多下降多少（負數）
    # slew_pos: 每秒最多上升多少（正數）
    if info.initialized:
        if info.slew_neg != 0.0:
            # 計算本次允許的最小輸出（不能降太快）
            min_out = info.last_output + info.slew_neg * info.ts
            if output < min_out:
                output = min_out

        if info.slew_pos != 0.0:
            # 計算本次允許的最大輸出（不能升太快）
            max_out = info.last_output + info.slew_pos * info.ts
            if output > max_out:
                output = max_out

        # ---- 步驟 9: 反算積分項 ----
        # 因為 slew rate 限制可能改變了 output，
        # 需要反算積分項，避免積分項和實際輸出不一致
        if info.slew_neg != 0.0 or info.slew_pos != 0.0:
            integral_term = output - proportional_term

    # 再次 clamp 積分項（因為 slew rate 反算可能讓它超出範圍）
    integral_term = _clamp(integral_term,
                           info.integral_limit.min,
                           info.integral_limit.max)

    # ---- 更新狀態（為下一次計算做準備）----
    info.integral = integral_term
    info.initialized = True
    info.last_error = error
    info.last_output = output

    return output
