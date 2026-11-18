#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// BENCH TEST ONLY - Arduino Uno MG996R, cooldown 5 seconds.
// DO NOT connect to a hopper or use this version to dispense food.
// Smart Cat Feeder - Arduino Uno R3 (MG996R prototype)
// Serial over USB at 115200 baud.
// Automatic FEED uses USB serial; D2 manual button works even when Pi is offline.
// One press = one servo cycle, debounced. NO FOOD / BENCH TEST ONLY.
// Does not dispense controlled portions; bench-test without the hopper attached.

const uint8_t SERVO_PIN = 9;
const uint8_t LED_GREEN_PIN = 4;    // Green: Idle (normal, not moving)
const uint8_t LED_YELLOW_PIN = 5;   // Yellow: Feeding or manual Emergency
const uint8_t MANUAL_BUTTON_PIN = 2;       // Momentary NO push button: D2 <-> GND
const unsigned long BUTTON_DEBOUNCE_MS = 35UL;
const unsigned long MANUAL_ANTI_REPEAT_MS = 2000UL; // Prevent accidental rapid presses
const uint8_t CLOSED_ANGLE = 20;     // Adjust before mounting the servo horn
const uint8_t OPEN_ANGLE = 80;       // Adjust to avoid mechanical stops
const unsigned long OPEN_MS = 650UL;
const unsigned long CLOSE_SETTLE_MS = 750UL;
const unsigned long COOLDOWN_MS = 5000UL; // BENCH TEST ONLY: 5 s between FEEDs

Servo feederServo;

// Keep both LCD addresses ready, but don't talk to the LCD when absent.
// Broken/borrowed LCD should be physically disconnected for now.
LiquidCrystal_I2C lcd27(0x27, 16, 2);
LiquidCrystal_I2C lcd3f(0x3F, 16, 2);
LiquidCrystal_I2C *lcd = nullptr;

enum ScreenState : uint8_t { SCREEN_IDLE, SCREEN_FEEDING, SCREEN_EMERGENCY };
ScreenState screenState = SCREEN_IDLE;
bool lcdReady = false;

// Serial "EMERGENCY" means a latched software STOP that blocks FEED.
// The D2 pushbutton means MANUAL EMERGENCY FEED (not a safety E-stop).
bool emergencyActive = false;

bool lastButtonRaw = HIGH;
bool stableButton = HIGH;
unsigned long lastButtonChangeAt = 0;
unsigned long lastManualAt = 0;
bool manualHasRun = false;
bool manualCycle = false;

void showScreen(ScreenState next) {
  if (lcd == nullptr) {
    screenState = next;
    return;
  }
  if (lcdReady && screenState == next) return;

  lcd->setCursor(0, 0);
  lcd->print(F("SMART CAT FEEDER")); // 16 characters
  lcd->setCursor(0, 1);
  lcd->print(F("                "));
  lcd->setCursor(0, 1);
  if (next == SCREEN_FEEDING) {
    lcd->print(F("Feeding"));
  } else if (next == SCREEN_EMERGENCY) {
    lcd->print(F("Emergency"));
  } else {
    lcd->print(F("Idle"));
  }
  screenState = next;
  lcdReady = true;
}

