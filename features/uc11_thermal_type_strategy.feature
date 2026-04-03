Feature: UC11 - Thermal 計算類型選擇 (Strategy Pattern)
  As a BMC 系統
  I need to 根據配置選擇不同的溫度彙總策略
  So that 針對不同場景（溫度、margin、功率）做最適合的控制

  Background:
    Given 一個 Zone，最低轉速 3000 RPM，Failsafe 百分比 75%
    And Zone 有溫度感測器 "temp_cpu0"
    And Zone 額外新增溫度感測器 "temp_cpu1"
    And Zone 有風扇 "fan0"，最大轉速 10000 RPM
    And Zone 有 Fan PID 控制器

  # === 正常處理 (Normal) ===
  Scenario: N - Absolute 模式取所有感測器中的最大值
    Given Zone 有一個 "temp" 類型 Thermal PID 控制器 "thermal_abs"，目標值 70.0
    And 感測器 "temp_cpu0" 讀數為 50.0
    And 感測器 "temp_cpu1" 讀數為 65.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 輸入值應為最大值 65.0

  Scenario: N - Margin 模式取所有感測器中的最小值
    Given Zone 有一個 "margin" 類型 Thermal PID 控制器 "thermal_margin"，目標值 10.0
    And 感測器 "temp_cpu0" 讀數為 15.0
    And 感測器 "temp_cpu1" 讀數為 8.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 輸入值應為最小值 8.0

  Scenario: N - Summation 模式加總所有感測器的值
    Given Zone 有一個 "powersum" 類型 Thermal PID 控制器 "thermal_power"，目標值 200.0
    And 感測器 "temp_cpu0" 讀數為 80.0
    And 感測器 "temp_cpu1" 讀數為 120.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 輸入值應為加總 200.0

  # === 異常處理 (Exception) ===
  Scenario: E - 無法識別的 Thermal 類型拋出錯誤
    When 嘗試建立類型為 "unknown_type" 的 Thermal 控制器
    Then 應拋出 ValueError

  # === 替代處理 (Alternative) ===
  Scenario: A - Margin 模式支援 TempToMargin 轉換
    Given Zone 有一個 "margin" 類型 Thermal PID 控制器 "thermal_margin"，目標值 10.0
    And 感測器 "temp_cpu0" 設定 TempToMargin 轉換，Tjmax 為 100.0
    And 感測器 "temp_cpu0" 讀數為 80.0
    And 感測器 "temp_cpu1" 讀數為 25.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 輸入值應為最小值 20.0
