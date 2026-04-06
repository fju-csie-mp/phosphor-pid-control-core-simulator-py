"""
PID 控制迴圈

對應 C++ 原始碼: pid/pidloop.hpp + pid/pidloop.cpp

這個模組提供兩種控制迴圈：

1. pid_control_loop() — 直接呼叫模式（v1）
   Zone 自己呼叫 sensor.read() 讀感測器。
   用於 BDD 測試和單 thread 執行。

2. pid_control_loop_threaded() — Queue 模式（v2）
   Zone 從 Queue 接收 SensorThread 發來的感測器值。
   用於多 Thread 執行，模擬原始 C++ 的 D-Bus 架構。

控制迴圈的核心流程不變：
  每 0.1 秒 (fan cycle):
    1. 更新感測器快取
    2. 每 1 秒 (thermal cycle): Thermal PID 計算目標 RPM
    3. Fan PID 計算 PWM 輸出
"""

from __future__ import annotations

import sys
import threading
import time

from pid_control.zone import Zone


def _process_thermals(zone: Zone) -> None:
    """
    執行一次完整的 thermal cycle。

    對應 C++: processThermals() (pidloop.cpp:22-33)
    """
    zone.clear_set_points()
    zone.clear_rpm_ceilings()
    zone.process_thermals()
    zone.determine_max_set_point_request()


# =========================================================================
# v1: 直接呼叫模式（BDD 測試 + 單 thread）
# =========================================================================

def pid_control_loop(
    zone: Zone,
    max_cycles: int | None = None,
    print_interval: int = 10,
) -> None:
    """
    直接呼叫模式的控制迴圈（v1）。

    Zone 自己呼叫 sensor.read() 讀感測器值。
    用於 BDD 測試和單 thread 執行。

    Args:
        zone: 要控制的 Zone
        max_cycles: 最大執行次數（None = 無限迴圈）
        print_interval: 每隔多少 cycle 印一次狀態
    """
    zone.initialize_cache()
    zone.update_sensors()
    _process_thermals(zone)

    ms_per_fan_cycle = zone.get_cycle_interval_time()
    ms_per_thermal_cycle = zone.get_update_thermals_cycle()
    cycle_cnt: int = 0
    iteration: int = 0
    sleep_sec = ms_per_fan_cycle / 1000.0

    _print_banner(zone)

    while max_cycles is None or iteration < max_cycles:
        time.sleep(sleep_sec)
        iteration += 1

        if zone.get_manual_mode():
            continue

        zone.update_fan_telemetry()

        if cycle_cnt >= ms_per_thermal_cycle:
            cycle_cnt -= ms_per_thermal_cycle
            zone.update_sensors()
            _process_thermals(zone)

        zone.process_fans()

        if iteration % print_interval == 0:
            _print_status(zone, iteration)

        cycle_cnt += ms_per_fan_cycle


# =========================================================================
# v2: Queue 模式（多 Thread，模擬 D-Bus 架構）
# =========================================================================

def pid_control_loop_threaded(
    zone: Zone,
    stop_event: threading.Event,
    print_interval: int = 10,
) -> None:
    """
    Queue 模式的控制迴圈（v2）。

    Zone 從 Queue 接收 SensorThread 發來的感測器值，
    而不是自己呼叫 sensor.read()。

    每個 Zone 跑在自己的 Thread 中，SensorThread 透過 Queue
    把感測器值推送過來。這模擬了原始 C++ 中：
      - phosphor-hwmon 透過 D-Bus signal 發送感測器值
      - swampd 的 DbusPassive 收到後更新快取

    Args:
        zone: 要控制的 Zone
        stop_event: 收到此 event 時停止迴圈
        print_interval: 每隔多少 cycle 印一次狀態
    """
    zone.initialize_cache()

    ms_per_fan_cycle = zone.get_cycle_interval_time()
    ms_per_thermal_cycle = zone.get_update_thermals_cycle()
    cycle_cnt: int = 0
    iteration: int = 0
    sleep_sec = ms_per_fan_cycle / 1000.0

    _print_banner(zone)

    while not stop_event.is_set():
        stop_event.wait(timeout=sleep_sec)
        if stop_event.is_set():
            break
        iteration += 1

        if zone.get_manual_mode():
            continue

        # 與 v1 的關鍵差異：用 drain_queue() 取代 update_sensors()
        # 感測器值是 SensorThread 透過 Queue 推送過來的
        zone.drain_queue()

        if cycle_cnt >= ms_per_thermal_cycle:
            cycle_cnt -= ms_per_thermal_cycle
            _process_thermals(zone)

        zone.process_fans()

        if iteration % print_interval == 0:
            _print_status(zone, iteration)

        cycle_cnt += ms_per_fan_cycle

    print(
        f"  Zone {zone.get_zone_id()} 控制迴圈已停止",
        file=sys.stderr,
    )


# =========================================================================
# 共用的輸出函數
# =========================================================================

def _print_banner(zone: Zone) -> None:
    ms_per_fan_cycle = zone.get_cycle_interval_time()
    ms_per_thermal_cycle = zone.get_update_thermals_cycle()
    print(
        f"\n{'='*70}\n"
        f"  Zone {zone.get_zone_id()} 控制迴圈啟動\n"
        f"  Fan cycle: 每 {ms_per_fan_cycle}ms | "
        f"Thermal cycle: 每 {ms_per_thermal_cycle}ms\n"
        f"{'='*70}",
        file=sys.stderr,
    )


def _print_status(zone: Zone, iteration: int) -> None:
    """印出當前 Zone 的狀態摘要"""
    failsafe = zone.get_failsafe_mode()
    max_sp = zone.get_max_set_point_request()

    fan_info_parts: list[str] = []
    for name in zone._fan_inputs:
        cached = zone._cached_values.get(name)
        output = zone._cached_fan_outputs.get(name)
        rpm_str = f"{cached.unscaled:.0f}" if cached else "?"
        pwm_str = f"{output.scaled * 100:.1f}%" if output else "?"
        fan_info_parts.append(f"{name}={rpm_str}RPM/{pwm_str}")

    temp_info_parts: list[str] = []
    for name in zone._thermal_inputs:
        cached = zone._cached_values.get(name)
        val_str = f"{cached.scaled:.1f}" if cached else "?"
        temp_info_parts.append(f"{name}={val_str}")

    fans_str = ", ".join(fan_info_parts)
    temps_str = ", ".join(temp_info_parts)
    fs_str = " [FAILSAFE]" if failsafe else ""

    print(
        f"  [Zone {zone.get_zone_id()} #{iteration:>4}] "
        f"setpoint={max_sp:.0f}RPM | "
        f"fans: {fans_str} | temps: {temps_str}{fs_str}",
        file=sys.stderr,
    )
