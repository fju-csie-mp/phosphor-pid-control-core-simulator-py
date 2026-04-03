Feature: UC3 - Failsafe 恢復
  As a BMC 系統
  I need to 在故障感測器恢復後退出 Failsafe 模式
  So that 風扇恢復正常 PID 控制避免持續高速浪費電力

  Background:
    Given 一個 Zone，最低轉速 3000 RPM，Failsafe 百分比 75%
    And Zone 有溫度感測器 "temp_cpu0"
    And Zone 有風扇 "fan0"，最大轉速 10000 RPM
    And Zone 有 Thermal PID 控制器，目標溫度 70 度
    And Zone 有 Fan PID 控制器

  # === 正常處理 (Normal) ===
  Scenario: N - 感測器恢復後退出 Failsafe 模式
    Given 感測器 "temp_cpu0" 標記為故障
    When 更新感測器快取
    Then Zone 應處於 Failsafe 模式
    When 感測器 "temp_cpu0" 恢復正常，讀數為 50.0
    And 更新感測器快取
    Then Zone 不應處於 Failsafe 模式

  # === 異常處理 (Exception) ===
  Scenario: E - 多個感測器故障時需全部恢復才能退出 Failsafe
    Given Zone 額外新增溫度感測器 "temp_cpu1"
    And 感測器 "temp_cpu0" 標記為故障
    And 感測器 "temp_cpu1" 標記為故障
    When 更新感測器快取
    Then Zone 應處於 Failsafe 模式
    When 感測器 "temp_cpu0" 恢復正常，讀數為 50.0
    And 更新感測器快取
    Then Zone 應處於 Failsafe 模式
    When 感測器 "temp_cpu1" 恢復正常，讀數為 45.0
    And 更新感測器快取
    Then Zone 不應處於 Failsafe 模式

  # === 替代處理 (Alternative) ===
  Scenario: A - missingIsAcceptable 的感測器故障不會觸發 Failsafe
    Given 感測器 "temp_cpu0" 設定為 missingIsAcceptable
    And 感測器 "temp_cpu0" 標記為故障
    When 更新感測器快取
    Then Zone 不應處於 Failsafe 模式
