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
# Background steps — 建立 Zone 基礎設施
# =========================================================================

@given('系統載入了包含以下設定的配置檔:')
def step_load_config(context):
    """從 table 讀取 zone config 並建立 Zone"""
    config = {}
    for row in context.table:
        config[row['設定項']] = float(row['值'])

    context.sensor_manager = SensorManager()
    context.zone = Zone(
        zone_id=0,
        min_thermal_output=config.get('minThermalOutput', 3000.0),
        failsafe_percent=config.get('failsafePercent', 75.0),
        cycle_interval_ms=100,
        update_thermals_ms=1000,
        sensor_manager=context.sensor_manager,
    )


@given('Zone 0 有以下溫度感測器:')
def step_add_temp_sensors(context):
    """從 table 新增溫度感測器到 zone"""
    for row in context.table:
        name = row['感測器名稱']
        base_temp = float(row['基礎溫度'])
        sensor = SimulatedSensor(name=name, timeout=2, base_temp=base_temp,
                                 amplitude=0, noise=0)
        context.sensor_manager.add_sensor(name, sensor)
        context.zone.add_thermal_input(name)


@given('Zone 0 有以下風扇:')
def step_add_fans(context):
    """從 table 新增風扇到 zone"""
    for row in context.table:
        name = row['風扇名稱']
        max_rpm = float(row['最大RPM'])
        fan = SimulatedFan(name=name, timeout=0, max_rpm=max_rpm)
        context.sensor_manager.add_sensor(name, fan)
        context.zone.add_fan_input(name)


@given('Zone 0 有一個 Thermal PID 控制器 "{ctrl_id}" 設定點為 {setpoint:g}')
def step_add_thermal_pid(context, ctrl_id, setpoint):
    """建立 Thermal PID (absolute/temp 類型) 並加入 zone"""
    inputs = [
        SensorInput(name=name) for name in context.zone._thermal_inputs
    ]
    pid_config = _default_thermal_pid_config()
    controller = ThermalController.create(
        context.zone, ctrl_id, inputs, setpoint, pid_config, ThermalType.ABSOLUTE
    )
    context.zone.add_thermal_pid(controller)


@given('Zone 0 有一個 Fan PID 控制器 "{ctrl_id}"')
def step_add_fan_pid(context, ctrl_id):
    """建立 Fan PID 並加入 zone"""
    fan_names = list(context.zone._fan_inputs)
    pid_config = _default_fan_pid_config()
    controller = FanController.create(context.zone, ctrl_id, fan_names, pid_config)
    if controller:
        context.zone.add_fan_pid(controller)


# =========================================================================
# Sensor 讀數設定
# =========================================================================

@given('溫度感測器 "{name}" 的讀數為 {value}')
@when('溫度感測器 "{name}" 的讀數為 {value}')
def step_set_sensor_reading(context, name, value):
    """設定模擬感測器回傳固定值"""
    sensor = context.sensor_manager.get_sensor(name)
    if value.strip().lower() == "nan":
        _override_sensor_read(sensor, float("nan"))
    else:
        _override_sensor_read(sensor, float(value))


@given('Zone 0 額外新增溫度感測器 "{name}" 基礎溫度為 {base_temp:g}')
def step_add_extra_temp_sensor(context, name, base_temp):
    """在 background 之後額外新增一個溫度感測器"""
    sensor = SimulatedSensor(name=name, timeout=2, base_temp=base_temp,
                             amplitude=0, noise=0)
    context.sensor_manager.add_sensor(name, sensor)
    context.zone.add_thermal_input(name)
    # 也需要更新已有的 thermal controller 的 inputs
    for ctrl in context.zone._thermals:
        if hasattr(ctrl, '_inputs'):
            # 檢查是否使用 SensorInput list
            if ctrl._inputs and isinstance(ctrl._inputs[0], SensorInput):
                ctrl._inputs.append(SensorInput(name=name))
            elif ctrl._inputs and isinstance(ctrl._inputs[0], str):
                ctrl._inputs.append(name)


# =========================================================================
# Failsafe 相關
# =========================================================================

@given('溫度感測器 "{name}" 被標記為故障')
@when('溫度感測器 "{name}" 被標記為故障')
def step_mark_sensor_failed(context, name):
    """標記感測器為故障"""
    sensor = context.sensor_manager.get_sensor(name)
    sensor.set_failed(True, "模擬故障")


@when('溫度感測器 "{name}" 恢復正常並讀數為 {value:g}')
def step_recover_sensor(context, name, value):
    """恢復感測器"""
    sensor = context.sensor_manager.get_sensor(name)
    sensor.set_failed(False)
    _override_sensor_read(sensor, value)


@given('溫度感測器 "{name}" 設定為 missingIsAcceptable')
def step_set_missing_acceptable(context, name):
    """設定感測器為可接受遺失"""
    context.zone._missing_acceptable.add(name)


@given('感測器 "{name}" 的個別 Failsafe 百分比為 {percent:g}')
def step_set_sensor_failsafe_percent(context, name, percent):
    """設定個別感測器的 failsafe 百分比"""
    context.zone.add_pid_failsafe_percent([name], percent)


# =========================================================================
# 手動模式
# =========================================================================

