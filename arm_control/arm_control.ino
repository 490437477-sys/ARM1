#include <Servo.h>

// 摇杆引脚定义
const int joy1XPin = A0;
const int joy1YPin = A1;
const int joy1ButtonPin = 2;

const int joy2XPin = A3;
const int joy2YPin = A2;
const int joy2ButtonPin = 4;

const int ledPin = 3;

// 4个舵机控制引脚
const int servoPins[] = {5, 9, 10, 11};
Servo servos[4];

// 舵机初始角度（归零位置）
const int servoInit[] = {45, 45, 0, 90};
int servoAngles[] = {45, 45, 0, 90};
int targetAngles[] = {45, 45, 0, 90};

// 舵机角度范围配置
const int servoRange[4][2] = {
  {0, 90},    // 舵机0：0~90
  {0, 90},    // 舵机1：0~90
  {0, 90},    // 舵机2：0~90
  {0, 180}    // 舵机3：0~180
};

const int deadZone = 50;
const int stepAngle = 1;
const int joyDelay = 30;

// 平滑运动速度（值越大越快，1=最慢）
const int smoothSpeed = 1;

// 按钮防抖
unsigned long lastButtonTime = 0;
const int debounceDelay = 50;

// 系统状态
enum SystemState { INITIALIZING, RUNNING };
SystemState systemState = INITIALIZING;
unsigned long lastBlinkTime = 0;
const int blinkInterval = 500;

void setup() {
  Serial.begin(9600);

  pinMode(joy1ButtonPin, INPUT_PULLUP);
  pinMode(joy2ButtonPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);

  for (int i = 0; i < 4; i++) {
    if (millis() - lastBlinkTime >= blinkInterval) {
      digitalWrite(ledPin, !digitalRead(ledPin));
      lastBlinkTime = millis();
    }
    
    servos[i].attach(servoPins[i]);
    servos[i].write(servoAngles[i]);
    delay(80);
  }

  digitalWrite(ledPin, HIGH);
  systemState = RUNNING;

  printHelp();
}

void printHelp() {
  Serial.println(F("========== 舵机控制 =========="));
  Serial.println(F("命令:"));
  Serial.println(F("  0 45   - 舵机0设置到45度"));
  Serial.println(F("  1 90   - 舵机1设置到90度"));
  Serial.println(F("  2 30   - 舵机2设置到30度"));
  Serial.println(F("  3 180  - 舵机3设置到180度"));
  Serial.println(F("  Z      - 全部归零"));
  Serial.println(F("  A      - 查看所有角度"));
  Serial.println(F("  H      - 显示帮助"));
  Serial.println(F("================================"));
}

void setServoAngle(int servoIndex, int angle) {
  if (servoIndex < 0 || servoIndex > 3) {
    Serial.println(F("舵机编号 0-3"));
    return;
  }
  
  angle = constrain(angle, servoRange[servoIndex][0], servoRange[servoIndex][1]);
  targetAngles[servoIndex] = angle;
  
  Serial.print(F("S"));
  Serial.print(servoIndex);
  Serial.print(F(" -> "));
  Serial.println(angle);
}

void zeroAll() {
  for (int i = 0; i < 4; i++) {
    targetAngles[i] = servoInit[i];
  }
  Serial.println(F("归零完成"));
}

void printAllAngles() {
  for (int i = 0; i < 4; i++) {
    Serial.print(F("S"));
    Serial.print(i);
    Serial.print(F(": "));
    Serial.print(servoAngles[i]);
    Serial.print(F("("));
    Serial.print(targetAngles[i]);
    Serial.print(F(") "));
  }
  Serial.println();
}

void smoothMove() {
  for (int i = 0; i < 4; i++) {
    if (servoAngles[i] < targetAngles[i]) {
      servoAngles[i] = min(servoAngles[i] + smoothSpeed, targetAngles[i]);
      servos[i].write(servoAngles[i]);
    } else if (servoAngles[i] > targetAngles[i]) {
      servoAngles[i] = max(servoAngles[i] - smoothSpeed, targetAngles[i]);
      servos[i].write(servoAngles[i]);
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd.length() == 0) return;

  Serial.print(F("> "));
  Serial.println(cmd);

  int spaceIdx = cmd.indexOf(' ');
  if (spaceIdx > 0) {
    int servoIndex = cmd.substring(0, spaceIdx).toInt();
    int angle = cmd.substring(spaceIdx + 1).toInt();
    if (servoIndex >= 0 && servoIndex <= 3 && angle >= 0) {
      setServoAngle(servoIndex, angle);
      return;
    }
  }

  if (cmd == "Z") {
    zeroAll();
  } else if (cmd == "A") {
    printAllAngles();
  } else if (cmd == "H") {
    printHelp();
  }
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    processCommand(cmd);
  }

  smoothMove();

  if (systemState != RUNNING) return;

  int joy1X = analogRead(joy1XPin) - 512;
  int joy1Y = analogRead(joy1YPin) - 512;
  int joy2X = analogRead(joy2XPin) - 512;
  int joy2Y = analogRead(joy2YPin) - 512;

  if (abs(joy1X) > deadZone) {
    servoAngles[0] = constrain(
      joy1X < 0 ? servoAngles[0] - stepAngle : servoAngles[0] + stepAngle,
      servoRange[0][0], servoRange[0][1]
    );
    targetAngles[0] = servoAngles[0];
    servos[0].write(servoAngles[0]);
  }

  if (abs(joy1Y) > deadZone) {
    servoAngles[1] = constrain(
      joy1Y < 0 ? servoAngles[1] - stepAngle : servoAngles[1] + stepAngle,
      servoRange[1][0], servoRange[1][1]
    );
    targetAngles[1] = servoAngles[1];
    servos[1].write(servoAngles[1]);
  }

  if (abs(joy2X) > deadZone) {
    servoAngles[2] = constrain(
      joy2X < 0 ? servoAngles[2] - stepAngle : servoAngles[2] + stepAngle,
      servoRange[2][0], servoRange[2][1]
    );
    targetAngles[2] = servoAngles[2];
    servos[2].write(servoAngles[2]);
  }

  if (abs(joy2Y) > deadZone) {
    servoAngles[3] = constrain(
      joy2Y < 0 ? servoAngles[3] - stepAngle : servoAngles[3] + stepAngle,
      servoRange[3][0], servoRange[3][1]
    );
    targetAngles[3] = servoAngles[3];
    servos[3].write(servoAngles[3]);
  }

  delay(joyDelay);
}