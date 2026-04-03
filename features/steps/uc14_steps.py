"""
UC14 — Stepwise 階梯控制的 step definitions
"""
import math

from behave import given, when, then

from pid_control.ec.stepwise import StepwiseInfo, stepwise, MAX_STEPWISE_POINTS
from pid_control.controllers.stepwise_controller import StepwiseController
from pid_control.sensors.sensor import SensorManager, SimulatedSensor, SimulatedFan
from pid_control.zone import Zone


def _build_stepwise_info(table, positive_hyst=0.0, negative_hyst=0.0,
                         is_ceiling=False):
    """從 behave table 建立 StepwiseInfo"""
    reading = [float("nan")] * MAX_STEPWISE_POINTS
    output = [float("nan")] * MAX_STEPWISE_POINTS
    for i, row in enumerate(table):
        reading[i] = float(row['溫度閾值'])
        output[i] = float(row['輸出值'])
    return StepwiseInfo(
        ts=1.0, reading=reading, output=output,
        positive_hysteresis=positive_hyst,
        negative_hysteresis=negative_hyst,
        is_ceiling=is_ceiling,
    )


@given('存在一個 Stepwise 控制器設定如下:')
def step_create_stepwise(context):
    context._stepwise_info = _build_stepwise_info(context.table)
    context._stepwise_controller = None  # 純演算法測試不需要 controller


@given('存在一個 isCeiling 為 true 的 Stepwise 控制器設定如下:')
def step_create_ceiling_stepwise(context):
    context._stepwise_info = _build_stepwise_info(context.table, is_ceiling=True)


@given('正向遲滯為 {pos:g} 負向遲滯為 {neg:g}')
def step_set_hysteresis(context, pos, neg):
    context._stepwise_info.positive_hysteresis = pos
    context._stepwise_info.negative_hysteresis = neg
    # 建立一個完整的 StepwiseController 來測試遲滯邏輯
    mgr = SensorManager()
    sensor = SimulatedSensor(name="test_sensor", amplitude=0, noise=0)
    mgr.add_sensor("test_sensor", sensor)
    zone = Zone(zone_id=99, min_thermal_output=0, failsafe_percent=75,
                cycle_interval_ms=100, update_thermals_ms=1000,
                sensor_manager=mgr)
    zone.add_thermal_input("test_sensor")
    ctrl = StepwiseController.create(
        zone, "sw_test", ["test_sensor"], context._stepwise_info
    )
    context._stepwise_controller = ctrl
    context._sw_zone = zone
    context._sw_mgr = mgr


@given('系統有一個 Zone 配置')
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
        zone, "sw_ceiling", ["test_sensor"], context._stepwise_info
    )
    zone.add_thermal_pid(ctrl)
    context._sw_zone = zone
    context._sw_mgr = mgr
    context._stepwise_controller = ctrl


@when('輸入溫度為 {temp:g}')
def step_stepwise_input(context, temp):
    """對純 Stepwise 演算法做查表"""
    context.stepwise_output = stepwise(context._stepwise_info, temp)


@when('輸入溫度變為 {temp:g}')
def step_stepwise_input_change(context, temp):
    """透過 StepwiseController 測試遲滯"""
    from pid_control.conf import ReadReturn, ValueCacheEntry
    from datetime import datetime

    ctrl = context._stepwise_controller
    zone = context._sw_zone
    mgr = context._sw_mgr

    # 覆寫感測器讀數
    sensor = mgr.get_sensor("test_sensor")
    def fixed_read():
        return ReadReturn(value=temp, updated=datetime.now(), unscaled=temp)
    sensor.read = fixed_read

    zone._cached_values["test_sensor"] = ValueCacheEntry(scaled=temp, unscaled=temp)
    ctrl.process()
    context.stepwise_output = ctrl._last_output


@when('輸入溫度為 {temp:g} 並執行 Stepwise 控制')
def step_stepwise_with_zone(context, temp):
    from pid_control.conf import ReadReturn, ValueCacheEntry
    from datetime import datetime

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
            stepwise_info=StepwiseInfo(),
        )
    except ValueError as e:
        context.caught_exception = e


# ----------- Assertions -----------

@then('Stepwise 輸出應該為 {expected:g}')
def step_assert_stepwise_output(context, expected):
    actual = context.stepwise_output
    assert abs(actual - expected) < 0.01, \
        f"期望 Stepwise 輸出 {expected}, 實際 {actual}"


@then('Stepwise 輸出應該維持為 {expected:g}')
def step_assert_stepwise_unchanged(context, expected):
    actual = context.stepwise_output
    assert abs(actual - expected) < 0.01, \
        f"期望 Stepwise 維持 {expected}, 實際 {actual}"


@then('Zone 的 RPM ceiling 應該包含 {expected:g}')
def step_assert_rpm_ceiling(context, expected):
    zone = context._sw_zone
    assert expected in zone._rpm_ceilings, \
        f"期望 ceiling 包含 {expected}, 實際 {zone._rpm_ceilings}"
