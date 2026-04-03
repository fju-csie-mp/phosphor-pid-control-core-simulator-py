Feature: UC2 - 進入 Failsafe 模式
  As a BMC 系統
  I need to 在感測器故障或超時時進入 Failsafe 模式
  So that 風扇被拉到安全轉速防止硬體過熱損壞

  Background:
    Given 一個 Zone，最低轉速 3000 RPM，Failsafe 百分比 75%
    And Zone 有溫度感測器 "temp_cpu0"
    And Zone 有風扇 "fan0"，最大轉速 10000 RPM
    And Zone 有 Thermal PID 控制器，目標溫度 70 度
    And Zone 有 Fan PID 控制器

  # === 正常處理 (Normal) ===
  Scenario: N - 感測器正常時 Zone 不在 Failsafe 模式
    Given 感測器 "temp_cpu0" 讀數為 50.0
    When 更新感測器快取
    Then Zone 不應處於 Failsafe 模式

  # === 異常處理 (Exception) ===
  Scenario: E - 感測器故障時進入 Failsafe
    Given 感測器 "temp_cpu0" 標記為故障
    When 更新感測器快取
    Then Zone 應處於 Failsafe 模式
    And Failsafe 百分比應為 75.0

  Scenario: E - 感測器故障時風扇 PWM 不低於 Failsafe 百分比
    Given 感測器 "temp_cpu0" 標記為故障
    When 更新感測器快取
    And 執行一次完整的控制迴圈
    Then 風扇 "fan0" 的 PWM 應不低於 75.0%

  # === 替代處理 (Alternative) ===
  Scenario: A - 個別感測器可設定不同的 Failsafe 百分比
    Given 感測器 "temp_cpu0" 的 Failsafe 百分比設為 90.0
    And 感測器 "temp_cpu0" 標記為故障
    When 更新感測器快取
    Then Failsafe 百分比應為 90.0
