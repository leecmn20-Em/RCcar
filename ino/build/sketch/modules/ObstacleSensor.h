#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\ObstacleSensor.h"
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

namespace HCSR04{
    extern const byte trigPin;
    extern const byte echoPin;

    const uint32_t measurementIntervalUs = 60000UL;
    const uint32_t echoTimeoutUs = 25000UL;

    enum MeasurementState : uint8_t {
        WAIT_INTERVAL,
        WAIT_ECHO_RISE,
        WAIT_ECHO_FALL
    };

    MeasurementState measurementState = WAIT_INTERVAL;

    uint32_t lastTriggerUs = 0;
    uint32_t echoWaitStartedUs = 0;
    uint32_t echoRiseUs = 0;

    int latestDistanceMm = -1;
    bool resultReady = false;

    void setup(){
        pinMode(trigPin, OUTPUT);
        pinMode(echoPin, INPUT);

        digitalWrite(trigPin, LOW);
        lastTriggerUs = micros();
    }

    void finishMeasurement(int distanceMm){
        latestDistanceMm = distanceMm;
        resultReady = true;
        measurementState = WAIT_INTERVAL;
    }

    void updateMeasurement(){
        uint32_t now = micros();

        switch(measurementState){
            case WAIT_INTERVAL:
                if(resultReady){
                    return;
                }

                if(now-lastTriggerUs<measurementIntervalUs){
                    return;
                }

                digitalWrite(trigPin, LOW);
                delayMicroseconds(2);
                digitalWrite(trigPin, HIGH);
                delayMicroseconds(10);
                digitalWrite(trigPin, LOW);

                lastTriggerUs = micros();
                echoWaitStartedUs = lastTriggerUs;
                measurementState = WAIT_ECHO_RISE;
                break;

            case WAIT_ECHO_RISE:
                if(digitalRead(echoPin)==HIGH){
                    echoRiseUs = now;
                    measurementState = WAIT_ECHO_FALL;
                }
                else if(now-echoWaitStartedUs>=echoTimeoutUs){
                    finishMeasurement(-1);
                }
                break;

            case WAIT_ECHO_FALL:
                if(digitalRead(echoPin)==LOW){
                    uint32_t durationUs = now-echoRiseUs;
                    int distanceMm =
                        static_cast<int>((durationUs*343UL)/2000UL);
                    finishMeasurement(distanceMm);
                }
                else if(now-echoRiseUs>=echoTimeoutUs){
                    finishMeasurement(-1);
                }
                break;
        }
    }

    bool readDistance(int& range){
        if(!resultReady){
            return false;
        }

        range = latestDistanceMm;
        resultReady = false;
        return true;
    }
}
