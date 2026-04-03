"""
UC14 — Stepwise 階梯控制的 step definitions
"""
import math

from behave import given, when, then

from pid_control.conf import ReadReturn, ValueCacheEntry
from pid_control.ec.stepwise import StepwiseInfo, stepwise, MAX_STEPWISE_POINTS
from pid_control.controllers.stepwise_controller import StepwiseController
from pid_control.sensors.sensor import SensorManager, SimulatedSensor, SimulatedFan
from pid_control.zone import Zone
from datetime import datetime


def _parse_table_string(table_str):
    """解析 '30/2000, 40/4000, 50/6000' 格式的對照表"""
    reading = [float("nan")] * MAX_STEPWISE_POINTS
    output = [float("nan")] * MAX_STEPWISE_POINTS
    pairs = [p.strip() for p in table_str.split(",")]
    for i, pair in enumerate(pairs):
        r, o = pair.split("/")
        reading[i] = float(r)
        output[i] = float(o)
    return reading, output


@given('一個 Stepwise 控制器，溫度對照表為 {table_str}')
def step_create_stepwise(context, table_str):
    reading, output = _parse_table_string(table_str)
    context._stepwise_info = StepwiseInfo(
        ts=1.0, reading=reading, output=output)
    context._stepwise_controller = None


@given('一個 isCeiling 的 Stepwise 控制器，溫度對照表為 {table_str}')
def step_create_ceiling_stepwise(context, table_str):
    reading, output = _parse_table_string(table_str)
    context._stepwise_info = StepwiseInfo(
        ts=1.0, reading=reading, output=output, is_ceiling=True)


@given('遲滯設定為正向 {pos:g}，負向 {neg:g}')
def step_set_hysteresis(context, pos, neg):
    context._stepwise_info.positive_hysteresis = pos
    context._stepwise_info.negative_hysteresis = neg
    # 建立完整的 controller 來測試遲滯
    mgr = SensorManager()
    sensor = SimulatedSensor(name="test_sensor", amplitude=0, noise=0)
    mgr.add_sensor("test_sensor", sensor)
    zone = Zone(zone_id=99, min_thermal_output=0, failsafe_percent=75,
                cycle_interval_ms=100, update_thermals_ms=1000,
                sensor_manager=mgr)
    zone.add_thermal_input("test_sensor")
    ctrl = StepwiseController.create(
        zone, "sw_test", ["test_sensor"], context._stepwise_info)
    context._stepwise_controller = ctrl
    context._sw_zone = zone
    context._sw_mgr = mgr


@given('一個配置好的 Zone')
def step_setup_zone_for_ceiling(context):
    mgr = SensorManager()
    sensor = SimulatedSensor(name="test_sensor", amplitude=0, noise=0)
    fan = SimulatedFan(name="test_fan")
    mgr.add_sensor("test_sensor", sensor)
    mgr.add_sensor("test_fan", fan)
    zone = Zone(zone_id=99, min_thermal_output=0, failsafe_percent=75,
                cycle_interval_ms=100, update_thermals_ms=1000,
                sensor_manager=mgr)
    zone.add_thermal_input("test_sensor")
    zone.add_fan_input("test_fan")
    ctrl = StepwiseController.create(
        zone, "sw_ceiling", ["test_sensor"], context._stepwise_info)
    zone.add_thermal_pid(ctrl)
    context._sw_zone = zone
    context._sw_mgr = mgr


@when('輸入溫度為 {temp:g}')
def step_stepwise_input(context, temp):
    context.stepwise_output = stepwise(context._stepwise_info, temp)


@when('輸入溫度變為 {temp:g}')
def step_stepwise_input_change(context, temp):
    ctrl = context._stepwise_controller
    zone = context._sw_zone
    mgr = context._sw_mgr
    sensor = mgr.get_sensor("test_sensor")

    def fixed_read():
        return ReadReturn(value=temp, updated=datetime.now(), unscaled=temp)
    sensor.read = fixed_read
    zone._cached_values["test_sensor"] = ValueCacheEntry(scaled=temp, unscaled=temp)
    ctrl.process()
    context.stepwise_output = ctrl._last_output


@when('輸入溫度為 {temp:g} 並執行 Stepwise 控制')
def step_stepwise_with_zone(context, temp):
    zone = context._sw_zone
    mgr = context._sw_mgr
    sensor = mgr.get_sensor("test_sensor")

    def fixed_read():
        return ReadReturn(value=temp, updated=datetime.now(), unscaled=temp)
    sensor.read = fixed_read
    zone.initialize_cache()
    zone.update_sensors()
    zone.clear_set_points()
    zone.clear_rpm_ceilings()
    zone.process_thermals()


@when('嘗試建立一個沒有輸入的 Stepwise 控制器')
def step_build_empty_stepwise(context):
    try:
        StepwiseController.create(
            owner=None, controller_id="test", inputs=[],
            stepwise_info=StepwiseInfo())
    except ValueError as e:
        context.caught_exception = e


# --- Assertions ---

@then('Stepwise 輸出應為 {expected:g}')
def step_assert_stepwise_output(context, expected):
    actual = context.stepwise_output
    assert abs(actual - expected) < 0.01, f"期望 {expected}, 實際 {actual}"


@then('Stepwise 輸出應維持為 {expected:g}')
def step_assert_stepwise_unchanged(context, expected):
    actual = context.stepwise_output
    assert abs(actual - expected) < 0.01, f"期望 {expected}, 實際 {actual}"


@then('Zone 的 RPM Ceiling 應包含 {expected:g}')
def step_assert_rpm_ceiling(context, expected):
    zone = context._sw_zone
    assert expected in zone._rpm_ceilings, \
        f"期望包含 {expected}, 實際 {zone._rpm_ceilings}"
