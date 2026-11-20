#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <TM1637Display.h>

// Smart Cat Feeder - Arduino Uno R3 (360-degree continuous rotation servo)
// Serial over USB at 115200 baud.
// Automatic FEED uses USB serial; D2 manual button works even when Pi is offline.
// One press = one servo cycle, debounced. NO FOOD / BENCH TEST ONLY.
// Does not dispense controlled portions; bench-test without the hopper attached.

const uint8_t SERVO_PIN = 9;
const uint8_t TM1637_CLK_PIN = 10; // 4-digit cooldown display CLK
const uint8_t TM1637_DIO_PIN = 11; // 4-digit cooldown display DIO
const uint8_t LED_GREEN_PIN = 4;    // Green: Idle (normal, not moving)
const uint8_t LED_YELLOW_PIN = 5;   // Yellow: Feeding or manual Emergency
const uint8_t IR_SENSOR_PIN = 6;    // IR obstacle module digital OUT / DO
const uint8_t LED_RED_PIN = 7;      // Red: food below minimum level / not yet verified
const uint8_t IR_FOOD_PRESENT_LEVEL = LOW; // Common FC-51: LOW when pellets are in front
const unsigned long FOOD_EMPTY_CONFIRM_MS = 3000UL;
const unsigned long FOOD_PRESENT_CONFIRM_MS = 800UL;
const uint8_t MANUAL_BUTTON_PIN = 2;       // Momentary NO push button: D2 <-> GND
const unsigned long BUTTON_DEBOUNCE_MS = 35UL;
const unsigned long MANUAL_ANTI_REPEAT_MS = 2000UL; // Prevent accidental rapid presses
// Continuous-rotation servo: pulse width controls speed/direction, not angle.
// Calibrate neutral for your specific servo; test without the hopper attached.
const uint16_t SERVO_STOP_US = 1500;
const uint16_t SERVO_RUN_US = 1700; // Use ~1300 for opposite direction if needed
// Empirical calibration: measured about 180 degrees in 2000 ms at 1700 us.
// Estimate one complete 360-degree rotation in 4000 ms at the SAME pulse.
// Continuous rotation has no position feedback; actual turns depend on load/power.
// Keep pulse unchanged so this timing estimate stays meaningful.
const uint8_t TARGET_REVOLUTIONS = 1;
const unsigned long REVOLUTION_MS = 4000UL;
const unsigned long OPEN_MS = TARGET_REVOLUTIONS * REVOLUTION_MS;
const unsigned long CLOSE_SETTLE_MS = 750UL;
const unsigned long COOLDOWN_MS = 60000UL; // Hard minimum between accepted FEEDs

Servo feederServo;
TM1637Display cooldownDisplay(TM1637_CLK_PIN, TM1637_DIO_PIN);

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

// Unconfirmed startup state is a warning. Never assume food exists until
// sensor reading stays stable for FOOD_PRESENT_CONFIRM_MS.
bool foodLevelKnown = false;
bool foodPresent = false;
bool foodRawPresent = false;
unsigned long foodRawChangedAt = 0;

