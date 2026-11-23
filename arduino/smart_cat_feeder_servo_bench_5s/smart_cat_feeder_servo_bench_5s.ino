#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <TM1637Display.h>


const uint8_t SERVO_PIN = 9;
const uint8_t TM1637_CLK_PIN = 10;
const uint8_t TM1637_DIO_PIN = 11;
const uint8_t LED_GREEN_PIN = 4;
const uint8_t LED_YELLOW_PIN = 5;
const uint8_t IR_SENSOR_PIN = 6;
const uint8_t HOPPER_TRIG_PIN = 3;
const uint8_t HOPPER_ECHO_PIN = 8;
const uint16_t HOPPER_FULL_CM = 5;
const uint16_t HOPPER_EMPTY_CM = 25;
const uint8_t HOPPER_MIN_PERCENT = 10;
const unsigned long HOPPER_SAMPLE_MS = 500UL;
const unsigned long HOPPER_ECHO_TIMEOUT_US = 12000UL;
const unsigned long LCD_PAGE_MS = 2500UL;
const uint8_t LED_RED_PIN = 7;
const uint8_t IR_FOOD_PRESENT_LEVEL = LOW;
const unsigned long FOOD_EMPTY_CONFIRM_MS = 3000UL;
const unsigned long FOOD_PRESENT_CONFIRM_MS = 800UL;
const uint8_t MANUAL_BUTTON_PIN = 2;
const unsigned long BUTTON_DEBOUNCE_MS = 35UL;
const unsigned long MANUAL_ANTI_REPEAT_MS = 2000UL;


const uint16_t SERVO_STOP_US = 1500;
const uint16_t SERVO_RUN_US = 1700;


const uint8_t TARGET_REVOLUTIONS = 1;
const unsigned long REVOLUTION_MS = 4000UL;
const unsigned long OPEN_MS = TARGET_REVOLUTIONS * REVOLUTION_MS;
const unsigned long CLOSE_SETTLE_MS = 750UL;
const unsigned long COOLDOWN_MS = 5000UL;

Servo feederServo;
TM1637Display cooldownDisplay(TM1637_CLK_PIN, TM1637_DIO_PIN);


LiquidCrystal_I2C lcd27(0x27, 16, 2);
LiquidCrystal_I2C lcd3f(0x3F, 16, 2);
LiquidCrystal_I2C *lcd = nullptr;

enum ScreenState : uint8_t { SCREEN_IDLE, SCREEN_FEEDING, SCREEN_EMERGENCY };
ScreenState screenState = SCREEN_IDLE;
bool lcdReady = false;


bool emergencyActive = false;

bool lastButtonRaw = HIGH;
bool stableButton = HIGH;
unsigned long lastButtonChangeAt = 0;
unsigned long lastManualAt = 0;
bool manualHasRun = false;
bool manualCycle = false;


bool foodLevelKnown = false;
bool foodPresent = false;
bool foodRawPresent = false;
unsigned long foodRawChangedAt = 0;
bool hopperKnown = false;
uint8_t hopperPercent = 0;
uint16_t hopperDistanceCm = 0;
uint8_t hopperMisses = 0;
unsigned long lastHopperSampleAt = 0;
unsigned long lastLcdPageAt = 0;
bool showBowlPage = false;


void showScreen(ScreenState next) {
  const bool changed = screenState != next;
  screenState = next;
  if (lcd == nullptr || (lcdReady && !changed)) return;
  lcd->setCursor(0, 0);
  lcd->print(F("SMART CAT FEEDER"));
  lcd->setCursor(0, 1);
  lcd->print(F("                "));
  lcd->setCursor(0, 1);
  if (next == SCREEN_EMERGENCY) {
    lcd->print(F("Emergency"));
  } else if (next == SCREEN_FEEDING) {
    lcd->print(F("Feeding"));
  } else if (showBowlPage) {
    if (!foodLevelKnown) lcd->print(F("Mangkuk: Cek"));
    else if (foodPresent) lcd->print(F("Mangkuk: Ada"));
    else lcd->print(F("Mangkuk: Kosong"));
  } else if (!hopperKnown) {
    lcd->print(F("Stok: Cek Sensor"));
  } else {
    lcd->print(F("Stok: "));
    lcd->print(hopperPercent);
    lcd->print('%');
    if (hopperPercent <= HOPPER_MIN_PERCENT) lcd->print(F(" LOW"));
  }
  lcdReady = true;
}

void updateLcdPage() {
  const unsigned long now = millis();
  if ((unsigned long)(now - lastLcdPageAt) < LCD_PAGE_MS) return;
  lastLcdPageAt = now;
  showBowlPage = !showBowlPage;
  lcdReady = false;
  showScreen(screenState);
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
  return (remainingMs + 999UL) / 1000UL;
}


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


void updateStatusLEDs() {
  const bool active = (servoState != IDLE) || emergencyActive;
  const bool lowOrUnknown = !hopperKnown || hopperPercent <= HOPPER_MIN_PERCENT;
  digitalWrite(LED_GREEN_PIN, (!active && !lowOrUnknown) ? HIGH : LOW);
  digitalWrite(LED_YELLOW_PIN, active ? HIGH : LOW);
  digitalWrite(LED_RED_PIN, lowOrUnknown ? HIGH : LOW);
}


