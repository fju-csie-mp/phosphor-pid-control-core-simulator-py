Feature: UC4 - 手動模式切換
  As a 管理員
  I need to 能切換手動模式直接控制風扇以及回到自動模式
  So that 可以在需要時手動介入或讓 PID 自動接管

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
  Scenario: N - 切換到手動模式後 PID 停止計算
    When 管理員將 Zone 0 切換為手動模式
    Then Zone 0 應該處於手動模式

  Scenario: N - 手動模式回到自動模式時觸發 redundant write
    Given Zone 0 處於手動模式
    When 管理員將 Zone 0 切換為自動模式
    Then Zone 0 不應該處於手動模式
    And Zone 0 的 redundant write 應該被啟用

  # === 異常處理 (Exception) ===
  Scenario: E - 手動模式下控制迴圈跳過 PID 計算
    Given 溫度感測器 "temp_cpu0" 的讀數為 85.0
    When 管理員將 Zone 0 切換為手動模式
    And 模擬手動模式下的一次控制迴圈
    Then 風扇 "fan0" 的 PWM 不應該被 PID 改變

  # === 替代處理 (Alternative) ===
  Scenario: A - 從手動回到自動後 PID 正常運作
    Given Zone 0 處於手動模式
    When 管理員將 Zone 0 切換為自動模式
    And 溫度感測器 "temp_cpu0" 的讀數為 50.0
    And 執行一次完整的控制迴圈
    Then 最大設定點應該等於最低溫度輸出 3000.0 RPM
