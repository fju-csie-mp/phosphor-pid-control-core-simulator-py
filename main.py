"""
PID 風扇控制模擬器 — 主程式入口

對應 C++ 原始碼: main.cpp

使用方式:
    uv run main.py                    # 使用預設的 config.json
    uv run main.py --conf my.json     # 指定設定檔
    uv run main.py --cycles 200       # 只跑 200 次迴圈（不加則無限迴圈）

整體啟動流程（對照 C++ main.cpp）：
  1. 解析命令列參數
  2. 從 JSON 建立感測器 (buildSensors)
  3. 從 JSON 建立 Zone 和 Controller (buildZones)
  4. 對每個 Zone 啟動控制迴圈 (pidControlLoop)

在 C++ 版本中，每個 Zone 有自己的 async timer（用 Boost.ASIO）。
這裡簡化成單一迴圈（只執行第一個 Zone）。
如果要多 Zone 同時跑，可以用 threading 模組。
"""

import argparse
import sys
from pathlib import Path

from pid_control.config_loader import (
    build_sensors_from_json,
    build_zones_from_json,
    load_config,
)
from pid_control.pidloop import pid_control_loop
from pid_control.sensors.sensor import SensorManager


def main():
    # --- 命令列參數 ---
    parser = argparse.ArgumentParser(
        description="PID 風扇控制模擬器 (phosphor-pid-control Python 版)"
    )
    parser.add_argument(
        "--conf",
        default="config.json",
        help="JSON 設定檔路徑 (預設: config.json)",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="最大執行迴圈次數 (預設: 無限迴圈, Ctrl+C 停止)",
    )
    parser.add_argument(
        "--print-interval",
        type=int,
        default=10,
        help="每隔多少 cycle 印一次狀態 (預設: 10)",
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
    # 簡化版：只跑第一個 Zone（多 Zone 可以用 threading）
    zone = zones[0]

    try:
        pid_control_loop(
            zone,
            max_cycles=args.cycles,
            print_interval=args.print_interval,
        )
    except KeyboardInterrupt:
        print("\n\n已停止控制迴圈 (Ctrl+C)", file=sys.stderr)


if __name__ == "__main__":
    main()
