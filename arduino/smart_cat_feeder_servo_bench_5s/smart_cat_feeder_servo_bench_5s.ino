#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// BENCH TEST ONLY - Arduino Uno MG996R, cooldown 5 seconds.
// DO NOT connect to a hopper or use this version to dispense food.
// Smart Cat Feeder - Arduino Uno R3 (MG996R prototype)
// Serial over USB at 115200 baud.
// The servo moves ONLY when a complete "FEED\n" command is received.
// Does not dispense controlled portions; bench-test without the hopper attached.

const uint8_t SERVO_PIN = 9;
const uint8_t CLOSED_ANGLE = 20;     // Adjust before mounting the servo horn
const uint8_t OPEN_ANGLE = 80;       // Adjust to avoid mechanical stops
const unsigned long OPEN_MS = 650UL;
const unsigned long CLOSE_SETTLE_MS = 750UL;
const unsigned long COOLDOWN_MS = 5000UL; // BENCH TEST ONLY: 5 s between FEEDs

Servo feederServo;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Status LCD follows the existing servo state. Emergency button is NOT used yet.
enum ScreenState : uint8_t { SCREEN_IDLE, SCREEN_FEEDING, SCREEN_EMERGENCY };
ScreenState screenState = SCREEN_IDLE;
bool lcdReady = false;
bool emergencyActive = false;

void showScreen(ScreenState next) {
  if (lcdReady && screenState == next) return;

  lcd.setCursor(0, 0);
  lcd.print(F("SMART CAT FEEDER")); // Exactly 16 characters
  lcd.setCursor(0, 1);
  lcd.print(F("                ")); // Clear old status without flicker
  lcd.setCursor(0, 1);

  if (next == SCREEN_FEEDING) {
    lcd.print(F("Feeding"));
  } else if (next == SCREEN_EMERGENCY) {
    lcd.print(F("Emergency"));
  } else {
    lcd.print(F("Idle"));
  }
  screenState = next;
  lcdReady = true;
}


enum ServoState : uint8_t {
  IDLE,
  OPENING,
  CLOSING
};

ServoState servoState = IDLE;
unsigned long stageStartedAt = 0;
unsigned long lastFeedAt = 0;
bool hasFed = false;

char lineBuffer[24];
uint8_t lineLength = 0;

void printStatus() {
  if (emergencyActive) {
    Serial.println(F("STATUS EMERGENCY"));
  } else if (servoState == OPENING) {
    Serial.println(F("STATUS OPENING"));
  } else if (servoState == CLOSING) {
    Serial.println(F("STATUS CLOSING"));
  } else {
    Serial.println(F("STATUS IDLE"));
  }
}

void scanI2CBus() {
  // Diagnostic only. This does not move the servo or change the LCD state.
  uint8_t found = 0;
  Serial.println(F("I2C_SCAN_START"));
  for (uint8_t address = 1; address <= 126; address++) {
    Wire.beginTransmission(address);
    const uint8_t error = Wire.endTransmission();
    if (error == 0) {
      Serial.print(F("I2C_FOUND 0x"));
      if (address < 16) Serial.print('0');
      Serial.println(address, HEX);
      found++;
    }
  }
  Serial.print(F("I2C_SCAN_DONE "));
  Serial.println(found);
}

void handleCommand(const char *command) {
  if (strcmp(command, "I2C_SCAN") == 0) {
    scanI2CBus();
    return;
  }
  if (strcmp(command, "PING") == 0) {
    Serial.println(F("PONG"));
    return;
  }

  if (strcmp(command, "STATUS") == 0) {
    printStatus();
    return;
  }

  if (strcmp(command, "EMERGENCY") == 0) {
    // LCD emergency test only; physical button to be added later.
    emergencyActive = true;
    feederServo.write(CLOSED_ANGLE);
    servoState = IDLE;
    digitalWrite(LED_BUILTIN, LOW);
    showScreen(SCREEN_EMERGENCY);
    Serial.println(F("ACK EMERGENCY"));
    return;
  }

  if (strcmp(command, "RESET") == 0) {
    emergencyActive = false;
    feederServo.write(CLOSED_ANGLE);
    servoState = IDLE;
    digitalWrite(LED_BUILTIN, LOW);
    showScreen(SCREEN_IDLE);
    Serial.println(F("ACK RESET"));
    return;
  }

  if (strcmp(command, "FEED") == 0) {
    if (emergencyActive) {
      Serial.println(F("ERR EMERGENCY"));
      return;
    }
    const unsigned long now = millis();

    if (servoState != IDLE) {
      Serial.println(F("ERR BUSY"));
      return;
    }
    if (hasFed && (unsigned long)(now - lastFeedAt) < COOLDOWN_MS) {
      Serial.println(F("ERR COOLDOWN"));
      return;
    }

    // Accept exactly one rotation cycle.
    lastFeedAt = now;
    hasFed = true;
    stageStartedAt = now;
    servoState = OPENING;
    showScreen(SCREEN_FEEDING);
    feederServo.write(OPEN_ANGLE);
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.println(F("ACK FEED"));
    return;
  }

  Serial.println(F("ERR UNKNOWN_COMMAND"));
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();

    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      if (lineLength > 0) {
        lineBuffer[lineLength] = '\0';
        handleCommand(lineBuffer);
        lineLength = 0;
      }
      continue;
    }

    if (lineLength < sizeof(lineBuffer) - 1) {
      lineBuffer[lineLength++] = c;
    } else {
      lineLength = 0;
      Serial.println(F("ERR LINE_TOO_LONG"));
    }
  }
}

void updateServo() {
  const unsigned long now = millis();

  if (servoState == OPENING &&
      (unsigned long)(now - stageStartedAt) >= OPEN_MS) {
    feederServo.write(CLOSED_ANGLE);
    servoState = CLOSING;
    stageStartedAt = now;
    Serial.println(F("STATE CLOSING"));
  }

  if (servoState == CLOSING &&
      (unsigned long)(now - stageStartedAt) >= CLOSE_SETTLE_MS) {
    servoState = IDLE;
    digitalWrite(LED_BUILTIN, LOW);
    showScreen(SCREEN_IDLE);
    Serial.println(F("DONE"));
  }
}

void setup() {
  Wire.begin();
  lcd.init();
  lcd.backlight();
  showScreen(SCREEN_IDLE);

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Set target before attaching: reduce unexpected travel at startup.
  feederServo.write(CLOSED_ANGLE);
  feederServo.attach(SERVO_PIN);
  Serial.begin(115200);
  Serial.println(F("READY SMART_CAT_FEEDER_V1"));
  Serial.println(F("BENCH MODE: COOLDOWN 5 SECONDS; NO FOOD / NO WEIGHT CONTROL"));
}

void loop() {
  readSerialCommands();
  updateServo();
}
