# 術語表 (Glossary)

本文件定義 PID 風扇控制系統中的專有名詞，作為 BDD 測試與系統文件的共通語言。

## 系統架構

| 術語 | 英文 | 定義 |
|------|------|------|
| Zone | Zone | 一組獨立控制的風扇與感測器。每個 Zone 各自運行控制迴圈，互不干擾。例如前方風扇負責 CPU 散熱、後方風扇負責 PCIe 散熱，可以分成兩個 Zone。 |
| 控制迴圈 | Control Loop | Zone 週期性執行的循環流程：讀取感測器 → 計算目標轉速 → 調整風扇 PWM。Fan 迴圈每 0.1 秒一次，Thermal 迴圈每 1 秒一次。 |
| 感測器 | Sensor | 提供讀數的裝置。溫度感測器回報溫度（°C），風扇感測器回報轉速（RPM）。 |
| 風扇 | Fan | 被控制的散熱裝置。系統透過調整 PWM 來改變風扇轉速。 |

## 控制演算法

| 術語 | 英文 | 定義 |
|------|------|------|
| PID | PID (Proportional-Integral-Derivative) | 一種回饋控制演算法。根據目標值與實際值的誤差，計算出控制輸出。P 項反應當前誤差，I 項修正累積誤差，D 項預測誤差趨勢。 |
| Thermal PID | Thermal PID Controller | 讀取溫度感測器，計算出風扇應該轉多快（目標 RPM）。執行頻率較低（每秒一次），因為溫度變化慢。 |
| Fan PID | Fan PID Controller | 讀取風扇當前 RPM，計算需要多少 PWM 才能達到 Thermal PID 給的目標 RPM。執行頻率較高（每 0.1 秒一次），因為風扇回饋快。 |
| Stepwise | Stepwise Controller | 查表式控制。不做 PID 計算，直接用溫度對照表決定輸出。例如 <30°C→低速、30~50°C→中速、>50°C→高速。 |
| Setpoint | Setpoint（設定點） | 控制目標值。Thermal PID 的 setpoint 是目標溫度（例如 70°C）；Fan PID 的 setpoint 是目標 RPM（由 Thermal PID 計算得出）。 |

## 控制參數

| 術語 | 英文 | 定義 |
|------|------|------|
| PWM | PWM (Pulse Width Modulation) | 脈寬調變，控制風扇轉速的方式。0% = 停轉，100% = 全速。 |
| RPM | RPM (Revolutions Per Minute) | 每分鐘轉數，衡量風扇實際轉速的單位。 |
| 最低轉速 | minThermalOutput | Zone 的最低 RPM 設定點。即使溫度很低，風扇也不會低於這個轉速。 |
| Slew Rate | Slew Rate（變化速率限制） | 限制輸出值每秒最大變化量，避免風扇轉速急升急降。 |
| 遲滯 | Hysteresis | 在閾值附近設定一個緩衝區間。輸入值在區間內波動時維持上次輸出不變，避免頻繁切換。 |
| RPM 上限 | RPM Ceiling | Stepwise 控制器可設定的風扇轉速上限，即使 PID 要求更高也不會超過此值。 |

## 安全機制

| 術語 | 英文 | 定義 |
|------|------|------|
| Failsafe | Failsafe（故障安全模式） | 當感測器故障或超時時，Zone 進入的保護模式。Failsafe 下風扇會被強制拉到安全百分比（例如 75%），防止因感測器失效導致溫度失控。 |
| Failsafe 百分比 | Failsafe Percent | Failsafe 模式下風扇的最低 PWM 百分比。可以在 Zone 層級設定（全域），也可以針對個別感測器設定不同值。 |
| 感測器超時 | Sensor Timeout | 感測器在設定秒數內沒有回報新讀數，就被視為故障，觸發 Failsafe。 |
| missingIsAcceptable | Missing Is Acceptable | 標記特定感測器為「可接受遺失」。該感測器故障時不會觸發 Failsafe。 |

## 操作模式

| 術語 | 英文 | 定義 |
|------|------|------|
| 自動模式 | Automatic Mode | 預設模式。PID 控制迴圈正常運作，自動調節風扇。 |
| 手動模式 | Manual Mode | 管理員手動控制風扇轉速，PID 停止計算。 |
| Redundant Write | Redundant Write | 從手動模式切回自動模式時，強制寫入一次風扇 PWM，確保風扇值與 PID 計算同步。 |

## Thermal 計算類型

| 術語 | 英文 | 定義 |
|------|------|------|
| Absolute 模式 | Absolute (temp/power) | 多個感測器取最大值。關注最熱的那個，確保最高溫部件被照顧到。 |
| Margin 模式 | Margin | 多個感測器取最小值。Margin = 離安全上限還有多遠，取最小 margin 等於關注最危險的感測器。 |
| Summation 模式 | Summation (powersum) | 多個感測器值加總。用於功率累加的場景。 |
| TempToMargin 轉換 | TempToMargin | 把絕對溫度轉成 margin 值。公式：margin = Tjmax - 溫度。Tjmax 是元件最高容許溫度。 |
