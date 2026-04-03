Feature: UC6 - 載入 JSON 設定並建立物件
  As a BMC 系統
  I need to 從 JSON 設定檔載入配置
  So that 自動建立所有感測器、控制器和 Zone 物件

  # === 正常處理 (Normal) ===
  Scenario: N - 從有效的 JSON 設定檔建立所有物件
    Given 一個包含 2 個溫度感測器、2 個風扇、1 個 Zone 的 JSON 設定檔
    When 載入該設定檔
    Then 應建立 4 個感測器
    And 應建立 1 個 Zone
    And Zone 0 應包含 Thermal 控制器
    And Zone 0 應包含 Fan 控制器

  Scenario: N - Fan 感測器建立為 SimulatedFan 類型
    Given 一個包含 2 個溫度感測器、2 個風扇、1 個 Zone 的 JSON 設定檔
    When 載入該設定檔
    Then 感測器 "fan0" 應為 SimulatedFan 類型
    And 感測器 "temp_cpu0" 應為 SimulatedSensor 類型

  # === 異常處理 (Exception) ===
  Scenario: E - 設定檔不存在時報錯
    When 嘗試載入不存在的設定檔 "nonexistent.json"
    Then 應拋出 FileNotFoundError

  Scenario: E - Thermal 控制器沒有輸入感測器時報錯
    When 嘗試建立一個沒有輸入感測器的 Thermal 控制器
    Then 應拋出 ValueError

  # === 替代處理 (Alternative) ===
  Scenario: A - Stepwise 控制器從 JSON 正確建立
    Given 一個包含 Stepwise 控制器的 JSON 設定檔
    When 載入該設定檔
    Then Zone 0 應包含 Stepwise 控制器
