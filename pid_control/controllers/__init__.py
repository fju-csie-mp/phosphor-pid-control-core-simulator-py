# controllers 子套件
# 包含所有控制器的實作：
#   - Controller: 控制器基底類別（抽象介面）
#   - PIDController: PID 控制器基底（Template Method 骨架）
#   - FanController: 風扇控制器（讀取風扇轉速 → PID 計算 → 輸出 PWM）
#   - ThermalController: 溫度控制器（讀取溫度 → PID 計算 → 輸出目標轉速）
#   - StepwiseController: 階梯控制器（查表決定輸出，不用 PID）
