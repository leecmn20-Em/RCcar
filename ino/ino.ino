#include <Arduino.h>
#include "modules\Commands.h"
#include "modules\Servo1.h"
//#include "modules\Displayer.h"
#include "modules\Arms.h"
#include "modules\Wheel.h"
#include "modules\LineSensor.h"
#include "modules\ObstacleSensor.h"

#pragma region Constants
const byte Encoder_Left = 2;
const byte Encoder_Right = 3;
const byte Motor_Left1 = 5;
const byte Motor_Left2 = 6;
const byte Motor_Right1 = 11;
const byte Motor_Right2 = 10;

//const byte LineSensor::Obstacle_Sensor = -1;
// The left/right sensors are mounted at the front of the car. The D12
// sensor is mounted behind them, near the center of the chassis floor.
const byte LineSensor::Line_Sensor_Left = A0;
const byte LineSensor::Line_Sensor_BodyCenter = 12;
const byte LineSensor::Line_Sensor_Right = A1;
#pragma endregion

#pragma region Object Declairation
Wheel leftwheel = Wheel(Motor_Left1,Motor_Left2,Encoder_Left,"LeftWheel");
Wheel rightwheel = Wheel(Motor_Right1,Motor_Right2,Encoder_Right,"RightWheel");
void ISRencoder_left(){
    leftwheel.onEncoderInterrupt();
}
void ISRencoder_right(){
    rightwheel.onEncoderInterrupt();
}

//Displayer oled = Displayer();
ObstacleSensor obsensor = ObstacleSensor();
#pragma endregion

namespace DrivePolicy {
    int drivemode = 0;
    bool onobstacle;
    bool iolleft;
    bool iolbodycenter;
    bool iolright;
    int lastLineSide = 0; // -1: left, 1: right
    int activeTurnSide = 0;
    uint32_t lastLineSeenMillis = 0;
    uint32_t sideDetectedSinceMillis = 0;
    uint32_t bodyCenterSinceMillis = 0;
    
    const int BASE_RPM = 60;
    const int SOFT_INNER_RPM = 40;
    const int SOFT_OUTER_RPM = 60;
    const int HARD_INNER_RPM = 0;
    const int HARD_OUTER_RPM = 50;
    const int SEARCH_OUTER_RPM = 35;
    const uint16_t SHARP_TURN_CONFIRM_MS = 150;
    const uint16_t ALIGNED_CONFIRM_MS = 500;
    const uint16_t SEARCH_TIMEOUT_MS = 1200;

    void lineTrace(){
        if(onobstacle){
            leftwheel.stop();
            rightwheel.stop();
            return;
        }

        bool sharpTurnConfirmed = activeTurnSide != 0 &&
                                  millis()-sideDetectedSinceMillis >= SHARP_TURN_CONFIRM_MS;

        // Both front sensors usually mean a stop line, intersection, or a line
        // that is too wide to determine a safe steering direction.
        if(iolleft && iolright){
            leftwheel.stop();
            rightwheel.stop();
        } else if(iolleft){
            if(iolbodycenter && !sharpTurnConfirmed){
                leftwheel.setTargetRPM(SOFT_INNER_RPM);
                rightwheel.setTargetRPM(SOFT_OUTER_RPM);
            }
            else{
                leftwheel.setTargetRPM(HARD_INNER_RPM);
                rightwheel.setTargetRPM(HARD_OUTER_RPM);
            }
        } else if(iolright){
            if(iolbodycenter && !sharpTurnConfirmed){
                leftwheel.setTargetRPM(SOFT_OUTER_RPM);
                rightwheel.setTargetRPM(SOFT_INNER_RPM);
            }
            else{
                leftwheel.setTargetRPM(HARD_OUTER_RPM);
                rightwheel.setTargetRPM(HARD_INNER_RPM);
            }
        } else if(iolbodycenter){
            leftwheel.setTargetRPM(BASE_RPM);
            rightwheel.setTargetRPM(BASE_RPM);
        } else if(millis()-lastLineSeenMillis <= SEARCH_TIMEOUT_MS){
            // All sensors are off: keep searching only toward the most recent
            // side that saw the line. The timeout prevents endless wandering.
            if(lastLineSide < 0){
                leftwheel.setTargetRPM(HARD_INNER_RPM);
                rightwheel.setTargetRPM(SEARCH_OUTER_RPM);
            }
            else if(lastLineSide > 0){
                leftwheel.setTargetRPM(SEARCH_OUTER_RPM);
                rightwheel.setTargetRPM(HARD_INNER_RPM);
            }
            else{
                leftwheel.stop();
                rightwheel.stop();
            }
        } else{
            leftwheel.stop();
            rightwheel.stop();
        }
    }

