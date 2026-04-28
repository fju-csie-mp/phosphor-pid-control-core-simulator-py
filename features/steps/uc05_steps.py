"""
UC5 — 感測器讀值與健康狀態的 step definitions

純 Sensor 單元測試，不涉及 Zone 或 Controller。
"""
from datetime import datetime

from behave import given, when, then

from pid_control.sensors.sensor import SimulatedFan, SimulatedSensor


# =========================================================================
# Given — 建立 Sensor
# =========================================================================

@given('一個 SimulatedSensor "{name}"，base {base:g}、amplitude {amp:g}、'
       'noise {noise:g}')
def step_create_simulated_sensor(context, name, base, amp, noise):
    sensor = SimulatedSensor(
        name=name, timeout=2,
        base_temp=base, amplitude=amp, noise=noise,
    )
    context._sensors = getattr(context, "_sensors", {})
    context._sensors[name] = sensor


@given('一個 SimulatedFan "{name}"，最大轉速 {max_rpm:g} RPM')
def step_create_simulated_fan(context, name, max_rpm):
    fan = SimulatedFan(name=name, timeout=0, max_rpm=max_rpm)
    context._sensors = getattr(context, "_sensors", {})
    context._sensors[name] = fan


@given('"{name}" 已被標記為故障')
def step_pre_mark_failed(context, name):
    context._sensors[name].set_failed(True, reason="既有故障")


# =========================================================================
# When — 操作 Sensor
# =========================================================================

@when('讀取感測器 "{name}" 一次')
def step_read_sensor_once(context, name):
    sensor = context._sensors[name]
    context._read_result = sensor.read()


@when('對 "{name}" 寫入 PWM {pwm:g}')
def step_write_fan_pwm(context, name, pwm):
    fan = context._sensors[name]
    context._last_raw = fan.write(pwm)


@when('將 "{name}" 標記為故障，原因 "{reason}"')
def step_mark_failed(context, name, reason):
    context._sensors[name].set_failed(True, reason=reason)


@when('將 "{name}" 標記為恢復正常')
def step_mark_recovered(context, name):
    context._sensors[name].set_failed(False)


# =========================================================================
# Then — 斷言
# =========================================================================

@then('讀值應介於 {low:g} 與 {high:g} 之間')
def step_assert_value_range(context, low, high):
    v = context._read_result.value
    assert low <= v <= high, f"讀值 {v} 不在 [{low}, {high}] 範圍內"


@then('讀值的 timestamp 應為當前時間')
def step_assert_timestamp_now(context):
    ts = context._read_result.updated
    delta = abs((datetime.now() - ts).total_seconds())
    assert delta < 1.0, f"timestamp 與當前時間差距 {delta} 秒，過大"


@then('讀值應接近 {expected:g} RPM，誤差容許 {tol:g}')
def step_assert_value_close(context, expected, tol):
    v = context._read_result.value
    assert abs(v - expected) <= tol, \
        f"讀值 {v} 與期望 {expected} 差距超過 {tol}"


@then('感測器 "{name}" 的 get_failed 應為 {expected}')
def step_assert_get_failed(context, name, expected):
    actual = context._sensors[name].get_failed()
    expect_bool = (expected.lower() == "true")
    assert actual is expect_bool, \
        f"get_failed 期望 {expect_bool}，實際 {actual}"


@then('感測器 "{name}" 的 fail_reason 應為 "{expected}"')
def step_assert_fail_reason(context, name, expected):
    actual = context._sensors[name].get_fail_reason()
    assert actual == expected, f"fail_reason 期望 {expected!r}，實際 {actual!r}"