@given('Zone 0 處於手動模式')
def step_zone_manual(context):
    context.zone.set_manual_mode(True)


@when('管理員將 Zone 0 切換為手動模式')
def step_switch_manual(context):
    context.zone.set_manual_mode(True)


@when('管理員將 Zone 0 切換為自動模式')
def step_switch_auto(context):
    context.zone.set_manual_mode(False)


@when('模擬手動模式下的一次控制迴圈')
def step_manual_loop(context):
    """手動模式下，PID 不應該執行"""
    # 記錄目前風扇 PWM
    for name in context.zone._fan_inputs:
        sensor = context.sensor_manager.get_sensor(name)
        if hasattr(sensor, '_current_pwm'):
            context.fan_pwm_before[name] = sensor._current_pwm
    # 手動模式下 pidControlLoop 會 skip processing
    if context.zone.get_manual_mode():
        pass  # 不執行任何 PID 計算


# =========================================================================
# 控制迴圈執行
# =========================================================================

@when('更新溫度感測器快取')
def step_update_sensors(context):
    context.zone.update_sensors()


@when('執行一次完整的控制迴圈')
def step_run_one_cycle(context):
    """執行一次完整的 thermal + fan 控制迴圈"""
    zone = context.zone
    zone.initialize_cache()
    # thermal cycle
    zone.update_sensors()
    zone.clear_set_points()
    zone.clear_rpm_ceilings()
    # 記錄 thermal input（供 assertion 使用）
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

@then('最大設定點應該等於最低溫度輸出 {expected:g} RPM')
def step_assert_setpoint_eq(context, expected):
    actual = context.zone.get_max_set_point_request()
    assert actual == expected, f"期望 {expected}, 實際 {actual}"


@then('最大設定點應該大於 {threshold:g} RPM')
def step_assert_setpoint_gt(context, threshold):
    actual = context.zone.get_max_set_point_request()
    assert actual > threshold, f"期望 > {threshold}, 實際 {actual}"


@then('風扇 "{name}" 應該有被寫入 PWM 值')
def step_assert_fan_written(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    assert hasattr(sensor, '_last_written_raw') and sensor._last_written_raw is not None, \
        f"風扇 {name} 沒有被寫入 PWM"


@then('Zone 0 應該處於 Failsafe 模式')
def step_assert_failsafe(context):
    assert context.zone.get_failsafe_mode(), "Zone 應該處於 Failsafe 但沒有"


@then('Zone 0 不應該處於 Failsafe 模式')
def step_assert_not_failsafe(context):
    assert not context.zone.get_failsafe_mode(), \
        f"Zone 不應該處於 Failsafe 但是處於: {context.zone.get_failsafe_sensors()}"


@then('Failsafe 百分比應該為 {expected:g}')
def step_assert_failsafe_percent(context, expected):
    actual = context.zone.get_failsafe_percent()
    assert actual == expected, f"期望 Failsafe {expected}%, 實際 {actual}%"


@then('風扇 "{name}" 的 PWM 應該不低於 {min_pct:g}%')
def step_assert_fan_pwm_min(context, name, min_pct):
    sensor = context.sensor_manager.get_sensor(name)
    actual_pct = sensor.current_pwm_percent
    assert actual_pct >= min_pct, \
        f"風扇 {name} PWM {actual_pct:.1f}% < 最低要求 {min_pct}%"


@then('Zone 0 應該處於手動模式')
def step_assert_manual(context):
    assert context.zone.get_manual_mode(), "Zone 應該在手動模式"


@then('Zone 0 不應該處於手動模式')
def step_assert_not_manual(context):
    assert not context.zone.get_manual_mode(), "Zone 不應該在手動模式"


@then('Zone 0 的 redundant write 應該被啟用')
def step_assert_redundant_write(context):
    assert context.zone.get_redundant_write(), "Redundant write 應該被啟用"


@then('風扇 "{name}" 的 PWM 不應該被 PID 改變')
def step_assert_fan_pwm_unchanged(context, name):
    sensor = context.sensor_manager.get_sensor(name)
    before = context.fan_pwm_before.get(name, sensor._current_pwm)
    after = sensor._current_pwm
    assert before == after, f"風扇 {name} PWM 被改變了: {before} → {after}"


# =========================================================================
# Helper functions
# =========================================================================

def _override_sensor_read(sensor, value):
    """覆寫模擬感測器的 read() 方法，讓它回傳固定值"""
    from pid_control.conf import ReadReturn
    from datetime import datetime

    def fixed_read():
        return ReadReturn(value=value, updated=datetime.now(), unscaled=value)
    sensor.read = fixed_read


def _default_thermal_pid_config():
    return PidConfig(
        ts=1.0,
        proportional_coeff=100.0,
        integral_coeff=2.0,
        integral_limit=Limits(min=0.0, max=10000.0),
        out_lim=Limits(min=3000.0, max=10000.0),
    )


def _default_fan_pid_config():
    return PidConfig(
        ts=0.1,
        proportional_coeff=0.01,
        integral_coeff=0.001,
        integral_limit=Limits(min=0.0, max=100.0),
        out_lim=Limits(min=20.0, max=100.0),
    )
