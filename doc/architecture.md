# 系統架構

## 原始 C++ 架構（OpenBMC phosphor-pid-control）

在真實的 BMC 環境中，感測器資料和風扇控制分散在不同的 daemon，透過 D-Bus 溝通：

```
phosphor-hwmon          swampd (PID 控制)           Linux sysfs
 (感測器 daemon)         (本專案的原型)              (硬體介面)
      │                       │                        │
      │  D-Bus signal         │                        │
      │  "溫度變了: 55°C"      │                        │
      ├──────────────────────►├─ 更新快取               │
      │                       ├─ Thermal PID 計算       │
      │                       ├─ Fan PID 計算           │
      │                       ├─ 寫入 PWM ────────────►│
      │                       │                        │ /sys/class/hwmon/pwm1
      │  D-Bus signal         │                        │
      │  "風扇轉速: 3500RPM"   │                        │
      ├──────────────────────►├─ 更新風扇快取            │
      │                       │                        │
```

重點：
- **感測器讀取**和 **PID 控制**是不同的程式
- 透過 D-Bus 的 signal（publish/subscribe）非同步溝通
- 每個 Zone 各自獨立，用 Boost.ASIO async timer 驅動

## 目前 Python 版本（v1 — 直接呼叫）

移除所有 D-Bus / sysfs 依賴，全部在同一個 thread 內直接呼叫：

```
main thread
  │
  └─ pidControlLoop()
       │
       ├─ sensor.read()          ← 直接呼叫 SimulatedSensor（產生假溫度）
       ├─ zone.processThermals() ← Thermal PID 計算
       ├─ zone.processFans()     ← Fan PID 計算
       └─ fan.write(pwm)         ← 直接呼叫 SimulatedFan（印出 PWM）
```

特徵：
- 單一 thread，沒有非同步溝通
- 沒有模擬 D-Bus 的 publish/subscribe
- 可以跑、可以看 PID 收斂，但架構上跟原始版本差異大

## 目標 Python 版本（v2 — threading + Queue）

用 threading + Queue 模擬原始架構中 D-Bus signal 的非同步溝通：

```
Sensor Thread                    Zone Thread (每個 Zone 一個)
 │                                │
 ├─ 定期產生感測器值               │
 ├─ queue.put(name, value) ──►   ├─ queue.get() 更新快取
 │                                ├─ Thermal PID 計算
 │                                ├─ Fan PID 計算
 │                                └─ fan.write(pwm)
 │                                │
 ├─ 定期產生風扇 RPM              │
 ├─ queue.put(name, rpm) ───►    ├─ queue.get() 更新風扇快取
 │                                │
```

### 與原始架構的對應

| 原始 C++ | Python v2 | 說明 |
|----------|-----------|------|
| phosphor-hwmon daemon | Sensor Thread | 定期產生感測器讀數 |
| D-Bus signal | `queue.Queue` | 非同步傳遞感測器值 |
| swampd (每個 Zone 的 async timer) | Zone Thread | 獨立的控制迴圈 |
| Boost.ASIO event loop | `threading.Thread` + `time.sleep` | 週期性排程 |
| sysfs 寫入 | `SimulatedFan.write()` | 模擬 PWM 輸出 |

### 為什麼用 threading + Queue

1. **不需要分 process** — 沒有記憶體隔離需求
2. **Queue 是 thread safe** — 不需要自己管 lock
3. **團隊熟悉** — 對應 C++ 的 `std::thread` + thread-safe queue

### Design Pattern 對應

| Pattern | 在哪裡 | v1 已有 | v2 新增 |
|---------|--------|---------|---------|
| Strategy | Controller 繼承體系 | ✓ | |
| Template Method | PIDController.process() | ✓ | |
| Factory Method | FanController.create() 等 | ✓ | |
| Adapter | ReadInterface / WriteInterface | ✓ | |
| Null Object | ReadOnly（未寫入端的佔位） | ✓ | |
| Observer | 感測器 → Queue → Zone | | ✓ |