// Emergency > feeding > food level > idle; LCD refreshes on state changes.
void showScreen(ScreenState next) {
  const bool changed = (screenState != next);
  screenState = next;
  if (lcd == nullptr) return;
  if (lcdReady && !changed) return;

  lcd->setCursor(0, 0);
  lcd->print(F("SMART CAT FEEDER"));
  lcd->setCursor(0, 1);
  lcd->print(F("                "));
  lcd->setCursor(0, 1);
  if (next == SCREEN_EMERGENCY) {
    lcd->print(F("Emergency"));
  } else if (next == SCREEN_FEEDING) {
    lcd->print(F("Feeding"));
  } else if (!foodLevelKnown) {
    lcd->print(F("Cek Makanan"));
  } else if (!foodPresent) {
    lcd->print(F("Makanan Habis"));
  } else {
    lcd->print(F("Idle"));
  }
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
unsigned long lastShownCooldownSeconds = 0xFFFFFFFFUL;

unsigned long remainingCooldownSeconds(unsigned long now) {
  if (!hasFed) return 0;
  const unsigned long elapsed = (unsigned long)(now - lastFeedAt);
  if (elapsed >= COOLDOWN_MS) return 0;
  const unsigned long remainingMs = COOLDOWN_MS - elapsed;
  return (remainingMs + 999UL) / 1000UL; // Round up: 5 -> 4 ... -> 0
}

// Non-blocking MM:SS display updates, only when a second changes.
// Tracks Arduino's *automatic* cooldown, starting with each accepted servo cycle.
// The D2 manual button can still override automatic cooldown.
void updateCooldownDisplay() {
  const unsigned long secondsLeft = remainingCooldownSeconds(millis());
  if (secondsLeft == lastShownCooldownSeconds) return;
  lastShownCooldownSeconds = secondsLeft;
  const unsigned int minutes = secondsLeft / 60UL;
  const unsigned int seconds = secondsLeft % 60UL;
  const int mmss = (int)(minutes * 100U + seconds);
  cooldownDisplay.showNumberDecEx(mmss, 0b01000000, true, 4, 0);
}

void printCooldownStatus() {
  Serial.print(F("COOLDOWN "));
  Serial.println(remainingCooldownSeconds(millis()));
}

char lineBuffer[24];
uint8_t lineLength = 0;

// LED priority: yellow = servo movement or software emergency lock;
// red = low/unknown food; green = confirmed food present and idle.
// Red can remain ON together with yellow if the hopper is empty.
void updateStatusLEDs() {
  const bool active = (servoState != IDLE) || emergencyActive;
  const bool lowOrUnknown = !foodLevelKnown || !foodPresent;
  digitalWrite(LED_GREEN_PIN, (!active && !lowOrUnknown) ? HIGH : LOW);
  digitalWrite(LED_YELLOW_PIN, active ? HIGH : LOW);
  digitalWrite(LED_RED_PIN, lowOrUnknown ? HIGH : LOW);
}

// Poll the IR module non-blockingly, ignoring brief gaps between pellets.
// Digital modules usually output LOW when they detect a nearby object.
// Sensor is only a LOW-LEVEL INDICATOR, not an accurate measure of food mass.
void updateFoodSensor() {
  const unsigned long now = millis();
  const bool observedFood = digitalRead(IR_SENSOR_PIN) == IR_FOOD_PRESENT_LEVEL;
  if (observedFood != foodRawPresent) {
    foodRawPresent = observedFood;
    foodRawChangedAt = now;
  }

  if (foodLevelKnown && observedFood == foodPresent) return;

  const unsigned long stableFor =
      observedFood ? FOOD_PRESENT_CONFIRM_MS : FOOD_EMPTY_CONFIRM_MS;
  if ((unsigned long)(now - foodRawChangedAt) < stableFor) return;

  foodPresent = observedFood;
  foodLevelKnown = true;
  updateStatusLEDs();
  lcdReady = false;
  showScreen(screenState);
  if (foodPresent) {
    Serial.println(F("FOOD PRESENT"));
  } else {
    Serial.println(F("FOOD EMPTY"));
  }
}

void printFoodStatus() {
  Serial.print(F("FOOD_STATUS RAW="));
  Serial.print(digitalRead(IR_SENSOR_PIN) == LOW ? F("LOW") : F("HIGH"));
  Serial.print(F(" STATE="));
  if (!foodLevelKnown) {
    Serial.println(F("CHECKING"));
  } else if (foodPresent) {
    Serial.println(F("PRESENT"));
  } else {
    Serial.println(F("EMPTY"));
  }
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
  feederServo.writeMicroseconds(SERVO_RUN_US);
  digitalWrite(LED_BUILTIN, HIGH);
  updateStatusLEDs();
  updateCooldownDisplay(); // Show 00:05 or 01:00 immediately on FEED start
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
  if (strcmp(command, "COOLDOWN_STATUS") == 0) {
    printCooldownStatus();
    return;
  }
  if (strcmp(command, "FOOD_STATUS") == 0) {
    printFoodStatus();
    return;
  }
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
    feederServo.writeMicroseconds(SERVO_STOP_US);
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
    feederServo.writeMicroseconds(SERVO_STOP_US);
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
    feederServo.writeMicroseconds(SERVO_STOP_US);
    servoState = CLOSING;
    stageStartedAt = now;
    Serial.println(F("STATE CLOSING")); // Protocol preserved; motor is stopped
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
  pinMode(LED_RED_PIN, OUTPUT);
  cooldownDisplay.setBrightness(4, true); // 0..7; 4 limits LED current
  updateCooldownDisplay(); // On boot: 00:00 (ready)
  pinMode(IR_SENSOR_PIN, INPUT_PULLUP); // Typical LM393 open-collector OUT
  foodRawPresent = digitalRead(IR_SENSOR_PIN) == IR_FOOD_PRESENT_LEVEL;
  foodRawChangedAt = millis();
  updateStatusLEDs(); // Red until food is verified, then green when idle.
  pinMode(MANUAL_BUTTON_PIN, INPUT_PULLUP);
  lastButtonRaw = digitalRead(MANUAL_BUTTON_PIN);
  stableButton = lastButtonRaw;
  lastButtonChangeAt = millis();

  // Set neutral stop pulse before attaching to avoid unexpected movement at boot.
  feederServo.writeMicroseconds(SERVO_STOP_US);
  feederServo.attach(SERVO_PIN);
  Serial.begin(115200);
  initOptionalLCD();
  showScreen(SCREEN_IDLE);
  Serial.println(F("READY SMART_CAT_FEEDER_V1"));
  Serial.println(F("SAFE MODE: BENCH TEST ONLY / NO WEIGHT CONTROL"));
}

void loop() {
  updateFoodSensor();
  updateManualButton();
  readSerialCommands();
  updateServo();
  updateCooldownDisplay();
}
