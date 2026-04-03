"""
共用的 step definitions — 建立 Zone / Sensor / Controller 的基礎步驟
"""
import math

from behave import given, when, then

from pid_control.conf import (
    SensorInput, ThermalType, ValueCacheEntry, get_thermal_type,
)
from pid_control.controllers.fan_controller import FanController
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.ec.pid import Limits, PidConfig
from pid_control.sensors.sensor import SensorManager, SimulatedFan, SimulatedSensor
from pid_control.zone import Zone


# =========================================================================
# Background — 建立 Zone 基礎設施
# =========================================================================

@given('一個 Zone，最低轉速 {min_rpm:g} RPM，Failsafe 百分比 {failsafe:g}%')
def step_create_zone(context, min_rpm, failsafe):
    context.sensor_manager = SensorManager()
    context.zone = Zone(
        zone_id=0,
        min_thermal_output=min_rpm,
        failsafe_percent=failsafe,
        cycle_interval_ms=100,
        update_thermals_ms=1000,
        sensor_manager=context.sensor_manager,
    )


@given('Zone 有溫度感測器 "{name}"')
def step_add_temp_sensor(context, name):
    sensor = SimulatedSensor(name=name, timeout=2, base_temp=50.0,
                             amplitude=0, noise=0)
    context.sensor_manager.add_sensor(name, sensor)
    context.zone.add_thermal_input(name)


@given('Zone 額外新增溫度感測器 "{name}"')
def step_add_extra_temp_sensor(context, name):
    sensor = SimulatedSensor(name=name, timeout=2, base_temp=50.0,
                             amplitude=0, noise=0)
    context.sensor_manager.add_sensor(name, sensor)
    context.zone.add_thermal_input(name)
    # 更新已有 thermal controller 的 inputs
    for ctrl in context.zone._thermals:
        if hasattr(ctrl, '_inputs'):
            if ctrl._inputs and isinstance(ctrl._inputs[0], SensorInput):
                ctrl._inputs.append(SensorInput(name=name))
            elif ctrl._inputs and isinstance(ctrl._inputs[0], str):
                ctrl._inputs.append(name)


@given('Zone 有風扇 "{name}"，最大轉速 {max_rpm:g} RPM')
def step_add_fan(context, name, max_rpm):
    fan = SimulatedFan(name=name, timeout=0, max_rpm=max_rpm)
    context.sensor_manager.add_sensor(name, fan)
    context.zone.add_fan_input(name)


@given('Zone 有 Thermal PID 控制器，目標溫度 {setpoint:g} 度')
def step_add_thermal_pid(context, setpoint):
    inputs = [SensorInput(name=n) for n in context.zone._thermal_inputs]
    pid_config = _default_thermal_pid_config()
    controller = ThermalController.create(
        context.zone, "thermal_pid", inputs, setpoint,
        pid_config, ThermalType.ABSOLUTE,
    )
    context.zone.add_thermal_pid(controller)


@given('Zone 有 Fan PID 控制器')
def step_add_fan_pid(context):
    fan_names = list(context.zone._fan_inputs)
    pid_config = _default_fan_pid_config()
    controller = FanController.create(context.zone, "fan_pid", fan_names, pid_config)
    if controller:
        context.zone.add_fan_pid(controller)


# =========================================================================
# 感測器讀數
# =========================================================================

@given('感測器 "{name}" 讀數為 {value}')
@when('感測器 "{name}" 讀數為 {value}')
def step_set_sensor_reading(context, name, value):
    sensor = context.sensor_manager.get_sensor(name)
    if value.strip().lower() == "nan":
        _override_sensor_read(sensor, float("nan"))
    else:
        _override_sensor_read(sensor, float(value))


# =========================================================================
# Failsafe 相關
# =========================================================================

