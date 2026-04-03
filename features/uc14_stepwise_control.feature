Feature: UC14 - Stepwise 階梯控制 (Strategy Pattern)
  As a BMC 系統
  I need to 能使用查表式的控制方式
  So that 在不需要精確 PID 控制的場景中用簡單的分段邏輯控制風扇

  # === 正常處理 (Normal) ===
  Scenario: N - 溫度低於最低閾值時輸出最低級
    Given 一個 Stepwise 控制器，溫度對照表為 30/2000, 40/4000, 50/6000, 60/8000
    When 輸入溫度為 25.0
    Then Stepwise 輸出應為 2000.0

  Scenario: N - 溫度在兩個閾值之間時輸出較低級的值
    Given 一個 Stepwise 控制器，溫度對照表為 30/2000, 40/4000, 50/6000, 60/8000
    When 輸入溫度為 45.0
    Then Stepwise 輸出應為 4000.0

  Scenario: N - 溫度超過最高閾值時輸出最高級
    Given 一個 Stepwise 控制器，溫度對照表為 30/2000, 40/4000, 50/6000, 60/8000
    When 輸入溫度為 75.0
    Then Stepwise 輸出應為 8000.0

  # === 異常處理 (Exception) ===
  Scenario: E - 遲滯區間內維持上次輸出不變
    Given 一個 Stepwise 控制器，溫度對照表為 30/2000, 40/4000, 50/6000, 60/8000
    And 遲滯設定為正向 2.0，負向 2.0
    When 輸入溫度為 45.0
    Then Stepwise 輸出應為 4000.0
    When 輸入溫度變為 46.0
    Then Stepwise 輸出應維持為 4000.0

  # === 替代處理 (Alternative) ===
  Scenario: A - Stepwise 輸出作為 RPM 上限 (Ceiling)
    Given 一個 isCeiling 的 Stepwise 控制器，溫度對照表為 30/5000, 50/8000
    And 一個配置好的 Zone
    When 輸入溫度為 35.0 並執行 Stepwise 控制
    Then Zone 的 RPM Ceiling 應包含 5000.0

  Scenario: A - Stepwise 沒有輸入感測器時建立失敗
    When 嘗試建立一個沒有輸入的 Stepwise 控制器
    Then 應拋出 ValueError
