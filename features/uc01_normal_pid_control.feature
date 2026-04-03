Feature: UC1 - 正常 PID 控制迴圈
  As a BMC 系統
  I need to 週期性地執行 PID 控制迴圈
  So that 根據溫度感測器的讀數自動調節風扇轉速

  Background:
    Given 系統載入了包含以下設定的配置檔:
      | 設定項             | 值      |
      | minThermalOutput | 3000.0 |
      | failsafePercent  | 75.0   |
    And Zone 0 有以下溫度感測器:
      | 感測器名稱    | 類型   | 基礎溫度 |
      | temp_cpu0 | temp | 50.0  |
    And Zone 0 有以下風扇:
      | 風扇名稱 | 最大RPM   |
      | fan0  | 10000.0 |
    And Zone 0 有一個 Thermal PID 控制器 "thermal_cpu" 設定點為 70.0
    And Zone 0 有一個 Fan PID 控制器 "fan_pid"

  # === 正常處理 (Normal) ===
  Scenario: N - 溫度低於設定點時風扇維持最低轉速
    Given 溫度感測器 "temp_cpu0" 的讀數為 45.0
    When 執行一次完整的控制迴圈
    Then 最大設定點應該等於最低溫度輸出 3000.0 RPM
    And 風扇 "fan0" 應該有被寫入 PWM 值

  Scenario: N - 溫度接近設定點時 PID 維持最低轉速
    Given 溫度感測器 "temp_cpu0" 的讀數為 68.0
    When 執行一次完整的控制迴圈
    Then 最大設定點應該等於最低溫度輸出 3000.0 RPM
    And 風扇 "fan0" 應該有被寫入 PWM 值

  Scenario: N - 溫度超過設定點時 PID 計算出正向 RPM 需求
    Given 溫度感測器 "temp_cpu0" 的讀數為 80.0
    When 執行一次完整的控制迴圈
    Then 最大設定點應該等於最低溫度輸出 3000.0 RPM
    And 風扇 "fan0" 應該有被寫入 PWM 值

  # === 異常處理 (Exception) ===
  Scenario: E - 感測器讀數為 NaN 時使用設定點作為輸入
    Given 溫度感測器 "temp_cpu0" 的讀數為 NaN
    When 執行一次完整的控制迴圈
    Then 最大設定點應該等於最低溫度輸出 3000.0 RPM

  # === 替代處理 (Alternative) ===
  Scenario: A - 多個溫度感測器時取最高溫度
    Given Zone 0 額外新增溫度感測器 "temp_cpu1" 基礎溫度為 60.0
    And 溫度感測器 "temp_cpu0" 的讀數為 50.0
    And 溫度感測器 "temp_cpu1" 的讀數為 65.0
    When 執行一次完整的控制迴圈
    Then Thermal PID 的輸入值應該是所有感測器中的最大值 65.0
