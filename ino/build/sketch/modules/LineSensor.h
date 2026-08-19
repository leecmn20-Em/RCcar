#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\LineSensor.h"
#pragma once

namespace LineSensor{
    extern const byte Line_Sensor_Left;
    extern const byte Line_Sensor_Right;
    uint16_t bufftime = 320;

    void setupSensors(){
        pinMode(Line_Sensor_Left, INPUT);
        pinMode(Line_Sensor_Right, INPUT);
    }

    inline bool onLine_left(){
        return digitalRead(Line_Sensor_Left) == HIGH;
    }

    inline bool onLine_right(){
        return digitalRead(Line_Sensor_Right) == HIGH;
    }
}