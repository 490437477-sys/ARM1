/*
 * Servo Arm Control System
 * Main Controller: Arduino UNO R3
 * 
 * Hardware:
 * - 2x Dual-axis Joystick Modules
 * - 4x MG995 Servo Motors
 * - No LED
 * 
 * Control Methods:
 * 1. Joystick Control - Physical joysticks
 * 2. Serial Commands - Arduino IDE Serial Monitor
 * 3. Python GUI - Computer interface
 * Modify: Remove servo4, Servo3 init angle 0, S1/S2 range 0-90 init 45, no auto refresh status
 */
#include <Servo.h>

// ===================== PIN DEFINITIONS =====================
const int joy1XPin = A0;
const int joy1YPin = A1;
const int joy1BtnPin = 2;

const int joy2XPin = A3;
const int joy2YPin = A2;
const int joy2BtnPin = 4;

const int servoPins[] = {11, 10, 9, 5};
const int SERVO_COUNT = 4;

// ===================== GLOBAL ADJUST PARAMETERS =====================
const int deadZone     = 60;
const int joyStep      = 1;
const int moveDelay    = 40;
const int btnDebounce  = 80;
const int btnStep      = 3;
const int smoothStep   = 1;

const int MAX_ANGLE_NORMAL = 180;
const int MAX_ANGLE_LIMITED = 90;
const int MIN_ANGLE        = 0;

// ===================== GLOBAL VARIABLES =====================
Servo servos[SERVO_COUNT];
// S0:90, S1:45, S2:45, S3:0, removed S4
int angles[SERVO_COUNT]  = {90, 45, 45, 0};
int targets[SERVO_COUNT]= {90, 45, 45, 0};

unsigned long lastMoveTick = 0;
unsigned long lastBtn1Tick  = 0;
unsigned long lastBtn2Tick  = 0;

String serialBuffer = "";

// ===================== SETUP =====================
void setup() {
  pinMode(joy1BtnPin, INPUT_PULLUP);
  pinMode(joy2BtnPin, INPUT_PULLUP);

  for(int i = 0; i < SERVO_COUNT; i++){
    servos[i].attach(servoPins[i]);
    servos[i].write(angles[i]);
    delay(30);
  }

  Serial.begin(9600);
  while(!Serial) delay(10);

  printHelpInfo();
  Serial.print("Init OK, Home: ");
  printNumArray(angles, SERVO_COUNT);
}

// ===================== MAIN LOOP =====================
void loop() {
  unsigned long nowMs = millis();

  if(nowMs - lastMoveTick < moveDelay){
    return;
  }
  lastMoveTick = nowMs;

  handleSerialInput();
  smoothServoMove();
  handleJoysticks();
}

// ===================== SMOOTH SERVO INTERPOLATION =====================
void smoothServoMove(){
  for(int i = 0; i < SERVO_COUNT; i++){
    if(angles[i] < targets[i]){
      angles[i] += smoothStep;
      if(angles[i] > targets[i]) angles[i] = targets[i];
    }else if(angles[i] > targets[i]){
      angles[i] -= smoothStep;
      if(angles[i] < targets[i]) angles[i] = targets[i];
    }
    servos[i].write(angles[i]);
  }
}

