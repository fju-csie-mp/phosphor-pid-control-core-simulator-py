"""
UC6 — JSON 設定檔載入的 step definitions
"""
from behave import given, when, then

from pid_control.config_loader import (
    build_sensors_from_json, build_zones_from_json, load_config,
)
from pid_control.conf import ThermalType
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.controllers.stepwise_controller import StepwiseController
from pid_control.ec.pid import Limits, PidConfig
from pid_control.sensors.sensor import SensorManager, SimulatedFan, SimulatedSensor


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
            "zone_config": {"minThermalOutput": 3000.0, "failsafePercent": 75.0},
            "pids": {
                "thermal_cpu": {
                    "type": "temp", "inputs": ["temp_cpu0", "temp_cpu1"],
                    "setpoint": 70.0,
                    "pid": {"samplePeriod": 1.0, "proportionalCoeff": 100.0,
                            "integralCoeff": 2.0,
                            "integralLimit_min": 0, "integralLimit_max": 10000,
                            "outLim_min": 3000, "outLim_max": 10000},
                },
                "fan_pid": {
                    "type": "fan", "inputs": ["fan0", "fan1"],
                    "pid": {"samplePeriod": 0.1, "proportionalCoeff": 0.01,
                            "integralCoeff": 0.001,
                            "integralLimit_min": 0, "integralLimit_max": 100,
                            "outLim_min": 20, "outLim_max": 100},
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
                    "type": "stepwise", "inputs": ["temp_cpu0"],
                    "stepwise": {"reading": [30, 40, 50, 60],
                                 "output": [2000, 4000, 6000, 8000]},
                },
                "fan_pid": {
                    "type": "fan", "inputs": ["fan0"],
                    "pid": {"samplePeriod": 0.1, "proportionalCoeff": 0.01,
                            "integralCoeff": 0.001,
                            "integralLimit_min": 0, "integralLimit_max": 100,
                            "outLim_min": 20, "outLim_max": 100},
                },
            },
        },
    },
}


# --- Given ---

@given('一個包含 2 個溫度感測器、2 個風扇、1 個 Zone 的 JSON 設定檔')
def step_valid_config(context):
    context._json_config = VALID_CONFIG


@given('一個包含 Stepwise 控制器的 JSON 設定檔')
def step_stepwise_config(context):
    context._json_config = STEPWISE_CONFIG


# --- When ---

@when('載入該設定檔')
def step_load_json(context):
    config = context._json_config
    context.sensor_manager = SensorManager()
    context.sensor_configs = build_sensors_from_json(
        config.get("sensors", {}), context.sensor_manager)
    context.zones = build_zones_from_json(
        config.get("zones", {}), context.sensor_manager)


@when('嘗試載入不存在的設定檔 "{path}"')
def step_load_missing(context, path):
    try:
        load_config(path)
    except FileNotFoundError as e:
        context.caught_exception = e


@when('嘗試建立一個沒有輸入感測器的 Thermal 控制器')
def step_build_empty_thermal(context):
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


# --- Then ---

@then('應建立 {count:d} 個感測器')
def step_assert_sensor_count(context, count):
    actual = len(context.sensor_configs)
    assert actual == count, f"期望 {count}, 實際 {actual}"


@then('應建立 {count:d} 個 Zone')
def step_assert_zone_count(context, count):
    actual = len(context.zones)
    assert actual == count, f"期望 {count}, 實際 {actual}"


@then('Zone 0 應包含 Thermal 控制器')
def step_assert_has_thermal(context):
    assert len(context.zones[0]._thermals) > 0


@then('Zone 0 應包含 Fan 控制器')
def step_assert_has_fan(context):
    assert len(context.zones[0]._fans) > 0


@then('Zone 0 應包含 Stepwise 控制器')
def step_assert_has_stepwise(context):
    has = any(isinstance(c, StepwiseController) for c in context.zones[0]._thermals)
    assert has, "Zone 0 沒有 Stepwise 控制器"


@then('感測器 "{name}" 應為 SimulatedFan 類型')
def step_assert_is_fan(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    assert isinstance(sensor, SimulatedFan), f"實際是 {type(sensor).__name__}"


@then('感測器 "{name}" 應為 SimulatedSensor 類型')
def step_assert_is_sensor(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    assert isinstance(sensor, SimulatedSensor), f"實際是 {type(sensor).__name__}"


@then('應拋出 FileNotFoundError')
def step_assert_fnf(context):
    assert isinstance(context.caught_exception, FileNotFoundError)


@then('應拋出 ValueError')
def step_assert_value_error(context):
    assert isinstance(context.caught_exception, ValueError)
