#include <Arduino.h>
#include <WiFi.h>

const char* ssid = "RobotArm_Team3";
const char* password = "robot1234";

const int port = 5000;

WiFiServer server(port);

void setup()
{
    Serial.begin(115200);

    // ESP32가 Wi-Fi AP 생성
    WiFi.softAP(ssid, password);

    Serial.println();
    Serial.println("SoftAP started");
    Serial.print("IP Address: ");
    Serial.println(WiFi.softAPIP());

    // TCP Server 시작
    server.begin();

    Serial.print("TCP Server started. Port: ");
    Serial.println(port);
}

void loop()
{
    // PC의 TCP 연결 기다리기
    WiFiClient client = server.available();

    if (client)
    {
        Serial.println("Client connected");

        while (client.connected())
        {
            if (client.available())
            {
                String data = client.readStringUntil('\n');

                Serial.print("Received: ");
                Serial.println(data);

                // Robot Arm 명령 ACK. 향후 AGV telemetry도 같은 TCP stream에
                // 전송되므로 Backend가 message 종류를 명확히 구분할 수 있게 한다.
                client.println("ARM_ACK,OK");
            }

            delay(1);
        }

        client.stop();
        Serial.println("Client disconnected");
    }
}
