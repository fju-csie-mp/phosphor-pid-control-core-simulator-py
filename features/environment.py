"""
behave 環境設定：每個 scenario 前後要做的事
"""
import sys
import os

# 確保可以 import 專案模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def before_scenario(context, scenario):
    """每個 scenario 開始前，清空共享狀態"""
    context.zone = None
    context.sensor_manager = None
    context.zones = []
    context.sensor_configs = {}
    context.caught_exception = None
    context.thermal_input_value = None
    context.fan_pwm_before = {}
    context.stepwise_output = None
