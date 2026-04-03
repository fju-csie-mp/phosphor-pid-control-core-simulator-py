Feature: UC14 - Stepwise 階梯控制 (Strategy Pattern)
  As a BMC 系統
  I need to 能使用查表式的控制方式
  So that 在不需要精確 PID 控制的場景中用簡單的分段邏輯控制風扇

  # === 正常處理 (Normal) ===
  Scenario: N - 溫度低於最低閾值時輸出最低級
    Given 存在一個 Stepwise 控制器設定如下:
      | 溫度閾值 | 輸出值   |
      | 30.0  | 2000.0 |
      | 40.0  | 4000.0 |
      | 50.0  | 6000.0 |
      | 60.0  | 8000.0 |
    When 輸入溫度為 25.0
    Then Stepwise 輸出應該為 2000.0

  Scenario: N - 溫度在兩個閾值之間時輸出較低級的值
    Given 存在一個 Stepwise 控制器設定如下:
      | 溫度閾值 | 輸出值   |
      | 30.0  | 2000.0 |
      | 40.0  | 4000.0 |
      | 50.0  | 6000.0 |
      | 60.0  | 8000.0 |
    When 輸入溫度為 45.0
    Then Stepwise 輸出應該為 4000.0

  Scenario: N - 溫度超過最高閾值時輸出最高級
    Given 存在一個 Stepwise 控制器設定如下:
      | 溫度閾值 | 輸出值   |
      | 30.0  | 2000.0 |
      | 40.0  | 4000.0 |
      | 50.0  | 6000.0 |
      | 60.0  | 8000.0 |
    When 輸入溫度為 75.0
    Then Stepwise 輸出應該為 8000.0

  # === 異常處理 (Exception) ===
  Scenario: E - 遲滯區間內維持上次輸出不變
    Given 存在一個 Stepwise 控制器設定如下:
      | 溫度閾值 | 輸出值   |
      | 30.0  | 2000.0 |
      | 40.0  | 4000.0 |
      | 50.0  | 6000.0 |
      | 60.0  | 8000.0 |
    And 正向遲滯為 2.0 負向遲滯為 2.0
    When 輸入溫度為 45.0
    Then Stepwise 輸出應該為 4000.0
    When 輸入溫度變為 46.0
    Then Stepwise 輸出應該維持為 4000.0

  # === 替代處理 (Alternative) ===
  Scenario: A - Stepwise 輸出作為 RPM 上限 (ceiling)
    Given 存在一個 isCeiling 為 true 的 Stepwise 控制器設定如下:
      | 溫度閾值 | 輸出值   |
      | 30.0  | 5000.0 |
      | 50.0  | 8000.0 |
    And 系統有一個 Zone 配置
    When 輸入溫度為 35.0 並執行 Stepwise 控制
    Then Zone 的 RPM ceiling 應該包含 5000.0

  Scenario: A - Stepwise 沒有 inputs 時建立失敗
    When 嘗試建立一個沒有輸入的 Stepwise 控制器
    Then 應該拋出 ValueError 並提示缺少輸入
