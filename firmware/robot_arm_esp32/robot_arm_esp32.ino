#include <Arduino.h>
#include <Servo.h>
#include <WiFi.h>

// Set these four values from the actual ESP32 wiring before compiling.
// The historical prototype used 3/5/9/6, but 6 and 9 are commonly connected
// to flash on classic ESP32 modules and are deliberately not used as defaults.
#ifndef ROBOT_ARM_BASE_PIN
#define ROBOT_ARM_BASE_PIN -1
#endif
#ifndef ROBOT_ARM_SHOULDER_PIN
#define ROBOT_ARM_SHOULDER_PIN -1
#endif
#ifndef ROBOT_ARM_UPPER_PIN
#define ROBOT_ARM_UPPER_PIN -1
#endif
#ifndef ROBOT_ARM_FOREARM_PIN
#define ROBOT_ARM_FOREARM_PIN -1
#endif

#if ROBOT_ARM_BASE_PIN < 0 || ROBOT_ARM_SHOULDER_PIN < 0 || \
    ROBOT_ARM_UPPER_PIN < 0 || ROBOT_ARM_FOREARM_PIN < 0
#error "Set all ROBOT_ARM_*_PIN values from the actual ESP32 wiring before compiling"
#endif

static_assert(ROBOT_ARM_BASE_PIN != ROBOT_ARM_SHOULDER_PIN,
              "Servo pins must be unique");
static_assert(ROBOT_ARM_BASE_PIN != ROBOT_ARM_UPPER_PIN,
              "Servo pins must be unique");
static_assert(ROBOT_ARM_BASE_PIN != ROBOT_ARM_FOREARM_PIN,
              "Servo pins must be unique");
static_assert(ROBOT_ARM_SHOULDER_PIN != ROBOT_ARM_UPPER_PIN,
              "Servo pins must be unique");
static_assert(ROBOT_ARM_SHOULDER_PIN != ROBOT_ARM_FOREARM_PIN,
              "Servo pins must be unique");
static_assert(ROBOT_ARM_UPPER_PIN != ROBOT_ARM_FOREARM_PIN,
              "Servo pins must be unique");

namespace Config {
constexpr char kSsid[] = "RobotArm_Team3";
constexpr char kPassword[] = "robot1234";
constexpr uint16_t kPort = 5000;
constexpr int kHomeAngle = 90;
constexpr size_t kCommandBufferSize = 64;
}  // namespace Config

WiFiServer server(Config::kPort);

Servo baseServo;
Servo shoulderServo;
Servo upperServo;
Servo forearmServo;

char commandBuffer[Config::kCommandBufferSize];
size_t commandLength = 0;
bool commandOverflow = false;

bool parseAngleCommand(const char* command, int angles[4]) {
    const char* cursor = command;

    for (size_t index = 0; index < 4; ++index) {
        while (*cursor == ' ' || *cursor == '\t') {
            ++cursor;
        }

        char* end = nullptr;
        const long value = strtol(cursor, &end, 10);
        if (end == cursor || value < 0 || value > 180) {
            return false;
        }

        while (*end == ' ' || *end == '\t') {
            ++end;
        }

        const char expectedDelimiter = index < 3 ? ',' : '\0';
        if (*end != expectedDelimiter) {
            return false;
        }

        angles[index] = static_cast<int>(value);
        cursor = index < 3 ? end + 1 : end;
    }

    return true;
}

void applyAngles(const int angles[4]) {
    // Wire order: base, shoulder, upper arm, forearm.
    baseServo.write(angles[0]);
    shoulderServo.write(angles[1]);
    upperServo.write(angles[2]);
    forearmServo.write(angles[3]);
}

void processCommand(WiFiClient& client) {
    commandBuffer[commandLength] = '\0';

    int angles[4] = {};
    if (commandOverflow || !parseAngleCommand(commandBuffer, angles)) {
        Serial.print("Rejected ARM command: ");
        Serial.println(commandOverflow ? "frame too long" : commandBuffer);
        client.println("ARM_ACK,ERROR");
    } else {
        applyAngles(angles);
        Serial.printf(
            "Applied ARM command: %d,%d,%d,%d\n",
            angles[0], angles[1], angles[2], angles[3]
        );
        // Exactly one ACK is emitted after all four Servo targets are applied.
        client.println("ARM_ACK,OK");
    }

    commandLength = 0;
    commandOverflow = false;
}

void consumeClientBytes(WiFiClient& client) {
    while (client.available()) {
        const char value = static_cast<char>(client.read());

        if (value == '\r') {
            continue;
        }
        if (value == '\n') {
            processCommand(client);
            continue;
        }
        if (commandOverflow) {
            continue;
        }
        if (commandLength + 1 >= Config::kCommandBufferSize) {
            commandOverflow = true;
            continue;
        }

        commandBuffer[commandLength++] = value;
    }
}

void attachServosAtHome() {
    baseServo.attach(ROBOT_ARM_BASE_PIN);
    shoulderServo.attach(ROBOT_ARM_SHOULDER_PIN);
    upperServo.attach(ROBOT_ARM_UPPER_PIN);
    forearmServo.attach(ROBOT_ARM_FOREARM_PIN);

    const int homeAngles[4] = {
        Config::kHomeAngle,
        Config::kHomeAngle,
        Config::kHomeAngle,
        Config::kHomeAngle,
    };
    applyAngles(homeAngles);
    delay(250);
}

void setup() {
    Serial.begin(115200);
    attachServosAtHome();

    if (!WiFi.softAP(Config::kSsid, Config::kPassword)) {
        Serial.println("SoftAP startup failed");
        return;
    }

    server.begin();
    Serial.println("Robot Arm ESP32 ready");
    Serial.print("SoftAP IP: ");
    Serial.println(WiFi.softAPIP());
    Serial.print("TCP port: ");
    Serial.println(Config::kPort);
}

void loop() {
    WiFiClient client = server.available();
    if (!client) {
        delay(1);
        return;
    }

    Serial.println("Backend connected");
    commandLength = 0;
    commandOverflow = false;

    while (client.connected()) {
        consumeClientBytes(client);
        delay(1);
    }

    client.stop();
    commandLength = 0;
    commandOverflow = false;
    Serial.println("Backend disconnected");
}
