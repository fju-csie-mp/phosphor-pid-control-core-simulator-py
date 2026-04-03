"""
UC6 — JSON 設定檔載入的 step definitions
"""
import json
import os
import tempfile

from behave import given, when, then

from pid_control.config_loader import (
    build_sensors_from_json, build_zones_from_json, load_config,
)
from pid_control.conf import SensorInput, ThermalType
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.controllers.stepwise_controller import StepwiseController
from pid_control.ec.pid import Limits, PidConfig
from pid_control.sensors.sensor import SensorManager, SimulatedFan, SimulatedSensor


# ----------- 測試用的 JSON 設定內容 -----------

VALID_CONFIG = {
    "sensors": {
        "temp_cpu0": {"type": "temp", "timeout": 2,
                      "simulation": {"baseTemp": 50.0, "amplitude": 0, "noise": 0}},
        "temp_cpu1": {"type": "temp", "timeout": 2,
                      "simulation": {"baseTemp": 45.0, "amplitude": 0, "noise": 0}},
        "fan0": {"type": "fan", "min": 0, "max": 255, "timeout": 0},
        "fan1": {"type": "fan", "min": 0, "max": 255, "timeout": 0},
    },
    "zones": {
        "0": {
            "zone_config": {
                "minThermalOutput": 3000.0,
                "failsafePercent": 75.0,
            },
            "pids": {
                "thermal_cpu": {
                    "type": "temp",
                    "inputs": ["temp_cpu0", "temp_cpu1"],
                    "setpoint": 70.0,
                    "pid": {
                        "samplePeriod": 1.0, "proportionalCoeff": 100.0,
                        "integralCoeff": 2.0,
                        "integralLimit_min": 0.0, "integralLimit_max": 10000.0,
                        "outLim_min": 3000.0, "outLim_max": 10000.0,
                    },
                },
                "fan_pid": {
                    "type": "fan",
                    "inputs": ["fan0", "fan1"],
                    "pid": {
                        "samplePeriod": 0.1, "proportionalCoeff": 0.01,
                        "integralCoeff": 0.001,
                        "integralLimit_min": 0.0, "integralLimit_max": 100.0,
                        "outLim_min": 20.0, "outLim_max": 100.0,
                    },
                },
            },
        },
    },
}

STEPWISE_CONFIG = {
    "sensors": {
        "temp_cpu0": {"type": "temp", "timeout": 2},
        "fan0": {"type": "fan", "min": 0, "max": 255, "timeout": 0},
    },
    "zones": {
        "0": {
            "zone_config": {"minThermalOutput": 3000.0, "failsafePercent": 75.0},
            "pids": {
                "stepwise_ctrl": {
                    "type": "stepwise",
                    "inputs": ["temp_cpu0"],
                    "stepwise": {
                        "reading": [30.0, 40.0, 50.0, 60.0],
                        "output": [2000.0, 4000.0, 6000.0, 8000.0],
                    },
                },
                "fan_pid": {
                    "type": "fan",
                    "inputs": ["fan0"],
                    "pid": {
                        "samplePeriod": 0.1, "proportionalCoeff": 0.01,
                        "integralCoeff": 0.001,
                        "integralLimit_min": 0.0, "integralLimit_max": 100.0,
                        "outLim_min": 20.0, "outLim_max": 100.0,
                    },
                },
            },
        },
    },
}


@given('存在一個有效的 JSON 設定檔包含:')
def step_valid_config(context):
    context._json_config = VALID_CONFIG


@given('存在一個 JSON 設定檔包含 Stepwise 控制器')
def step_stepwise_config(context):
    context._json_config = STEPWISE_CONFIG


@when('系統載入該設定檔')
def step_load_json(context):
    config = context._json_config
    context.sensor_manager = SensorManager()
    context.sensor_configs = build_sensors_from_json(
        config.get("sensors", {}), context.sensor_manager
    )
    context.zones = build_zones_from_json(
        config.get("zones", {}), context.sensor_manager
    )


@when('嘗試載入不存在的設定檔 "{path}"')
def step_load_missing(context, path):
    try:
        load_config(path)
    except FileNotFoundError as e:
        context.caught_exception = e


@given('存在一個 Thermal 控制器配置但 inputs 為空')
def step_empty_thermal_inputs(context):
    context._empty_inputs = True


@when('嘗試建立該控制器')
def step_build_empty_controller(context):
    try:
        ThermalController.create(
            owner=None, controller_id="test", inputs=[],
            setpoint=70.0,
            pid_config=PidConfig(ts=1.0, proportional_coeff=1.0,
                                 out_lim=Limits(min=0, max=100)),
            thermal_type=ThermalType.ABSOLUTE,
        )
    except ValueError as e:
        context.caught_exception = e


# ----------- Assertions -----------

@then('應該建立 {count:d} 個感測器')
def step_assert_sensor_count(context, count):
    actual = len(context.sensor_configs)
    assert actual == count, f"期望 {count} 個感測器, 實際 {actual}"


@then('應該建立 {count:d} 個 Zone')
def step_assert_zone_count(context, count):
    actual = len(context.zones)
    assert actual == count, f"期望 {count} 個 Zone, 實際 {actual}"


@then('Zone 0 應該包含 Thermal 控制器')
def step_assert_has_thermal(context):
    zone = context.zones[0]
    assert len(zone._thermals) > 0, "Zone 0 沒有 Thermal 控制器"


@then('Zone 0 應該包含 Fan 控制器')
def step_assert_has_fan(context):
    zone = context.zones[0]
    assert len(zone._fans) > 0, "Zone 0 沒有 Fan 控制器"


@then('Zone 0 應該包含 Stepwise 控制器')
def step_assert_has_stepwise(context):
    zone = context.zones[0]
    has_stepwise = any(isinstance(c, StepwiseController) for c in zone._thermals)
    assert has_stepwise, "Zone 0 沒有 Stepwise 控制器"


@then('感測器 "{name}" 應該是 SimulatedFan 類型')
def step_assert_is_fan(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    assert isinstance(sensor, SimulatedFan), \
        f"{name} 應該是 SimulatedFan, 實際是 {type(sensor).__name__}"


@then('感測器 "{name}" 應該是 SimulatedSensor 類型')
def step_assert_is_sensor(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    assert isinstance(sensor, SimulatedSensor), \
        f"{name} 應該是 SimulatedSensor, 實際是 {type(sensor).__name__}"


@then('應該拋出 FileNotFoundError')
def step_assert_file_not_found(context):
    assert isinstance(context.caught_exception, FileNotFoundError), \
        f"期望 FileNotFoundError, 實際 {type(context.caught_exception)}"


@then('應該拋出 ValueError 並提示缺少輸入')
def step_assert_value_error(context):
    assert isinstance(context.caught_exception, ValueError), \
        f"期望 ValueError, 實際 {type(context.caught_exception)}"
