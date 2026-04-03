Feature: UC6 - 載入 JSON 設定並建立物件
  As a BMC 系統
  I need to 從 JSON 設定檔載入配置
  So that 自動建立所有感測器、控制器和 Zone 物件

  # === 正常處理 (Normal) ===
  Scenario: N - 從有效的 JSON 設定檔建立所有物件
    Given 存在一個有效的 JSON 設定檔包含:
      | 感測器數量 | Zone數量 | 控制器數量 |
      | 4       | 1      | 2       |
    When 系統載入該設定檔
    Then 應該建立 4 個感測器
    And 應該建立 1 個 Zone
    And Zone 0 應該包含 Thermal 控制器
    And Zone 0 應該包含 Fan 控制器

  Scenario: N - Fan 類型的感測器建立為 SimulatedFan
    Given 存在一個有效的 JSON 設定檔包含:
      | 感測器數量 | Zone數量 | 控制器數量 |
      | 4       | 1      | 2       |
    When 系統載入該設定檔
    Then 感測器 "fan0" 應該是 SimulatedFan 類型
    And 感測器 "temp_cpu0" 應該是 SimulatedSensor 類型

  # === 異常處理 (Exception) ===
  Scenario: E - 設定檔不存在時報錯
    When 嘗試載入不存在的設定檔 "nonexistent.json"
    Then 應該拋出 FileNotFoundError

  Scenario: E - Thermal 控制器沒有 inputs 時報錯
    Given 存在一個 Thermal 控制器配置但 inputs 為空
    When 嘗試建立該控制器
    Then 應該拋出 ValueError 並提示缺少輸入

  # === 替代處理 (Alternative) ===
  Scenario: A - Stepwise 控制器從 JSON 正確建立
    Given 存在一個 JSON 設定檔包含 Stepwise 控制器
    When 系統載入該設定檔
    Then Zone 0 應該包含 Stepwise 控制器
