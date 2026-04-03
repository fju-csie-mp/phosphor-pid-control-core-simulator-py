Feature: UC4 - 手動模式切換
  As a 管理員
  I need to 能切換手動模式直接控制風扇以及回到自動模式
  So that 可以在需要時手動介入或讓 PID 自動接管

  Background:
    Given 一個 Zone，最低轉速 3000 RPM，Failsafe 百分比 75%
    And Zone 有溫度感測器 "temp_cpu0"
    And Zone 有風扇 "fan0"，最大轉速 10000 RPM
    And Zone 有 Thermal PID 控制器，目標溫度 70 度
    And Zone 有 Fan PID 控制器

  # === 正常處理 (Normal) ===
  Scenario: N - 切換到手動模式
    When 切換為手動模式
    Then Zone 應處於手動模式

  Scenario: N - 從手動模式回到自動模式時觸發 Redundant Write
    Given Zone 處於手動模式
    When 切換為自動模式
    Then Zone 不應處於手動模式
    And Redundant Write 應被啟用

  # === 異常處理 (Exception) ===
  Scenario: E - 手動模式下控制迴圈不執行 PID 計算
    Given 感測器 "temp_cpu0" 讀數為 85.0
    When 切換為手動模式
    And 模擬手動模式下的一次控制迴圈
    Then 風扇 "fan0" 的 PWM 不應被 PID 改變

  # === 替代處理 (Alternative) ===
  Scenario: A - 從手動回到自動後 PID 正常運作
    Given Zone 處於手動模式
    When 切換為自動模式
    And 感測器 "temp_cpu0" 讀數為 50.0
    And 執行一次完整的控制迴圈
    Then 最大 Setpoint 應為 3000.0 RPM
