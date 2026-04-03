Feature: UC1 - 正常 PID 控制迴圈
  As a BMC 系統
  I need to 週期性地執行 PID 控制迴圈
  So that 根據溫度感測器的讀數自動調節風扇轉速

  Background:
    Given 一個 Zone，最低轉速 3000 RPM，Failsafe 百分比 75%
    And Zone 有溫度感測器 "temp_cpu0"
    And Zone 有風扇 "fan0"，最大轉速 10000 RPM
    And Zone 有 Thermal PID 控制器，目標溫度 70 度
    And Zone 有 Fan PID 控制器

  # === 正常處理 (Normal) ===
  Scenario: N - 溫度低於設定點時風扇維持最低轉速
    Given 感測器 "temp_cpu0" 讀數為 45.0
    When 執行一次完整的控制迴圈
    Then 最大 Setpoint 應為 3000.0 RPM
    And 風扇 "fan0" 應該有被寫入 PWM 值

  Scenario: N - 溫度接近設定點時風扇維持最低轉速
    Given 感測器 "temp_cpu0" 讀數為 68.0
    When 執行一次完整的控制迴圈
    Then 最大 Setpoint 應為 3000.0 RPM
    And 風扇 "fan0" 應該有被寫入 PWM 值

  Scenario: N - 溫度超過設定點時 PID 計算出正向 RPM 需求
    Given 感測器 "temp_cpu0" 讀數為 80.0
    When 執行一次完整的控制迴圈
    Then 最大 Setpoint 應為 3000.0 RPM
    And 風扇 "fan0" 應該有被寫入 PWM 值

  # === 異常處理 (Exception) ===
  Scenario: E - 感測器讀數為 NaN 時使用設定點作為輸入
    Given 感測器 "temp_cpu0" 讀數為 NaN
    When 執行一次完整的控制迴圈
    Then 最大 Setpoint 應為 3000.0 RPM

  # === 替代處理 (Alternative) ===
  Scenario: A - 多個溫度感測器時取最高溫度
    Given Zone 額外新增溫度感測器 "temp_cpu1"
    And 感測器 "temp_cpu0" 讀數為 50.0
    And 感測器 "temp_cpu1" 讀數為 65.0
    When 執行一次完整的控制迴圈
    Then Thermal PID 輸入值應為最大值 65.0
