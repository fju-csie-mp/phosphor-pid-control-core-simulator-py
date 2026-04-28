Feature: UC5 - 感測器讀值與健康狀態
  As a BMC 系統
  I need to 透過統一介面讀取感測器、寫入風扇、並追蹤感測器健康狀態
  So that 上層 Zone 與控制器可以用一致方式存取硬體資訊

  # === 正常處理 (Normal) ===
  Scenario: N - SimulatedSensor 讀值落在 base ± amplitude 範圍內
    Given 一個 SimulatedSensor "temp_a"，base 50.0、amplitude 5.0、noise 0.0
    When 讀取感測器 "temp_a" 一次
    Then 讀值應介於 45.0 與 55.0 之間
    And 讀值的 timestamp 應為當前時間

  Scenario: N - SimulatedFan 寫入 PWM 後讀回對應 RPM
    Given 一個 SimulatedFan "fan_a"，最大轉速 10000 RPM
    When 對 "fan_a" 寫入 PWM 0.5
    And 讀取感測器 "fan_a" 一次
    Then 讀值應接近 5000.0 RPM，誤差容許 100

  # === 異常處理 (Exception) ===
  Scenario: E - 感測器被標記故障後 get_failed 為 True 且有故障原因
    Given 一個 SimulatedSensor "temp_b"，base 50.0、amplitude 0.0、noise 0.0
    When 將 "temp_b" 標記為故障，原因 "感測器斷線"
    Then 感測器 "temp_b" 的 get_failed 應為 True
    And 感測器 "temp_b" 的 fail_reason 應為 "感測器斷線"

  # === 替代處理 (Alternative) ===
  Scenario: A - 故障感測器恢復後 get_failed 回 False
    Given 一個 SimulatedSensor "temp_c"，base 50.0、amplitude 0.0、noise 0.0
    And "temp_c" 已被標記為故障
    When 將 "temp_c" 標記為恢復正常
    Then 感測器 "temp_c" 的 get_failed 應為 False
