"""
UC11 — Thermal 計算類型選擇 (Strategy) 的 step definitions
"""
import math

from behave import given, when, then

from pid_control.conf import SensorInput, ThermalType, get_thermal_type
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.ec.pid import Limits, PidConfig


@given('Zone 0 有一個類型為 "{type_str}" 的 Thermal PID 控制器 "{ctrl_id}" 設定點為 {setpoint:g}')
def step_add_typed_thermal(context, type_str, ctrl_id, setpoint):
    """建立指定類型的 Thermal PID 控制器"""
    thermal_type = get_thermal_type(type_str)
    inputs = [
        SensorInput(name=name)
        for name in context.zone._thermal_inputs
    ]
    pid_config = PidConfig(
        ts=1.0, proportional_coeff=100.0, integral_coeff=2.0,
        integral_limit=Limits(min=0.0, max=10000.0),
        out_lim=Limits(min=3000.0, max=10000.0),
    )
    controller = ThermalController.create(
        context.zone, ctrl_id, inputs, setpoint, pid_config, thermal_type
    )
    context.zone.add_thermal_pid(controller)
    context._last_thermal_controller = controller


@given('感測器 "{name}" 設定了 TempToMargin 轉換 Tjmax 為 {tjmax:g}')
def step_set_temp_to_margin(context, name, tjmax):
    """設定某感測器的 TempToMargin 轉換"""
    # 找到最後一個 thermal controller 並修改其 inputs
    ctrl = context._last_thermal_controller
    for si in ctrl._inputs:
        if si.name == name:
            si.convert_temp_to_margin = True
            si.convert_margin_zero = tjmax
            break


@when('執行一次 Thermal 控制計算')
def step_run_thermal(context):
    """只執行 thermal 部分"""
    zone = context.zone
    zone.initialize_cache()
    zone.update_sensors()
    zone.clear_set_points()
    zone.clear_rpm_ceilings()

    # 記錄 input_proc 的結果
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


@then('Thermal PID 的輸入值應該是所有感測器中的最大值 {expected:g}')
def step_assert_thermal_max(context, expected):
    actual = context.thermal_input_value
    assert abs(actual - expected) < 0.01, \
        f"期望最大值 {expected}, 實際 {actual}"


@then('Thermal PID 的輸入值應該是所有感測器中的最小值 {expected:g}')
def step_assert_thermal_min(context, expected):
    actual = context.thermal_input_value
    assert abs(actual - expected) < 0.01, \
        f"期望最小值 {expected}, 實際 {actual}"


@then('Thermal PID 的輸入值應該是所有感測器的加總 {expected:g}')
def step_assert_thermal_sum(context, expected):
    actual = context.thermal_input_value
    assert abs(actual - expected) < 0.01, \
        f"期望加總 {expected}, 實際 {actual}"


@then('應該拋出 ValueError')
def step_assert_value_error_generic(context):
    assert isinstance(context.caught_exception, ValueError), \
        f"期望 ValueError, 實際 {type(context.caught_exception)}"