    void force(int ls = 0, int rs = 0){
        drivemode = 2;
        leftwheel.setTargetRPM(ls);
        rightwheel.setTargetRPM(rs);
        Serial.print("left wheel RPM set to: ");
        Serial.println(ls);
        Serial.print("right wheel RPM set to: ");
        Serial.println(rs);
    }

    void emergencystop(){
        drivemode = -1;
        leftwheel.stop();
        rightwheel.stop();
    }

    void drive(){
        switch(drivemode){
            case 0: //stop
                leftwheel.setTargetRPM(0);
                rightwheel.setTargetRPM(0);
                break;
            case 1: //free trace
                lineTrace();
                break;
            default:
                break;
        }
    }

    void drive(int mode){
        drivemode = mode;
        drive();
    }
}

namespace {
    void doSerialCommand(){
        String command[COMMAND_MAXLENGTH];
        if(!getSerialCommand(command)){
            return;
        }
        if(command[0]=="SETSPEED"){
            int ls = command[1].toInt();
            int rs = command[2].toInt();
            DrivePolicy::force(ls, rs);
        }
    }
}

namespace Update {
    uint32_t cmillis = 0;
    uint32_t lastloopmillis = 0;
    uint32_t lastcalmillis = 0;
    uint32_t lastcalmillis_fast = 0;
    uint32_t lastconmillis = 0;
    uint32_t lastconmillis_fine = 0;
    uint32_t calperiod = 1000;
    uint32_t calperiod_fast = 1000;
    uint32_t conperiod = 1000;
    uint32_t conperiod_fine = 1000;

    void init(){
        lastloopmillis = 0;
        lastcalmillis = 0;
        lastconmillis = 0;
        lastconmillis_fine = 0;
    }

    void ready(){
        cmillis = millis();
    }

    void end(){
        return;
    }

    void monitor(){
        Serial.println("==========");
        Serial.print("Drivemode: ");
        Serial.println(DrivePolicy::drivemode);
        Serial.print("Left wheel duty: ");
        Serial.print(leftwheel.getCurrentDuty());
        Serial.print('/');
        Serial.print(leftwheel.getTargetDuty());
        Serial.print('/');
        Serial.println(leftwheel.getEstimatedRPM());
        Serial.print("Right wheel duty: ");
        Serial.print(rightwheel.getCurrentDuty());
        Serial.print('/');
        Serial.print(rightwheel.getTargetDuty());
        Serial.print('/');
        Serial.println(rightwheel.getEstimatedRPM());
        if(LineSensor::onLine_left()){
            Serial.println("left ON-line");
        }
        else{
            Serial.println("left OFF-line");
        }
        if(LineSensor::onLine_bodyCenter()){
            Serial.println("body-center ON-line");
        }
        else{
            Serial.println("body-center OFF-line");
        }
        if(LineSensor::onLine_right()){
            Serial.println("right ON-line");
        }
        else{
            Serial.println("right OFF-line");
        }
        Serial.print("Obstacle? ");
        if(DrivePolicy::onobstacle){
            Serial.println("yes");
        }
        else{
            Serial.println("no");
        }
    }

