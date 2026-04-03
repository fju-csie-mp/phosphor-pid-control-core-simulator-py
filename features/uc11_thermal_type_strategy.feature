Feature: UC11 - Thermal 計算類型選擇 (Strategy Pattern)
  As a BMC 系統
  I need to 根據配置選擇不同的溫度彙總策略
  So that 針對不同場景（溫度、margin、功率）做最適合的控制

  Background:
    Given 系統載入了包含以下設定的配置檔:
      | 設定項             | 值      |
      | minThermalOutput | 3000.0 |
      | failsafePercent  | 75.0   |
    And Zone 0 有以下溫度感測器:
      | 感測器名稱    | 類型   | 基礎溫度 |
      | temp_cpu0 | temp | 50.0  |
      | temp_cpu1 | temp | 60.0  |
    And Zone 0 有以下風扇:
      | 風扇名稱 | 最大RPM   |
      | fan0  | 10000.0 |
    And Zone 0 有一個 Fan PID 控制器 "fan_pid"

  # === 正常處理 (Normal) ===
  Scenario: N - Absolute 模式取所有感測器中的最大值
    Given Zone 0 有一個類型為 "temp" 的 Thermal PID 控制器 "thermal_abs" 設定點為 70.0
    And 溫度感測器 "temp_cpu0" 的讀數為 50.0
    And 溫度感測器 "temp_cpu1" 的讀數為 65.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 的輸入值應該是所有感測器中的最大值 65.0

  Scenario: N - Margin 模式取所有感測器中的最小值
    Given Zone 0 有一個類型為 "margin" 的 Thermal PID 控制器 "thermal_margin" 設定點為 10.0
    And 溫度感測器 "temp_cpu0" 的讀數為 15.0
    And 溫度感測器 "temp_cpu1" 的讀數為 8.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 的輸入值應該是所有感測器中的最小值 8.0

  Scenario: N - Summation 模式加總所有感測器的值
    Given Zone 0 有一個類型為 "powersum" 的 Thermal PID 控制器 "thermal_power" 設定點為 200.0
    And 溫度感測器 "temp_cpu0" 的讀數為 80.0
    And 溫度感測器 "temp_cpu1" 的讀數為 120.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 的輸入值應該是所有感測器的加總 200.0

  # === 異常處理 (Exception) ===
  Scenario: E - 無法識別的 Thermal 類型拋出錯誤
    When 嘗試建立類型為 "unknown_type" 的 Thermal 控制器
    Then 應該拋出 ValueError

  # === 替代處理 (Alternative) ===
  Scenario: A - Margin 模式支援 TempToMargin 溫度轉換
    Given Zone 0 有一個類型為 "margin" 的 Thermal PID 控制器 "thermal_margin" 設定點為 10.0
    And 感測器 "temp_cpu0" 設定了 TempToMargin 轉換 Tjmax 為 100.0
    And 溫度感測器 "temp_cpu0" 的讀數為 80.0
    And 溫度感測器 "temp_cpu1" 的讀數為 25.0
    When 執行一次 Thermal 控制計算
    Then Thermal PID 的輸入值應該是所有感測器中的最小值 20.0