@given('感測器 "{name}" 標記為故障')
@when('感測器 "{name}" 標記為故障')
def step_mark_sensor_failed(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    sensor.set_failed(True, "模擬故障")


@when('感測器 "{name}" 恢復正常，讀數為 {value:g}')
def step_recover_sensor(context, name, value):
    sensor = context.sensor_manager.get_sensor(name)
    sensor.set_failed(False)
    _override_sensor_read(sensor, value)


@given('感測器 "{name}" 設定為 missingIsAcceptable')
def step_set_missing_acceptable(context, name):
    context.zone._missing_acceptable.add(name)


@given('感測器 "{name}" 的 Failsafe 百分比設為 {percent:g}')
def step_set_sensor_failsafe_percent(context, name, percent):
    context.zone.add_pid_failsafe_percent([name], percent)


# =========================================================================
# 手動模式
# =========================================================================

@given('Zone 處於手動模式')
def step_zone_manual(context):
    context.zone.set_manual_mode(True)


@when('切換為手動模式')
def step_switch_manual(context):
    context.zone.set_manual_mode(True)


@when('切換為自動模式')
def step_switch_auto(context):
    context.zone.set_manual_mode(False)


@when('模擬手動模式下的一次控制迴圈')
def step_manual_loop(context):
    for name in context.zone._fan_inputs:
        sensor = context.sensor_manager.get_sensor(name)
        if hasattr(sensor, '_current_pwm'):
            context.fan_pwm_before[name] = sensor._current_pwm
    # 手動模式下不執行任何 PID 計算


# =========================================================================
# 控制迴圈
# =========================================================================

@when('更新感測器快取')
def step_update_sensors(context):
    context.zone.update_sensors()


@when('執行一次完整的控制迴圈')
def step_run_one_cycle(context):
    zone = context.zone
    zone.initialize_cache()
    # thermal cycle
    zone.update_sensors()
    zone.clear_set_points()
    zone.clear_rpm_ceilings()
    for ctrl in zone._thermals:
        if hasattr(ctrl, 'input_proc'):
            context.thermal_input_value = ctrl.input_proc()
    zone.process_thermals()
    zone.determine_max_set_point_request()
    # fan cycle
    zone.update_fan_telemetry()
    zone.process_fans()


# =========================================================================
# Assertions
# =========================================================================

@then('最大 Setpoint 應為 {expected:g} RPM')
def step_assert_setpoint_eq(context, expected):
    actual = context.zone.get_max_set_point_request()
    assert actual == expected, f"期望 {expected}, 實際 {actual}"


@then('最大 Setpoint 應大於 {threshold:g} RPM')
def step_assert_setpoint_gt(context, threshold):
    actual = context.zone.get_max_set_point_request()
    assert actual > threshold, f"期望 > {threshold}, 實際 {actual}"


@then('風扇 "{name}" 應該有被寫入 PWM 值')
def step_assert_fan_written(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    assert hasattr(sensor, '_last_written_raw') and sensor._last_written_raw is not None, \
        f"風扇 {name} 沒有被寫入 PWM"


@then('Zone 應處於 Failsafe 模式')
def step_assert_failsafe(context):
    assert context.zone.get_failsafe_mode(), "Zone 應處於 Failsafe 但沒有"


@then('Zone 不應處於 Failsafe 模式')
def step_assert_not_failsafe(context):
    assert not context.zone.get_failsafe_mode(), \
        f"Zone 不應處於 Failsafe, 故障感測器: {context.zone.get_failsafe_sensors()}"


@then('Failsafe 百分比應為 {expected:g}')
def step_assert_failsafe_percent(context, expected):
    actual = context.zone.get_failsafe_percent()
    assert actual == expected, f"期望 {expected}%, 實際 {actual}%"


@then('風扇 "{name}" 的 PWM 應不低於 {min_pct:g}%')
def step_assert_fan_pwm_min(context, name, min_pct):
    sensor = context.sensor_manager.get_sensor(name)
    actual_pct = sensor.current_pwm_percent
    assert actual_pct >= min_pct, \
        f"風扇 {name} PWM {actual_pct:.1f}% < 最低要求 {min_pct}%"


@then('Zone 應處於手動模式')
def step_assert_manual(context):
    assert context.zone.get_manual_mode()


@then('Zone 不應處於手動模式')
def step_assert_not_manual(context):
    assert not context.zone.get_manual_mode()


@then('Redundant Write 應被啟用')
def step_assert_redundant_write(context):
    assert context.zone.get_redundant_write()


@then('風扇 "{name}" 的 PWM 不應被 PID 改變')
def step_assert_fan_pwm_unchanged(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    before = context.fan_pwm_before.get(name, sensor._current_pwm)
    assert before == sensor._current_pwm, \
        f"風扇 PWM 被改變: {before} → {sensor._current_pwm}"


# =========================================================================
# Helpers
# =========================================================================

def _override_sensor_read(sensor, value):
    from pid_control.conf import ReadReturn
    from datetime import datetime
    def fixed_read():
        return ReadReturn(value=value, updated=datetime.now(), unscaled=value)
    sensor.read = fixed_read


def _default_thermal_pid_config():
    return PidConfig(
        ts=1.0, proportional_coeff=100.0, integral_coeff=2.0,
        integral_limit=Limits(min=0.0, max=10000.0),
        out_lim=Limits(min=3000.0, max=10000.0),
    )


def _default_fan_pid_config():
    return PidConfig(
        ts=0.1, proportional_coeff=0.01, integral_coeff=0.001,
        integral_limit=Limits(min=0.0, max=100.0),
        out_lim=Limits(min=20.0, max=100.0),
    )
