# phosphor-pid-control-core-simulator-py

從 [OpenBMC phosphor-pid-control](https://github.com/openbmc/phosphor-pid-control) (C++) 抽取核心 PID 風扇控制邏輯，翻譯為 Python 的模擬器。移除了 D-Bus / sysfs / systemd 等硬體依賴，用模擬感測器取代，可在任何環境執行。

本專案為 Design Pattern 課程作業。

## 前置需求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) — Python 套件與專案管理工具

### 安裝 uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或用 Homebrew
brew install uv
```

## 快速開始

```bash
# clone
git clone https://github.com/fju-csie-mp/phosphor-pid-control-core-simulator-py.git
cd phosphor-pid-control-core-simulator-py

# 執行模擬器（uv 會自動建立虛擬環境和安裝依賴）
uv run main.py

# 指定設定檔
uv run main.py --conf config.json

# 跑 100 次迴圈後停止
uv run main.py --cycles 100

# 調整印出頻率（每 5 個 cycle 印一次）
uv run main.py --cycles 200 --print-interval 5

# 無限迴圈模式，按 Ctrl+C 停止
uv run main.py
```

## 執行測試

使用 [behave](https://behave.readthedocs.io/)（Python 的 Cucumber/BDD 框架）：

```bash
# 執行全部測試
uv run --extra test behave

# 執行單一 feature
uv run --extra test behave features/uc01_normal_pid_control.feature

# 顯示詳細輸出
uv run --extra test behave -v
```

### 測試覆蓋的用例

| Feature | Use Case | Scenarios |
|---------|----------|-----------|
| UC1 | 正常 PID 控制迴圈 | N×3, E×1, A×1 |
| UC2 | 進入 Failsafe 模式 | N×1, E×2, A×1 |
| UC3 | Failsafe 恢復 | N×1, E×1, A×1 |
| UC4 | 手動模式切換 | N×2, E×1, A×1 |
| UC6 | JSON 設定檔載入 (Factory Method) | N×2, E×2, A×1 |
| UC11 | Thermal 計算類型選擇 (Strategy) | N×3, E×1, A×1 |
| UC14 | Stepwise 階梯控制 (Strategy) | N×3, E×1, A×2 |

每個 Use Case 按 NEA 三段法撰寫：N = 正常處理、E = 異常處理、A = 替代處理。

術語定義見 [doc/glossary.md](doc/glossary.md)，系統架構見 [doc/architecture.md](doc/architecture.md)。

## 架構對照

原始 C++ 中，感測器和 PID 控制是不同的 daemon，透過 D-Bus 非同步溝通。本專案用 `threading` + `queue.Queue` 模擬這個架構：

| 原始 C++ | Python 版 |
|----------|-----------|
| phosphor-hwmon (感測器 daemon) | Sensor Thread |
| D-Bus signal | `queue.Queue` |
| swampd (每個 Zone 的 async timer) | Zone Thread |
| sysfs 寫入 | `SimulatedFan.write()` |

詳細架構說明見 [doc/architecture.md](doc/architecture.md)。

## 專案結構

```
main.py                          # 入口程式
config.json                      # 範例設定檔
doc/
└── glossary.md                  # 術語表（Zone, Failsafe, PID 等定義）
pid_control/
├── ec/
│   ├── pid.py                   # PID 核心數學運算    ← pid/ec/pid.cpp
│   └── stepwise.py              # Stepwise 查表演算法  ← pid/ec/stepwise.cpp
├── conf.py                      # 資料結構與介面定義    ← conf.hpp + interfaces.hpp
├── controllers/
│   ├── controller.py            # Controller 抽象基底  ← pid/controller.hpp
│   ├── pid_controller.py        # PID 控制器基底       ← pid/pidcontroller.cpp
│   ├── fan_controller.py        # 風扇控制器           ← pid/fancontroller.cpp
│   ├── thermal_controller.py    # 溫度控制器           ← pid/thermalcontroller.cpp
│   └── stepwise_controller.py   # 階梯控制器           ← pid/stepwisecontroller.cpp
├── sensors/
│   └── sensor.py                # 感測器基底 + 模擬實作  ← sensors/ + dbus/ + sysfs/
├── zone.py                      # Zone 區域管理        ← pid/zone.cpp
├── pidloop.py                   # 控制迴圈             ← pid/pidloop.cpp
└── config_loader.py             # JSON 設定載入        ← buildjson + builder
features/                        # BDD 測試 (behave/Cucumber)
├── uc01_normal_pid_control.feature
├── uc02_failsafe_mode.feature
├── uc03_failsafe_recovery.feature
├── uc04_manual_mode.feature
├── uc06_json_config_loading.feature
├── uc11_thermal_type_strategy.feature
├── uc14_stepwise_control.feature
└── steps/                       # Step definitions
```

## 追 code 建議閱讀順序

1. **`pid_control/ec/pid.py`** — 最底層的 PID 數學，每行都有中文註解
2. **`pid_control/conf.py`** — 所有資料結構定義，了解系統的「名詞」
3. **`pid_control/controllers/controller.py`** → **`pid_controller.py`** — Strategy + Template Method
4. **`pid_control/controllers/thermal_controller.py`** → **`fan_controller.py`** — 兩種具體控制器
5. **`pid_control/zone.py`** — Zone 如何管理快取和 Setpoint
6. **`pid_control/pidloop.py`** — 整個迴圈怎麼串起來
7. **`pid_control/config_loader.py`** — JSON 怎麼變成物件（Factory）

## 控制流程

```
JSON config
    │
    ▼
buildSensors() ──► SensorManager（感測器註冊表）
buildZones()   ──► Zone + Controllers
    │
    ▼
pidControlLoop（每個 Zone 獨立迴圈）
    │
    ├─ 每 1 秒 (Thermal cycle)
    │   ├─ updateSensors()          讀取溫度
    │   ├─ processThermals()        Thermal PID → 目標 RPM
    │   └─ determineMaxSetPoint()   取最大 Setpoint
    │
    └─ 每 0.1 秒 (Fan cycle)
        ├─ updateFanTelemetry()     讀取風扇轉速
        └─ processFans()            Fan PID → PWM 輸出
```

## License

Apache License 2.0 — 與原始 [phosphor-pid-control](https://github.com/openbmc/phosphor-pid-control) 相同。