void updateHopperSensor() {
  const unsigned long now = millis();
  if ((unsigned long)(now - lastHopperSampleAt) < HOPPER_SAMPLE_MS) return;
  lastHopperSampleAt = now;
  digitalWrite(HOPPER_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(HOPPER_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(HOPPER_TRIG_PIN, LOW);
  const unsigned long echoUs = pulseIn(HOPPER_ECHO_PIN, HIGH, HOPPER_ECHO_TIMEOUT_US);
  const unsigned long distanceCm = echoUs * 343UL / 20000UL;
  if (echoUs == 0 || distanceCm < 2 || distanceCm > 200) {
    if (hopperMisses < 3) hopperMisses++;
    if (hopperMisses >= 3 && hopperKnown) {
      hopperKnown = false;
      updateStatusLEDs();
      lcdReady = false;
      showScreen(screenState);
      Serial.println(F("HOPPER SENSOR_ERROR"));
    }
    return;
  }
  hopperMisses = 0;
  long percent = ((long)HOPPER_EMPTY_CM - (long)distanceCm) * 100L /
                 ((long)HOPPER_EMPTY_CM - (long)HOPPER_FULL_CM);
  percent = constrain(percent, 0L, 100L);
  const uint8_t measured = (uint8_t)percent;
  const bool changed = !hopperKnown || measured != hopperPercent;
  hopperKnown = true;
  hopperPercent = measured;
  hopperDistanceCm = (uint16_t)distanceCm;
  if (changed) {
    updateStatusLEDs();
    lcdReady = false;
    showScreen(screenState);
  }
}

void printHopperStatus() {
  Serial.print(F("HOPPER_STATUS STATE="));
  Serial.print(hopperKnown ? F("OK") : F("UNKNOWN"));
  Serial.print(F(" PERCENT="));
  if (hopperKnown) Serial.print(hopperPercent);
  else Serial.print(F("NA"));
  Serial.print(F(" DIST_CM="));
  if (hopperKnown) Serial.println(hopperDistanceCm);
  else Serial.println(F("NA"));
}

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


void startServoCycle(bool manual) {
  const unsigned long now = millis();
  stageStartedAt = now;
  servoState = OPENING;
  manualCycle = manual;


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
  updateCooldownDisplay();
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


    if (stableButton == LOW) {
      if (emergencyActive) {
        Serial.println(F("MANUAL_IGNORED EMERGENCY_LOCK"));
      } else if (servoState != IDLE) {
        Serial.println(F("MANUAL_IGNORED BUSY"));
      } else if (manualHasRun &&
                 (unsigned long)(now - lastManualAt) < MANUAL_ANTI_REPEAT_MS) {
        Serial.println(F("MANUAL_IGNORED ANTI_REPEAT"));
      } else {
        startServoCycle(true);
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
  if (strcmp(command, "FOOD_STATUS") == 0 || strcmp(command, "BOWL_STATUS") == 0) {
    printFoodStatus();
    return;
  }
  if (strcmp(command, "HOPPER_STATUS") == 0) {
    printHopperStatus();
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


    if (!hopperKnown || hopperPercent <= HOPPER_MIN_PERCENT) {
      Serial.println(F("ERR HOPPER_LOW"));
      return;
    }
    if (!foodLevelKnown) {
      Serial.println(F("ERR BOWL_UNKNOWN"));
      return;
    }
    if (foodPresent) {
      Serial.println(F("ERR BOWL_FULL"));
      return;
    }
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
  pinMode(LED_RED_PIN, OUTPUT);
  cooldownDisplay.setBrightness(4, true);
  updateCooldownDisplay();
  pinMode(HOPPER_TRIG_PIN, OUTPUT);
  digitalWrite(HOPPER_TRIG_PIN, LOW);
  pinMode(HOPPER_ECHO_PIN, INPUT);
  pinMode(IR_SENSOR_PIN, INPUT_PULLUP);
  foodRawPresent = digitalRead(IR_SENSOR_PIN) == IR_FOOD_PRESENT_LEVEL;
  foodRawChangedAt = millis();
  updateStatusLEDs();
  pinMode(MANUAL_BUTTON_PIN, INPUT_PULLUP);
  lastButtonRaw = digitalRead(MANUAL_BUTTON_PIN);
  stableButton = lastButtonRaw;
  lastButtonChangeAt = millis();


  feederServo.writeMicroseconds(SERVO_STOP_US);
  feederServo.attach(SERVO_PIN);
  Serial.begin(115200);
  initOptionalLCD();
  showScreen(SCREEN_IDLE);
  Serial.println(F("READY SMART_CAT_FEEDER_V1"));
  Serial.println(F("BENCH MODE: COOLDOWN 5 SECONDS; NO FOOD / NO WEIGHT CONTROL"));
}

void loop() {
  updateHopperSensor();
  updateFoodSensor();
  updateManualButton();
  readSerialCommands();
  updateServo();
  updateCooldownDisplay();
  updateLcdPage();
}