// ===================== JOYSTICK PROCESS =====================
void handleJoysticks(){
  int j1X = analogRead(joy1XPin) - 512;
  int j1Y = analogRead(joy1YPin) - 512;
  int j2X = analogRead(joy2XPin) - 512;
  int j2Y = analogRead(joy2YPin) - 512;

  if(j1X < -deadZone) targets[0] = constrain(targets[0] - joyStep, MIN_ANGLE, MAX_ANGLE_NORMAL);
  else if(j1X > deadZone) targets[0] = constrain(targets[0] + joyStep, MIN_ANGLE, MAX_ANGLE_NORMAL);

  if(j1Y < -deadZone) targets[1] = constrain(targets[1] - joyStep, MIN_ANGLE, MAX_ANGLE_LIMITED);
  else if(j1Y > deadZone) targets[1] = constrain(targets[1] + joyStep, MIN_ANGLE, MAX_ANGLE_LIMITED);

  if(j2X < -deadZone) targets[2] = constrain(targets[2] - joyStep, MIN_ANGLE, MAX_ANGLE_LIMITED);
  else if(j2X > deadZone) targets[2] = constrain(targets[2] + joyStep, MIN_ANGLE, MAX_ANGLE_LIMITED);

  if(j2Y < -deadZone) targets[3] = constrain(targets[3] - joyStep, MIN_ANGLE, MAX_ANGLE_NORMAL);
  else if(j2Y > deadZone) targets[3] = constrain(targets[3] + joyStep, MIN_ANGLE, MAX_ANGLE_NORMAL);
}

// ===================== SERIAL DATA PROCESS =====================
void handleSerialInput(){
  while(Serial.available() > 0){
    char ch = Serial.read();
    if(ch == '\n' || ch == '\r'){
      if(serialBuffer.length() > 0){
        parseSerialCommand(serialBuffer);
        serialBuffer = "";
      }
    }else{
      if((ch >= '0' && ch <= '9') || ch == ' ' || ch == 'h' || ch == 's'){
        serialBuffer += ch;
      }
    }
  }
}

void parseSerialCommand(String cmd){
  cmd.trim();
  if(cmd.length() == 0) return;

  if(cmd == "h" || cmd == "help"){
    printHelpInfo();
    return;
  }
  if(cmd == "s" || cmd == "status"){
    Serial.print("STATUS All Servos [S0,S1,S2,S3]: ");
    printNumArray(angles, SERVO_COUNT);
    return;
  }

  int parseVals[4] = {0};
  int valCount = 0;
  int splitStart = 0;

  for(int i = 0; i <= cmd.length() && valCount < SERVO_COUNT; i++){
    if(cmd.charAt(i) == ' ' || i == cmd.length()){
      String numStr = cmd.substring(splitStart, i);
      if(numStr.toInt() >= 0){
        parseVals[valCount++] = numStr.toInt();
      }
      splitStart = i + 1;
    }
  }

  if(valCount == 4){
    for(int i = 0; i < SERVO_COUNT; i++){
      int limit;
      if(i == 1 || i == 2) limit = MAX_ANGLE_LIMITED;
      else limit = MAX_ANGLE_NORMAL;
      targets[i] = constrain(parseVals[i], MIN_ANGLE, limit);
    }
    Serial.print("Batch OK Target: ");
    printNumArray(targets, SERVO_COUNT);
    return;
  }

  if(valCount == 2){
    int servoId = parseVals[0];
    int setAng  = parseVals[1];
    if(servoId >= 0 && servoId < SERVO_COUNT){
      int limit;
      if(servoId == 1 || servoId == 2) limit = MAX_ANGLE_LIMITED;
      else limit = MAX_ANGLE_NORMAL;
      targets[servoId] = constrain(setAng, MIN_ANGLE, limit);
      Serial.print("S");
      Serial.print(servoId);
      Serial.print(" target = ");
      Serial.println(targets[servoId]);
      return;
    }
  }

  Serial.println("Err: cmd invalid, input h for help");
}

// ===================== SERIAL PRINT UTILS =====================
void printHelpInfo(){
  Serial.println("======== Servo Arm Command List ========");
  Serial.println("h        Show help");
  Serial.println("s        Print ALL 4 servos current angles");
  Serial.println("0 60     Set S0 target to 60");
  Serial.println("90 45 45 0 Batch set all targets");
  Serial.println("Limit:S1/S2 0-90 | S0/S3 0-180");
  Serial.println("========================================");
}

void printNumArray(int arr[], int len){
  for(int i = 0; i < len; i++){
    Serial.print(arr[i]);
    if(i != len - 1) Serial.print(",");
  }
  Serial.println();
}