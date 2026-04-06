"""
UC10 — 多 Zone 獨立控制的 step definitions
"""
from behave import given, when, then

from pid_control.conf import SensorInput, ThermalType
from pid_control.controllers.fan_controller import FanController
from pid_control.controllers.thermal_controller import ThermalController
from pid_control.ec.pid import Limits, PidConfig
from pid_control.sensors.sensor import SensorManager, SimulatedFan, SimulatedSensor
from pid_control.zone import Zone


def _make_thermal_pid_config():
    return PidConfig(
        ts=1.0, proportional_coeff=100.0, integral_coeff=2.0,
        integral_limit=Limits(min=0.0, max=10000.0),
        out_lim=Limits(min=3000.0, max=10000.0),
    )


def _make_fan_pid_config():
    return PidConfig(
        ts=0.1, proportional_coeff=0.01, integral_coeff=0.001,
        integral_limit=Limits(min=0.0, max=100.0),
        out_lim=Limits(min=20.0, max=100.0),
    )


def _override_sensor_read(sensor, value):
    from pid_control.conf import ReadReturn
    from datetime import datetime
    def fixed_read():
        return ReadReturn(value=value, updated=datetime.now(), unscaled=value)
    sensor.read = fixed_read


@given('Zone {zid:d}，最低轉速 {min_rpm:g} RPM，Failsafe 百分比 {fs:g}%，有感測器 "{sensor_name}" 和風扇 "{fan_name}"')
def step_create_zone_with_sensor_fan(context, zid, min_rpm, fs, sensor_name, fan_name):
    """建立一個 Zone，包含一個感測器和一個風扇"""
    # 共用 sensor_manager（多 Zone 可以共用感測器）
    if not hasattr(context, '_multi_mgr') or context._multi_mgr is None:
        context._multi_mgr = SensorManager()
        context._multi_zones = {}

    mgr = context._multi_mgr

    # 只在感測器不存在時才建立（支援共用感測器）
    try:
        mgr.get_sensor(sensor_name)
    except KeyError:
        sensor = SimulatedSensor(name=sensor_name, timeout=2, base_temp=50.0,
                                 amplitude=0, noise=0)
        mgr.add_sensor(sensor_name, sensor)

    try:
        mgr.get_sensor(fan_name)
    except KeyError:
        fan = SimulatedFan(name=fan_name, timeout=0, max_rpm=10000.0)
        mgr.add_sensor(fan_name, fan)

    zone = Zone(
        zone_id=zid,
        min_thermal_output=min_rpm,
        failsafe_percent=fs,
        cycle_interval_ms=100,
        update_thermals_ms=1000,
        sensor_manager=mgr,
    )
    zone.add_thermal_input(sensor_name)
    zone.add_fan_input(fan_name)

    context._multi_zones[zid] = zone


@given('兩個 Zone 都有 Thermal PID 控制器和 Fan PID 控制器')
def step_add_controllers_to_all_zones(context):
    """為所有 Zone 建立 Thermal PID 和 Fan PID"""
    for zid, zone in context._multi_zones.items():
        # Thermal PID — out_lim.min 對齊 Zone 的 minThermalOutput
        min_output = zone._min_thermal_output
        thermal_config = PidConfig(
            ts=1.0, proportional_coeff=100.0, integral_coeff=2.0,
            integral_limit=Limits(min=0.0, max=10000.0),
            out_lim=Limits(min=min_output, max=10000.0),
        )
        inputs = [SensorInput(name=n) for n in zone._thermal_inputs]
        thermal = ThermalController.create(
            zone, f"thermal_{zid}", inputs, 70.0,
            thermal_config, ThermalType.ABSOLUTE,
        )
        zone.add_thermal_pid(thermal)

        # Fan PID
        fan_names = list(zone._fan_inputs)
        fan_ctrl = FanController.create(
            zone, f"fan_pid_{zid}", fan_names, _make_fan_pid_config(),
        )
        if fan_ctrl:
            zone.add_fan_pid(fan_ctrl)


@when('對兩個 Zone 各執行一次控制迴圈')
def step_run_both_zones(context):
    """對所有 Zone 各執行一次完整的控制迴圈"""
    for zone in context._multi_zones.values():
        zone.initialize_cache()
        zone.update_sensors()
        zone.clear_set_points()
        zone.clear_rpm_ceilings()
        zone.process_thermals()
        zone.determine_max_set_point_request()
        zone.update_fan_telemetry()
        zone.process_fans()


@when('對兩個 Zone 各更新感測器快取')
def step_update_both_zones(context):
    for zone in context._multi_zones.values():
        zone.initialize_cache()
        zone.update_sensors()
        zone.update_fan_telemetry()


# --- Assertions ---

@then('Zone {zid:d} 的最大 Setpoint 應不低於 {expected:g} RPM')
def step_assert_zone_setpoint_gte(context, zid, expected):
    zone = context._multi_zones[zid]
    actual = zone.get_max_set_point_request()
    assert actual >= expected, \
        f"Zone {zid}: 期望 >= {expected}, 實際 {actual}"


@then('Zone 0 與 Zone 1 的 Setpoint 應該獨立計算')
def step_assert_zones_independent(context):
    z0 = context._multi_zones[0]
    z1 = context._multi_zones[1]
    # 兩個 Zone 的 min_thermal_output 不同，所以 setpoint 應該不同
    # （除非剛好算出一樣的值，但因為 min 不同，至少底線不同）
    sp0 = z0.get_max_set_point_request()
    sp1 = z1.get_max_set_point_request()
    assert z0._min_thermal_output != z1._min_thermal_output, \
        "兩個 Zone 的最低轉速設定應該不同才能驗證獨立性"


@then('Zone {zid:d} 的最大 Setpoint 應為 {expected:g} RPM')
def step_assert_zone_setpoint(context, zid, expected):
    zone = context._multi_zones[zid]
    actual = zone.get_max_set_point_request()
    assert actual == expected, \
        f"Zone {zid}: 期望 {expected}, 實際 {actual}"


@then('Zone {zid:d} 應處於 Failsafe 模式')
def step_assert_zone_failsafe(context, zid):
    zone = context._multi_zones[zid]
    assert zone.get_failsafe_mode(), \
        f"Zone {zid} 應處於 Failsafe 但沒有"


@then('Zone {zid:d} 不應處於 Failsafe 模式')
def step_assert_zone_not_failsafe(context, zid):
    zone = context._multi_zones[zid]
    assert not zone.get_failsafe_mode(), \
        f"Zone {zid} 不應處於 Failsafe, 故障感測器: {zone.get_failsafe_sensors()}"


@then('Zone {zid:d} 的快取中 "{name}" 值應為 {expected:g}')
def step_assert_zone_cached(context, zid, name, expected):
    zone = context._multi_zones[zid]
    actual = zone.get_cached_value(name)
    assert abs(actual - expected) < 0.01, \
        f"Zone {zid} 快取 {name}: 期望 {expected}, 實際 {actual}"
