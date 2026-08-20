#pragma once

namespace LineSensor{
    extern const byte Line_Sensor_Left;
    extern const byte Line_Sensor_Right;
    extern const byte Line_Sensor_Center;
    uint16_t bufftime = 800;

    void setupSensors(){
        pinMode(Line_Sensor_Left, INPUT);
        pinMode(Line_Sensor_Right, INPUT);
        pinMode(Line_Sensor_Center, INPUT);
    }

    inline bool onLine_left(){
        return digitalRead(Line_Sensor_Left) == HIGH;
    }

    inline bool onLine_right(){
        return digitalRead(Line_Sensor_Right) == HIGH;
    }

    inline bool onLine_center(){
        return digitalRead(Line_Sensor_Center) == HIGH;
    }
}