    int updateCalc(){
        if(cmillis-lastcalmillis>=calperiod){
            leftwheel.estimateRPM(cmillis-lastcalmillis);
            rightwheel.estimateRPM(cmillis-lastcalmillis);
            
            int range = obsensor.getrange();
            if(range!=-1 && range<150){
                DrivePolicy::onobstacle = true;
            }
            else{
                DrivePolicy::onobstacle = false;
            }

            lastcalmillis = cmillis;
            return 1;
        }
        return 0;
    }

    int updateFast(){
        if(cmillis-lastcalmillis_fast>=calperiod_fast){
            LineSensor::update(cmillis);
            DrivePolicy::iolleft = LineSensor::onLine_left();
            DrivePolicy::iolbodycenter = LineSensor::onLine_bodyCenter();
            DrivePolicy::iolright = LineSensor::onLine_right();

            if(DrivePolicy::iolleft || DrivePolicy::iolbodycenter || DrivePolicy::iolright){
                DrivePolicy::lastLineSeenMillis = cmillis;
            }

            int detectedSide = 0;
            if(DrivePolicy::iolleft && !DrivePolicy::iolright){
                detectedSide = -1;
            }
            else if(DrivePolicy::iolright && !DrivePolicy::iolleft){
                detectedSide = 1;
            }

            if(detectedSide != 0){
                DrivePolicy::lastLineSide = detectedSide;
                if(DrivePolicy::activeTurnSide != detectedSide){
                    DrivePolicy::activeTurnSide = detectedSide;
                    DrivePolicy::sideDetectedSinceMillis = cmillis;
                }
            }
            else{
                DrivePolicy::activeTurnSide = 0;
                DrivePolicy::sideDetectedSinceMillis = 0;
            }

            // The body-center sensor confirms that the chassis is aligned over
            // the line. After a stable straight section, discard an old turn.
            if(DrivePolicy::iolbodycenter && !DrivePolicy::iolleft && !DrivePolicy::iolright){
                if(DrivePolicy::bodyCenterSinceMillis == 0){
                    DrivePolicy::bodyCenterSinceMillis = cmillis;
                }
                else if(cmillis-DrivePolicy::bodyCenterSinceMillis >= DrivePolicy::ALIGNED_CONFIRM_MS){
                    DrivePolicy::lastLineSide = 0;
                }
            }
            else{
                DrivePolicy::bodyCenterSinceMillis = 0;
            }

            lastcalmillis_fast = cmillis;
            return 1;
        }
        return 0;
    }

    int updateCon(){
        if(cmillis-lastconmillis>=conperiod){
            DrivePolicy::drive();
            leftwheel.followRPM();
            rightwheel.followRPM();

            lastconmillis = cmillis;
            return 1;
        }
        return 0;
    }

    int updateFine(){
        if(cmillis-lastconmillis_fine>=conperiod_fine){
            leftwheel.updateMotor();
            rightwheel.updateMotor();

            lastconmillis_fine = cmillis;
            return 1;
        }
        return 0;
    }

    int updateLoop(){
        if(cmillis-lastloopmillis>=1000){
            monitor();

            lastloopmillis = cmillis;
            return 1;
        }
        return 0;
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("Arduino Booting...");
    leftwheel.setup();
    rightwheel.setup();
    LineSensor::setupSensors();
    attachInterrupt(digitalPinToInterrupt(leftwheel.getEncoder()), ISRencoder_left, FALLING);
    attachInterrupt(digitalPinToInterrupt(rightwheel.getEncoder()), ISRencoder_right, FALLING);
    Update::calperiod = 50;
    Update::calperiod_fast = 10;
    Update::conperiod = 50;
    Update::conperiod_fine = 10;
    //oled.init();
    Serial.println("1");
    obsensor.init();
    Serial.println("2");
    DrivePolicy::drivemode = 1;
    Serial.println("Arduino ONLINE");
}

void loop() {
    doSerialCommand();

    Update::ready();
    Update::updateCalc();
    Update::updateFast();
    Update::updateCon();
    Update::updateFine();
    Update::updateLoop();
    Update::end();
}
