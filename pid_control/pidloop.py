"""
PID 控制迴圈

對應 C++ 原始碼: pid/pidloop.hpp + pid/pidloop.cpp

這個模組實作了整個系統的主控制迴圈。
控制迴圈是一個無限迴圈，週期性地執行以下步驟：

  每 0.1 秒（fan cycle）：
    1. 更新風扇轉速快取
    2. 執行 Fan PID（根據目標 RPM 調整 PWM）

  每 1 秒（thermal cycle，嵌在 fan cycle 中）：
    3. 更新溫度感測器快取
    4. 清除上次的 setpoints
    5. 執行 Thermal PID（根據溫度算出目標 RPM）
    6. 計算最終的 max setpoint

在 C++ 版本中，這個迴圈用 Boost.ASIO 的 async_wait 實現
（非同步遞迴呼叫），這裡簡化成 Python 的 time.sleep 迴圈。

整個流程圖：
  ┌─────────────────────────────────────────────────────┐
  │                    main loop                         │
  │                                                      │
  │  每 0.1s (fan cycle):                                │
  │    ├─ updateFanTelemetry()  ← 讀風扇 RPM            │
  │    │                                                  │
  │    ├─ 每 1s (thermal cycle):                         │
  │    │   ├─ updateSensors()      ← 讀溫度             │
  │    │   ├─ clearSetPoints()                           │
  │    │   ├─ processThermals()    ← Thermal PID 計算   │
  │    │   └─ determineMaxSetPoint()                     │
  │    │                                                  │
  │    └─ processFans()            ← Fan PID 計算        │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import sys
import time

from pid_control.zone import Zone


def _process_thermals(zone: Zone) -> None:
    """
    執行一次完整的 thermal cycle。

    對應 C++: processThermals() (pidloop.cpp:22-33)

    流程：
      1. 讀取所有溫度感測器的最新值
      2. 清除上次的 setpoint 和 RPM 上限
      3. 執行所有 Thermal PID / Stepwise 控制器
      4. 從所有 setpoint 中計算出最大的那個
    """
    zone.update_sensors()
    zone.clear_set_points()
    zone.clear_rpm_ceilings()
    zone.process_thermals()
    zone.determine_max_set_point_request()


def pid_control_loop(
    zone: Zone,
    max_cycles: int | None = None,
    print_interval: int = 10,
) -> None:
    """
    主控制迴圈。

    對應 C++: pidControlLoop() (pidloop.cpp:35-143)

    在 C++ 版本中，這是一個 async 遞迴函數（用 Boost.ASIO timer 驅動）。
    這裡簡化成同步的 while 迴圈。

    Args:
        zone: 要控制的 Zone
        max_cycles: 最大執行次數（None = 無限迴圈，用於測試時可設定有限次數）
        print_interval: 每隔多少 cycle 印一次狀態
    """
    # --- 初始化 ---
    zone.initialize_cache()
    _process_thermals(zone)

    ms_per_fan_cycle = zone.get_cycle_interval_time()     # 風扇迴圈間隔(ms)
    ms_per_thermal_cycle = zone.get_update_thermals_cycle()  # 溫度迴圈間隔(ms)

    cycle_cnt: int = 0    # 累積毫秒計數器
    iteration: int = 0    # 迴圈次數

    sleep_sec = ms_per_fan_cycle / 1000.0  # 轉成秒

    print(
        f"\n{'='*70}\n"
        f"  Zone {zone.get_zone_id()} 控制迴圈啟動\n"
        f"  Fan cycle: 每 {ms_per_fan_cycle}ms | "
        f"Thermal cycle: 每 {ms_per_thermal_cycle}ms\n"
        f"{'='*70}",
        file=sys.stderr,
    )

    while max_cycles is None or iteration < max_cycles:
        time.sleep(sleep_sec)
        iteration += 1

        # --- 手動模式：跳過所有計算 ---
        if zone.get_manual_mode():
            continue

        # --- 更新風扇轉速快取 ---
        zone.update_fan_telemetry()

        # --- Thermal cycle（頻率較低）---
        # 用累積毫秒的方式來決定是否該執行 thermal cycle
        if cycle_cnt >= ms_per_thermal_cycle:
            cycle_cnt -= ms_per_thermal_cycle
            _process_thermals(zone)

        # --- Fan cycle（每次都執行）---
        zone.process_fans()

        # --- 印出狀態（方便觀察 PID 收斂過程）---
        if iteration % print_interval == 0:
            _print_status(zone, iteration)

        # 累加毫秒計數器
        cycle_cnt += ms_per_fan_cycle


def _print_status(zone: Zone, iteration: int) -> None:
    """印出當前 Zone 的狀態摘要"""
    failsafe = zone.get_failsafe_mode()
    max_sp = zone.get_max_set_point_request()

    # 收集風扇資訊
    fan_info_parts: list[str] = []
    for name in zone._fan_inputs:
        cached = zone._cached_values.get(name)
        output = zone._cached_fan_outputs.get(name)
        rpm_str = f"{cached.unscaled:.0f}" if cached else "?"
        pwm_str = f"{output.scaled * 100:.1f}%" if output else "?"
        fan_info_parts.append(f"{name}={rpm_str}RPM/{pwm_str}")

    # 收集溫度資訊
    temp_info_parts: list[str] = []
    for name in zone._thermal_inputs:
        cached = zone._cached_values.get(name)
        val_str = f"{cached.scaled:.1f}" if cached else "?"
        temp_info_parts.append(f"{name}={val_str}")

    fans_str = ", ".join(fan_info_parts)
    temps_str = ", ".join(temp_info_parts)
    fs_str = " [FAILSAFE]" if failsafe else ""

    print(
        f"  [#{iteration:>4}] setpoint={max_sp:.0f}RPM | "
        f"fans: {fans_str} | temps: {temps_str}{fs_str}",
        file=sys.stderr,
    )
