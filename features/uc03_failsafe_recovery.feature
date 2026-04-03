Feature: UC3 - Failsafe 恢復
  As a BMC 系統
  I need to 在故障感測器恢復後退出 Failsafe 模式
  So that 風扇恢復正常 PID 控制避免持續高速浪費電力

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
  Scenario: N - 感測器恢復後退出 Failsafe 模式
    Given 溫度感測器 "temp_cpu0" 被標記為故障
    When 更新溫度感測器快取
    Then Zone 0 應該處於 Failsafe 模式
    When 溫度感測器 "temp_cpu0" 恢復正常並讀數為 50.0
    And 更新溫度感測器快取
    Then Zone 0 不應該處於 Failsafe 模式

  # === 異常處理 (Exception) ===
  Scenario: E - 多個感測器故障時需全部恢復才能退出 Failsafe
    Given Zone 0 額外新增溫度感測器 "temp_cpu1" 基礎溫度為 45.0
    And 溫度感測器 "temp_cpu0" 被標記為故障
    And 溫度感測器 "temp_cpu1" 被標記為故障
    When 更新溫度感測器快取
    Then Zone 0 應該處於 Failsafe 模式
    When 溫度感測器 "temp_cpu0" 恢復正常並讀數為 50.0
    And 更新溫度感測器快取
    Then Zone 0 應該處於 Failsafe 模式
    When 溫度感測器 "temp_cpu1" 恢復正常並讀數為 45.0
    And 更新溫度感測器快取
    Then Zone 0 不應該處於 Failsafe 模式

  # === 替代處理 (Alternative) ===
  Scenario: A - missingIsAcceptable 的感測器故障不會觸發 Failsafe
    Given 溫度感測器 "temp_cpu0" 設定為 missingIsAcceptable
    And 溫度感測器 "temp_cpu0" 被標記為故障
    When 更新溫度感測器快取
    Then Zone 0 不應該處於 Failsafe 模式