bool i2cPresent(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void initOptionalLCD() {
  Wire.begin();
  if (i2cPresent(0x27)) {
    lcd = &lcd27;
    Serial.println(F("LCD FOUND 0x27"));
  } else if (i2cPresent(0x3F)) {
    lcd = &lcd3f;
    Serial.println(F("LCD FOUND 0x3F"));
  } else {
    lcd = nullptr;
    Serial.println(F("LCD NOT CONNECTED - continue without LCD"));
    return;
  }
  lcd->init();
  lcd->backlight();
  lcdReady = false;
  showScreen(screenState);
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

// Exclusive LEDs: GREEN only while truly idle; YELLOW for movement
// (YOLO FEED or D2 manual button), or during latched software EMERGENCY.
void updateStatusLEDs() {
  const bool active = (servoState != IDLE) || emergencyActive;
  digitalWrite(LED_GREEN_PIN, active ? LOW : HIGH);
  digitalWrite(LED_YELLOW_PIN, active ? HIGH : LOW);
}

// Shared servo state machine, preserving existing FEED serial protocol.
void startServoCycle(bool manual) {
  const unsigned long now = millis();
  stageStartedAt = now;
  servoState = OPENING;
  manualCycle = manual;
  // A manual cycle must also start the automatic cooldown.
  // Without this, YOLO could instantly trigger another feed after button release.
  lastFeedAt = now;
  hasFed = true;
  if (manual) {
    lastManualAt = now;
    manualHasRun = true;
    showScreen(SCREEN_EMERGENCY);
    Serial.println(F("EVENT MANUAL_FEED"));
  } else {
    showScreen(SCREEN_FEEDING);
  }
  feederServo.write(OPEN_ANGLE);
  digitalWrite(LED_BUILTIN, HIGH);
  updateStatusLEDs();
}

void updateManualButton() {
  const bool raw = digitalRead(MANUAL_BUTTON_PIN);
  const unsigned long now = millis();

  if (raw != lastButtonRaw) {
    lastButtonRaw = raw;
    lastButtonChangeAt = now;
  }

  if (raw != stableButton &&
      (unsigned long)(now - lastButtonChangeAt) >= BUTTON_DEBOUNCE_MS) {
    stableButton = raw;

    // HIGH->LOW stable edge: one cycle per fresh button press.
    if (stableButton == LOW) {
      if (emergencyActive) {
        Serial.println(F("MANUAL_IGNORED EMERGENCY_LOCK"));
      } else if (servoState != IDLE) {
        Serial.println(F("MANUAL_IGNORED BUSY"));
      } else if (manualHasRun &&
                 (unsigned long)(now - lastManualAt) < MANUAL_ANTI_REPEAT_MS) {
        Serial.println(F("MANUAL_IGNORED ANTI_REPEAT"));
      } else {
        startServoCycle(true); // Bypasses YOLO and automatic cooldown
      }
    }
  }
}

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
    manualCycle = false;
    digitalWrite(LED_BUILTIN, LOW);
    showScreen(SCREEN_EMERGENCY);
    updateStatusLEDs();
    Serial.println(F("ACK EMERGENCY"));
    return;
  }

  if (strcmp(command, "RESET") == 0) {
    emergencyActive = false;
    feederServo.write(CLOSED_ANGLE);
    servoState = IDLE;
    manualCycle = false;
    digitalWrite(LED_BUILTIN, LOW);
    showScreen(SCREEN_IDLE);
    updateStatusLEDs();
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

    // Keep original automatic FEED cooldown, independent of manual presses.
    startServoCycle(false);
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
    manualCycle = false;
    showScreen(emergencyActive ? SCREEN_EMERGENCY : SCREEN_IDLE);
    updateStatusLEDs();
    Serial.println(F("DONE"));
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_YELLOW_PIN, OUTPUT);
  updateStatusLEDs(); // Boot in Idle: green ON, yellow OFF.
  pinMode(MANUAL_BUTTON_PIN, INPUT_PULLUP);
  lastButtonRaw = digitalRead(MANUAL_BUTTON_PIN);
  stableButton = lastButtonRaw;
  lastButtonChangeAt = millis();

  // Set closed target before attach to reduce unwanted movement at boot.
  feederServo.write(CLOSED_ANGLE);
  feederServo.attach(SERVO_PIN);
  Serial.begin(115200);
  initOptionalLCD();
  showScreen(SCREEN_IDLE);
  Serial.println(F("READY SMART_CAT_FEEDER_V1"));
  Serial.println(F("BENCH MODE: COOLDOWN 5 SECONDS; NO FOOD / NO WEIGHT CONTROL"));
}

void loop() {
  updateManualButton();
  readSerialCommands();
  updateServo();
}
