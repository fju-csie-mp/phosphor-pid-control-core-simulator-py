Feature: UC2 - 進入 Failsafe 模式
  As a BMC 系統
  I need to 在感測器故障或超時時進入 Failsafe 模式
  So that 風扇被拉到安全轉速防止硬體因過熱而損壞

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
  Scenario: N - 感測器正常時 Zone 不在 Failsafe 模式
    Given 溫度感測器 "temp_cpu0" 的讀數為 50.0
    When 更新溫度感測器快取
    Then Zone 0 不應該處於 Failsafe 模式

  # === 異常處理 (Exception) ===
  Scenario: E - 感測器回報故障時進入 Failsafe
    Given 溫度感測器 "temp_cpu0" 被標記為故障
    When 更新溫度感測器快取
    Then Zone 0 應該處於 Failsafe 模式
    And Failsafe 百分比應該為 75.0

  Scenario: E - 感測器故障時風扇 PWM 不低於 Failsafe 百分比
    Given 溫度感測器 "temp_cpu0" 被標記為故障
    When 更新溫度感測器快取
    And 執行一次完整的控制迴圈
    Then 風扇 "fan0" 的 PWM 應該不低於 75.0%

  # === 替代處理 (Alternative) ===
  Scenario: A - 個別感測器可設定不同的 Failsafe 百分比
    Given 感測器 "temp_cpu0" 的個別 Failsafe 百分比為 90.0
    And 溫度感測器 "temp_cpu0" 被標記為故障
    When 更新溫度感測器快取
    Then Failsafe 百分比應該為 90.0
