"""
JSON 配置檔載入器

對應 C++ 原始碼:
  - sensors/buildjson.cpp (感測器配置解析)
  - pid/buildjson.cpp (PID 配置解析)
  - pid/builder.cpp (物件建立)

這個模組負責：
  1. 讀取 JSON 設定檔
  2. 解析成 Python 的 dataclass
  3. 根據配置建立所有的 Sensor、Controller、Zone 物件

JSON 設定檔結構大致如下：
{
  "sensors": {
    "感測器名稱": { type, readPath, writePath, min, max, timeout, ... }
  },
  "zones": {
    "zone_id": {
      "zone_config": { minThermalOutput, failsafePercent, ... },
      "pids": {
        "控制器名稱": { type, inputs, setpoint, pid, ... }
      }
    }
  }
}
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pid_control.conf import (
    ControllerInfo,
    CycleTime,
    SensorConfig,
    SensorInput,
    ThermalType,
    ZoneConfig,
    get_thermal_type,
    is_thermal_type,
)
from pid_control.controllers.controller import Controller
from pid_control.controllers.fan_controller import FanController
from pid_control.controllers.stepwise_controller import StepwiseController
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.ec.pid import Limits, PidConfig
from pid_control.ec.stepwise import MAX_STEPWISE_POINTS, StepwiseInfo
from pid_control.sensors.sensor import SensorManager, SimulatedFan, SimulatedSensor
from pid_control.zone import Zone


def load_config(path: str | Path) -> dict:
    """讀取 JSON 設定檔並回傳原始 dict"""
    with open(path) as f:
        return json.load(f)


def build_sensors_from_json(
    config: dict, sensor_manager: SensorManager
) -> dict[str, SensorConfig]:
    """
    從 JSON 建立所有感測器。

    對應 C++: buildSensorsFromJson() (sensors/buildjson.cpp)

    在 C++ 版本中，這裡會根據 readPath/writePath 建立
    DbusPassive、SysFsRead、SysFsWrite 等物件。
    我們用 SimulatedSensor / SimulatedFan 取代。

    Args:
        config: JSON 設定中的 "sensors" 區塊
        sensor_manager: 感測器管理器

    Returns:
        感測器名稱 → SensorConfig 的對照表
    """
    sensor_configs: dict[str, SensorConfig] = {}

    for name, s in config.items():
        sc = SensorConfig(
            type=s.get("type", ""),
            read_path=s.get("readPath", ""),
            write_path=s.get("writePath", ""),
            min=s.get("min", 0),
            max=s.get("max", 0),
            timeout=s.get("timeout", 0),
        )
        sensor_configs[name] = sc

        # 根據類型建立模擬感測器
        if sc.type == "fan":
            sim = s.get("simulation", {})
            fan = SimulatedFan(
                name=name,
                timeout=sc.timeout,
                max_rpm=sim.get("maxRpm", 10000.0),
                min_pwm=sc.min,
                max_pwm=sc.max if sc.max else 255,
            )
            sensor_manager.add_sensor(name, fan)
        else:
            # temp, margin, power 等都用模擬溫度感測器
            sim = s.get("simulation", {})
            sensor = SimulatedSensor(
                name=name,
                timeout=sc.timeout,
                base_temp=sim.get("baseTemp", 45.0),
                amplitude=sim.get("amplitude", 8.0),
                noise=sim.get("noise", 0.5),
                period=sim.get("period", 30.0),
            )
            sensor_manager.add_sensor(name, sensor)

    return sensor_configs


def _parse_pid_config(pid_dict: dict) -> PidConfig:
    """從 JSON 的 "pid" 欄位解析 PID 參數"""
    return PidConfig(
        ts=pid_dict.get("samplePeriod", 0.1),
        proportional_coeff=pid_dict.get("proportionalCoeff", 0.0),
        integral_coeff=pid_dict.get("integralCoeff", 0.0),
        derivative_coeff=pid_dict.get("derivativeCoeff", 0.0),
        feed_fwd_offset=pid_dict.get("feedFwdOffset", 0.0),
        feed_fwd_gain=pid_dict.get("feedFwdGain", 0.0),
        integral_limit=Limits(
            min=pid_dict.get("integralLimit_min", 0.0),
            max=pid_dict.get("integralLimit_max", 0.0),
        ),
        out_lim=Limits(
            min=pid_dict.get("outLim_min", 0.0),
            max=pid_dict.get("outLim_max", 0.0),
        ),
        slew_neg=pid_dict.get("slewNeg", 0.0),
        slew_pos=pid_dict.get("slewPos", 0.0),
        positive_hysteresis=pid_dict.get("positiveHysteresis", 0.0),
        negative_hysteresis=pid_dict.get("negativeHysteresis", 0.0),
    )


def _parse_stepwise_info(sw_dict: dict) -> StepwiseInfo:
    """從 JSON 的 "stepwise" 欄位解析 Stepwise 參數"""
    reading = [float("nan")] * MAX_STEPWISE_POINTS
    output = [float("nan")] * MAX_STEPWISE_POINTS

    for i, r in enumerate(sw_dict.get("reading", [])):
        if i >= MAX_STEPWISE_POINTS:
            break
        reading[i] = r

    for i, o in enumerate(sw_dict.get("output", [])):
        if i >= MAX_STEPWISE_POINTS:
            break
        output[i] = o

    return StepwiseInfo(
        ts=sw_dict.get("samplePeriod", 0.1),
        reading=reading,
        output=output,
        positive_hysteresis=sw_dict.get("positiveHysteresis", 0.0),
        negative_hysteresis=sw_dict.get("negativeHysteresis", 0.0),
        is_ceiling=sw_dict.get("isCeiling", False),
    )


def build_zones_from_json(
    config: dict, sensor_manager: SensorManager
) -> list[Zone]:
    """
    從 JSON 建立所有 Zone 及其 Controller。

    對應 C++: buildZonesFromJson() + buildPIDsFromJson() (pid/buildjson.cpp + builder.cpp)

    這是整個系統建立流程中最複雜的部分：
      1. 解析每個 zone 的配置（min RPM, failsafe %, cycle time）
      2. 對每個 zone，解析其所有的 PID / Stepwise 控制器
      3. 根據類型呼叫對應的 Factory Method 建立控制器物件
      4. 把控制器加入 Zone

    Args:
        config: JSON 設定中的 "zones" 區塊
        sensor_manager: 已建好的感測器管理器

    Returns:
        建好的 Zone 清單
    """
    zones: list[Zone] = []

    for zone_id_str, zone_data in config.items():
        zone_id = int(zone_id_str)
        zc = zone_data.get("zone_config", {})

        cycle_time = CycleTime(
            cycle_interval_ms=zc.get("cycleIntervalTimeMS", 100),
            update_thermals_ms=zc.get("updateThermalsTimeMS", 1000),
        )

        zone = Zone(
            zone_id=zone_id,
            min_thermal_output=zc.get("minThermalOutput", 3000.0),
            failsafe_percent=zc.get("failsafePercent", 75.0),
            cycle_interval_ms=cycle_time.cycle_interval_ms,
            update_thermals_ms=cycle_time.update_thermals_ms,
            sensor_manager=sensor_manager,
            accumulate_set_point=zc.get("accumulateSetPoint", False),
        )

        # 解析每個控制器
        pids = zone_data.get("pids", {})
        for pid_name, pid_data in pids.items():
            pid_type = pid_data.get("type", "")

            # 解析輸入感測器
            raw_inputs = pid_data.get("inputs", [])
            input_names: list[str] = []
            sensor_inputs: list[SensorInput] = []
            for inp in raw_inputs:
                if isinstance(inp, str):
                    input_names.append(inp)
                    sensor_inputs.append(SensorInput(name=inp))
                elif isinstance(inp, dict):
                    name = inp.get("name", "")
                    input_names.append(name)
                    sensor_inputs.append(SensorInput(
                        name=name,
                        convert_margin_zero=inp.get("convertMarginZero", float("nan")),
                        convert_temp_to_margin=inp.get("convertTempToMargin", False),
                        missing_is_acceptable=inp.get("missingIsAcceptable", False),
                    ))

            # --- 根據類型建立控制器 ---
            if pid_type == "fan":
                # Fan PID 控制器
                pid_config = _parse_pid_config(pid_data.get("pid", {}))
                controller = FanController.create(
                    zone, pid_name, input_names, pid_config
                )
                if controller:
                    for name in input_names:
                        missing_ok = any(
                            si.missing_is_acceptable
                            for si in sensor_inputs
                            if si.name == name
                        )
                        zone.add_fan_input(name, missing_ok)
                    zone.add_fan_pid(controller)

            elif pid_type == "stepwise":
                # Stepwise 控制器
                sw_info = _parse_stepwise_info(pid_data.get("stepwise", {}))
                controller = StepwiseController.create(
                    zone, pid_name, input_names, sw_info
                )
                for name in input_names:
                    missing_ok = any(
                        si.missing_is_acceptable
                        for si in sensor_inputs
                        if si.name == name
                    )
                    zone.add_thermal_input(name, missing_ok)
                zone.add_thermal_pid(controller)

            elif is_thermal_type(pid_type):
                # Thermal PID 控制器 (temp / margin / power / powersum)
                pid_config = _parse_pid_config(pid_data.get("pid", {}))
                thermal_type = get_thermal_type(pid_type)
                setpoint = pid_data.get("setpoint", 0.0)
                controller = ThermalController.create(
                    zone, pid_name, sensor_inputs, setpoint,
                    pid_config, thermal_type,
                )
                for si in sensor_inputs:
                    zone.add_thermal_input(si.name, si.missing_is_acceptable)
                zone.add_thermal_pid(controller)

            else:
                print(f"  警告: 未知的控制器類型 '{pid_type}'，跳過 {pid_name}")

        zones.append(zone)

    return zones
