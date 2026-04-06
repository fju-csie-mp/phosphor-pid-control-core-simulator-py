Feature: UC10 - 多 Zone 獨立控制
  As a BMC 系統
  I need to 支援多個 Zone 各自獨立運行控制迴圈
  So that 不同區域的散熱策略互不干擾

  # === 正常處理 (Normal) ===
  Scenario: N - 兩個 Zone 各自獨立運行
    Given Zone 0，最低轉速 3000 RPM，Failsafe 百分比 75%，有感測器 "temp_cpu0" 和風扇 "fan0"
    And Zone 1，最低轉速 2000 RPM，Failsafe 百分比 80%，有感測器 "temp_pcie" 和風扇 "fan1"
    And 兩個 Zone 都有 Thermal PID 控制器和 Fan PID 控制器
    When 感測器 "temp_cpu0" 讀數為 50.0
    And 感測器 "temp_pcie" 讀數為 45.0
    And 對兩個 Zone 各執行一次控制迴圈
    Then Zone 0 的最大 Setpoint 應不低於 3000.0 RPM
    And Zone 1 的最大 Setpoint 應不低於 2000.0 RPM
    And Zone 0 與 Zone 1 的 Setpoint 應該獨立計算

  # === 異常處理 (Exception) ===
  Scenario: E - 一個 Zone 進入 Failsafe 不影響另一個 Zone
    Given Zone 0，最低轉速 3000 RPM，Failsafe 百分比 75%，有感測器 "temp_cpu0" 和風扇 "fan0"
    And Zone 1，最低轉速 2000 RPM，Failsafe 百分比 80%，有感測器 "temp_pcie" 和風扇 "fan1"
    And 兩個 Zone 都有 Thermal PID 控制器和 Fan PID 控制器
    When 感測器 "temp_cpu0" 標記為故障
    And 感測器 "temp_pcie" 讀數為 45.0
    And 對兩個 Zone 各更新感測器快取
    Then Zone 0 應處於 Failsafe 模式
    And Zone 1 不應處於 Failsafe 模式

  # === 替代處理 (Alternative) ===
  Scenario: A - 兩個 Zone 共用同一個感測器，各自維護快取
    Given Zone 0，最低轉速 3000 RPM，Failsafe 百分比 75%，有感測器 "temp_shared" 和風扇 "fan0"
    And Zone 1，最低轉速 2000 RPM，Failsafe 百分比 80%，有感測器 "temp_shared" 和風扇 "fan1"
    And 兩個 Zone 都有 Thermal PID 控制器和 Fan PID 控制器
    When 感測器 "temp_shared" 讀數為 55.0
    And 對兩個 Zone 各執行一次控制迴圈
    Then Zone 0 的快取中 "temp_shared" 值應為 55.0
    And Zone 1 的快取中 "temp_shared" 值應為 55.0
    And Zone 0 的最大 Setpoint 應不低於 3000.0 RPM
    And Zone 1 的最大 Setpoint 應不低於 2000.0 RPM
