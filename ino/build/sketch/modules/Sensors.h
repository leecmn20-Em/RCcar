#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\Sensors.h"
#pragma once

namespace LineSensor{
    extern const byte Obstacle_Sensor;
    extern const byte Line_Sensor_Left;
    extern const byte Line_Sensor_Right;

    void setupSensors(){
        //pinMode(Obstacle_Sensor, INPUT);
        pinMode(Line_Sensor_Left, INPUT);
        pinMode(Line_Sensor_Right, INPUT);
    }

    inline bool onLine_left(){
        return digitalRead(Line_Sensor_Left) == HIGH;
    }

    inline bool onLine_right(){
        return digitalRead(Line_Sensor_Right) == HIGH;
    }

    inline bool obstacleDetected(){
        return digitalRead(Obstacle_Sensor) == LOW;
    }
}