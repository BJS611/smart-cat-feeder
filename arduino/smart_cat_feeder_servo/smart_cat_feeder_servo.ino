#include <Servo.h>

// Smart Cat Feeder - Arduino Uno R3 (MG996R prototype)
// Serial over USB at 115200 baud.
// The servo moves ONLY when a complete "FEED\n" command is received.
// Does not dispense controlled portions; bench-test without the hopper attached.

const uint8_t SERVO_PIN = 9;
const uint8_t CLOSED_ANGLE = 20;     // Adjust before mounting the servo horn
const uint8_t OPEN_ANGLE = 80;       // Adjust to avoid mechanical stops
const unsigned long OPEN_MS = 650UL;
const unsigned long CLOSE_SETTLE_MS = 750UL;
const unsigned long COOLDOWN_MS = 60000UL; // Hard minimum between accepted FEEDs

Servo feederServo;

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
  if (servoState == OPENING) {
    Serial.println(F("STATUS OPENING"));
  } else if (servoState == CLOSING) {
    Serial.println(F("STATUS CLOSING"));
  } else {
    Serial.println(F("STATUS IDLE"));
  }
}

void handleCommand(const char *command) {
  if (strcmp(command, "PING") == 0) {
    Serial.println(F("PONG"));
    return;
  }

  if (strcmp(command, "STATUS") == 0) {
    printStatus();
    return;
  }

  if (strcmp(command, "FEED") == 0) {
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
    Serial.println(F("DONE"));
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Set target before attaching: reduce unexpected travel at startup.
  feederServo.write(CLOSED_ANGLE);
  feederServo.attach(SERVO_PIN);
  Serial.begin(115200);
  Serial.println(F("READY SMART_CAT_FEEDER_V1"));
  Serial.println(F("SAFE MODE: BENCH TEST ONLY / NO WEIGHT CONTROL"));
}

void loop() {
  readSerialCommands();
  updateServo();
}
