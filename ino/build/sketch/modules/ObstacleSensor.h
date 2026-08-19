#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\ObstacleSensor.h"
#pragma once

#include "Adafruit_VL53L0X.h"

class ObstacleSensor : public Adafruit_VL53L0X{
public:
    using Adafruit_VL53L0X::Adafruit_VL53L0X;
    void init(){
        if(!Adafruit_VL53L0X::begin()){
            Serial.println("Obstacle sensor initialize failed");
            for(;;);
        }
    }
    int getrange(){
        rangingTest(&measure, false);
        if(measure.RangeStatus!=4){
            return measure.RangeMilliMeter;
        }
        else{
            return -1;
        }
    }
private:
    VL53L0X_RangingMeasurementData_t measure;
};