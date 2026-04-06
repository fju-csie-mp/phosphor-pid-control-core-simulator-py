"""
PID 風扇控制模擬器 — 主程式入口

對應 C++ 原始碼: main.cpp

使用方式:
    uv run main.py                    # 使用預設的 config.json
    uv run main.py --conf my.json     # 指定設定檔
    uv run main.py --cycles 200       # 只跑 200 次迴圈（v1 直接呼叫模式）
    uv run main.py --threaded         # v2 多 Thread 模式（模擬 D-Bus 架構）

啟動流程（對照 C++ main.cpp）：
  1. 解析命令列參數
  2. 從 JSON 建立感測器 (buildSensors)
  3. 從 JSON 建立 Zone 和 Controller (buildZones)
  4. 啟動控制迴圈：
     - 預設: v1 直接呼叫模式（單 thread）
     - --threaded: v2 Queue 模式（Sensor Thread + 每個 Zone 一個 Thread）
"""

import argparse
import sys
import threading
from pathlib import Path

from pid_control.config_loader import (
    build_sensors_from_json,
    build_zones_from_json,
    load_config,
)
from pid_control.pidloop import pid_control_loop, pid_control_loop_threaded
from pid_control.sensor_thread import SensorThread
from pid_control.sensors.sensor import SensorManager


def main():
    parser = argparse.ArgumentParser(
        description="PID 風扇控制模擬器 (phosphor-pid-control Python 版)"
    )
    parser.add_argument(
        "--conf", default="config.json",
        help="JSON 設定檔路徑 (預設: config.json)",
    )
    parser.add_argument(
        "--cycles", type=int, default=None,
        help="最大執行迴圈次數 (預設: 無限迴圈, Ctrl+C 停止。僅 v1 模式)",
    )
    parser.add_argument(
        "--print-interval", type=int, default=10,
        help="每隔多少 cycle 印一次狀態 (預設: 10)",
    )
    parser.add_argument(
        "--threaded", action="store_true",
        help="啟用 v2 多 Thread 模式（Sensor Thread + Zone Thread）",
    )
    args = parser.parse_args()

    # --- 讀取設定檔 ---
    conf_path = Path(args.conf)
    if not conf_path.exists():
        print(f"錯誤: 找不到設定檔 {conf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"載入設定檔: {conf_path}", file=sys.stderr)
    config = load_config(conf_path)

    # --- 建立感測器 ---
    sensor_manager = SensorManager()
    sensor_configs = build_sensors_from_json(
        config.get("sensors", {}), sensor_manager
    )
    print(
        f"已建立 {len(sensor_configs)} 個感測器: "
        f"{', '.join(sensor_configs.keys())}",
        file=sys.stderr,
    )

    # --- 建立 Zone ---
    zones = build_zones_from_json(config.get("zones", {}), sensor_manager)
    print(f"已建立 {len(zones)} 個 Zone", file=sys.stderr)

    if not zones:
        print("錯誤: 沒有任何 Zone 被建立", file=sys.stderr)
        sys.exit(1)

    # --- 啟動控制迴圈 ---
    if args.threaded:
        _run_threaded(zones, sensor_manager, args.print_interval)
    else:
        _run_single(zones[0], args.cycles, args.print_interval)


def _run_single(zone, max_cycles, print_interval):
    """v1: 直接呼叫模式（單 thread，向下相容）"""
    print("模式: v1 直接呼叫（單 thread）", file=sys.stderr)
    try:
        pid_control_loop(
            zone, max_cycles=max_cycles, print_interval=print_interval,
        )
    except KeyboardInterrupt:
        print("\n\n已停止控制迴圈 (Ctrl+C)", file=sys.stderr)


def _run_threaded(zones, sensor_manager, print_interval):
    """
    v2: Queue 模式（多 Thread，模擬 D-Bus 架構）

    啟動的 Thread：
      1. SensorThread — 定期讀取所有感測器，透過 Queue 發送給各 Zone
      2. 每個 Zone 一個 Thread — 從 Queue 接收感測器值，執行 PID 控制

    對應原始 C++：
      - SensorThread ≈ phosphor-hwmon daemon
      - Zone Thread ≈ swampd 中每個 Zone 的 async timer
      - Queue ≈ D-Bus signal
    """
    print(
        f"模式: v2 多 Thread（Sensor Thread + {len(zones)} 個 Zone Thread）",
        file=sys.stderr,
    )

    stop_event = threading.Event()

    # 建立每個 Zone 的 Queue 和感測器訂閱關係
    zone_queues: dict[int, object] = {}
    zone_sensors: dict[int, list[str]] = {}
    for zone in zones:
        zid = zone.get_zone_id()
        zone_queues[zid] = zone.get_sensor_queue()
        # 每個 Zone 關心自己的溫度感測器和風扇
        zone_sensors[zid] = zone._thermal_inputs + zone._fan_inputs

    # 啟動 Sensor Thread
    sensor_thread = SensorThread(
        sensor_manager, zone_queues, zone_sensors, interval=0.5
    )
    st = threading.Thread(
        target=sensor_thread.run, args=(stop_event,),
        name="SensorThread", daemon=True,
    )
    st.start()
    print("  SensorThread 已啟動", file=sys.stderr)

    # 啟動每個 Zone 的 Thread
    zone_threads: list[threading.Thread] = []
    for zone in zones:
        zt = threading.Thread(
            target=pid_control_loop_threaded,
            args=(zone, stop_event, print_interval),
            name=f"Zone-{zone.get_zone_id()}",
            daemon=True,
        )
        zt.start()
        zone_threads.append(zt)
        print(f"  Zone {zone.get_zone_id()} Thread 已啟動", file=sys.stderr)

    # 主 thread 等待 Ctrl+C
    try:
        while True:
            # 檢查是否有 thread 意外結束
            for zt in zone_threads:
                if not zt.is_alive():
                    print(f"警告: {zt.name} 意外結束", file=sys.stderr)
            stop_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在停止所有 Thread...", file=sys.stderr)
        stop_event.set()

        # 等待所有 thread 結束
        st.join(timeout=3.0)
        for zt in zone_threads:
            zt.join(timeout=3.0)

        print("已停止所有 Thread", file=sys.stderr)


if __name__ == "__main__":
    main()
