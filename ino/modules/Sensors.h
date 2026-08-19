#pragma once

namespace LineSensor{
    extern const byte Obstacle_Sensor = 8;
    extern const byte Line_Sensor_Left = A1;
    extern const byte Line_Sensor_Right = A2;

    void setupSensors(){
        //pinMode(Obstacle_Sensor, INPUT);
        pinMode(Line_Sensor_Left, INPUT);
        pinMode(Line_Sensor_Right, INPUT);
    }

    inline bool onLine_left(){
        return digitalRead(Line_Sensor_Left) == LOW;
    }

    inline bool onLine_right(){
        return digitalRead(Line_Sensor_Right) == LOW;
    }

    inline bool obstacleDetected(){
        return digitalRead(Obstacle_Sensor) == LOW;
    }
}