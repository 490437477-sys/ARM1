# Servo Robot Arm Control System Manual

## 1. Product Overview

This is a **4-DOF Servo Robot Arm Control System** supporting three control methods:

| Control Method | Description |
|---------------|-------------|
| Joystick | Dual joystick real-time control |
| Serial Commands | Arduino IDE Serial Monitor |
| Python GUI | Computer visual control |

## 2. Hardware Configuration

- Arduino UNO R3 (Main Controller)
- 2x Dual-axis Joystick Modules
- 4x MG90S Servos

## 3. Pin Definitions

### Servo Pins

| Servo | Pin |
|-------|-----|
| Servo0 | D5 |
| Servo1 | D9 |
| Servo2 | D10 |
| Servo3 | D11 |
| Servo4 | D7 |

### Joystick Pins

| Joystick | X-axis | Y-axis | Button |
|----------|--------|--------|--------|
| Joystick1 | A0 | A1 | D2 |
| Joystick2 | A3 | A2 | D4 |

## 4. Control Logic

| Input | Controls | Angle Range |
|-------|----------|-------------|
| Joystick1 X-axis | Servo0 | 0-90 deg |
| Joystick1 Y-axis | Servo1 | 0-90 deg |
| Joystick1 Button | - | - |
| Joystick2 X-axis | Servo2 | 0-90 deg |
| Joystick2 Y-axis | Servo3 | 0-180 deg |
| Joystick2 Button | - | - |

## 5. Arduino Setup

1. Open `arm_control.ino` in Arduino IDE
2. Select Board: **Arduino UNO**
3. Select correct COM port
4. Upload code
5. Open Serial Monitor (baud rate 9600)

## 6. Serial Commands

### Servo Control Commands

| Command | Function | Example |
|---------|----------|---------|
| `0 90` | Set Servo0 to 90 deg | `0 45` |
| `1 45` | Set Servo1 to 45 deg | `1 90` |
| `2 90` | Set Servo2 to 90 deg | `2 30` |
| `3 90` | Set Servo3 to 90 deg | `3 180` |

### Quick Commands

| Command | Function |
|---------|----------|
| `4 45` | Set Servo4 to 45 deg (max 90) |
| `90` | Set all servos to 90 deg |
| `A` | Show all angles |
| `H` | Show help |

## 7. Python GUI

### Requirements

- Python 3.x
- pyserial library

### Installation & Running

```bash
pip install pyserial
python servo_control.py
```

### GUI Features

- Port selection and refresh
- Connect/Disconnect control
- Slider control for angles
- Numeric input control
- Reset button

## 8. Safety Warnings

### Power Requirements

After uploading code, switch power from USB to **external power (9V 1A or higher)**.

### Overload Protection

- Do not apply excessive force when gripping objects
- Servo stall will cause current surge and may restart the board

---

**Repository**: https://gitee.com/li-tian12/arm1