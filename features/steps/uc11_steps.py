"""
UC11 — Thermal 計算類型選擇 (Strategy) 的 step definitions
"""
from behave import given, when, then

from pid_control.conf import SensorInput, get_thermal_type
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.ec.pid import Limits, PidConfig


@given('Zone 有一個 "{type_str}" 類型 Thermal PID 控制器 "{ctrl_id}"，目標值 {setpoint:g}')
def step_add_typed_thermal(context, type_str, ctrl_id, setpoint):
    thermal_type = get_thermal_type(type_str)
    inputs = [SensorInput(name=n) for n in context.zone._thermal_inputs]
    pid_config = PidConfig(
        ts=1.0, proportional_coeff=100.0, integral_coeff=2.0,
        integral_limit=Limits(min=0.0, max=10000.0),
        out_lim=Limits(min=3000.0, max=10000.0),
    )
    controller = ThermalController.create(
        context.zone, ctrl_id, inputs, setpoint, pid_config, thermal_type)
    context.zone.add_thermal_pid(controller)
    context._last_thermal_controller = controller


@given('感測器 "{name}" 設定 TempToMargin 轉換，Tjmax 為 {tjmax:g}')
def step_set_temp_to_margin(context, name, tjmax):
    ctrl = context._last_thermal_controller
    for si in ctrl._inputs:
        if si.name == name:
            si.convert_temp_to_margin = True
            si.convert_margin_zero = tjmax
            break


@when('執行一次 Thermal 控制計算')
def step_run_thermal(context):
    zone = context.zone
    zone.initialize_cache()
    zone.update_sensors()
    zone.clear_set_points()
    zone.clear_rpm_ceilings()
    ctrl = context._last_thermal_controller
    context.thermal_input_value = ctrl.input_proc()
    zone.process_thermals()
    zone.determine_max_set_point_request()


@when('嘗試建立類型為 "{type_str}" 的 Thermal 控制器')
def step_build_unknown_thermal(context, type_str):
    try:
        get_thermal_type(type_str)
    except ValueError as e:
        context.caught_exception = e


@then('Thermal PID 輸入值應為最大值 {expected:g}')
def step_assert_thermal_max(context, expected):
    actual = context.thermal_input_value
    assert abs(actual - expected) < 0.01, f"期望 {expected}, 實際 {actual}"


@then('Thermal PID 輸入值應為最小值 {expected:g}')
def step_assert_thermal_min(context, expected):
    actual = context.thermal_input_value
    assert abs(actual - expected) < 0.01, f"期望 {expected}, 實際 {actual}"


@then('Thermal PID 輸入值應為加總 {expected:g}')
def step_assert_thermal_sum(context, expected):
    actual = context.thermal_input_value
    assert abs(actual - expected) < 0.01, f"期望 {expected}, 實際 {actual}"
