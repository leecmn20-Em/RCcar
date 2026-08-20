#pragma once

#include "Adafruit_VL53L0X.h"

class ObstacleSensor : public Adafruit_VL53L0X{
public:
    using Adafruit_VL53L0X::Adafruit_VL53L0X;
    void init(uint16_t period){
        if(!begin()){
            Serial.println(F("Obstacle sensor initialize failed"));
            for(;;);
        }
        if(!startRangeContinuous(period)){
            Serial.println(F("Obstacle sensor ranging failed"));
            for(;;);
        }
    }
    bool pollRange(int& range){
        if(!isRangeComplete()){
            return false;
        }
        uint16_t result = readRangeResult();
        if(result==0xFFFF || readRangeStatus()==4){
            range = -1;
        }
        else{
            range = (int)result;
        }
        return true;
    }
};