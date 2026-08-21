#include <Arduino.h>
#include "modules\Commands.h"
//#include "modules\Servo1.h"
//#include "modules\Displayer.h"
//#include "modules\Arms.h"
#include "modules\Wheel.h"
#include "modules\LineSensor.h"
//#include "modules\ObstacleSensor.h"

#pragma region Constants
const byte Encoder_Left = 2;
const byte Encoder_Right = 3;
const byte Motor_Left1 = 6;
const byte Motor_Left2 = 5;
const byte Motor_Right1 = 10;
const byte Motor_Right2 = 11;

//const byte LineSensor::Obstacle_Sensor = -1;
const byte LineSensor::Line_Sensor_Left = 4;
const byte LineSensor::Line_Sensor_Right = 7;
const byte LineSensor::Line_Sensor_Center = 8;
#pragma endregion

#pragma region Object Declairation
Wheel leftwheel = Wheel(Motor_Left1,Motor_Left2,Encoder_Left);
Wheel rightwheel = Wheel(Motor_Right1,Motor_Right2,Encoder_Right);
void ISRencoder_left(){
    leftwheel.onEncoderInterrupt();
}
void ISRencoder_right(){
    rightwheel.onEncoderInterrupt();
}

//Displayer oled = Displayer();
//ObstacleSensor obsensor = ObstacleSensor();
#pragma endregion

namespace Update{
    uint32_t cmillis = 0;
}

namespace DrivePolicy {
    int drivemode = 0;

    int range = 0;
    bool onobstacle = false;

    uint8_t tracePolicy = 0;
    uint8_t lastIOL = 0;
    
    const int RPM_base = 90;
    const int RPM_softturn_inner = 40;
    const int RPM_softturn_outer = 90;
    const int RPM_sharpturn_inner = 0;
    const int RPM_sharpturn_outer = 60;
    const int RPM_search_inner = 60;
    const int linesearch_timeout = 3000;
    const int allign_wait = 500;
    const int sharpturn_wait = 150;
    const int lost_timeout = 5000;

    void search(){
        leftwheel.setTargetRPM(RPM_softturn_outer);
        rightwheel.setTargetRPM(RPM_softturn_inner);
    }

    void updateTracePolicy(uint8_t state){
        switch(tracePolicy){
            case 0: // go straight
                if(state & 0b100){
                    tracePolicy = 1;
                }
                else if(state & 0b001){
                    tracePolicy = 2;
                }
                break;
            case 1: // turn left
                if(state & 0b010){
                    tracePolicy = 0;
                }
                else if(state & 0b001){
                    tracePolicy = 2;
                }
                break;
            case 2: // turn right
                if(state & 0b100){
                    tracePolicy = 1;
                }
                else if(state & 0b010){
                    tracePolicy = 0;
                }
                break;
            default:
                break;
        }

        lastIOL = state;
    }

    void lineTrace(){
        switch(tracePolicy){
            case 0: // go straight
                leftwheel.setTargetRPM(RPM_base);
                rightwheel.setTargetRPM(RPM_base);
                break;
            case 1: // turn left
                leftwheel.setTargetRPM(RPM_sharpturn_inner);
                rightwheel.setTargetRPM(RPM_sharpturn_outer);
                break;
            case 2: // turn right
                leftwheel.setTargetRPM(RPM_sharpturn_outer);
                rightwheel.setTargetRPM(RPM_sharpturn_inner);
                break;
            case 3: // turn left softly
                leftwheel.setTargetRPM(RPM_softturn_inner);
                rightwheel.setTargetRPM(RPM_softturn_outer);
                break;
            case 4: // turn right softly
                leftwheel.setTargetRPM(RPM_softturn_outer);
                rightwheel.setTargetRPM(RPM_softturn_inner);
                break;
            default:
                leftwheel.stop();
                rightwheel.stop();
                break;
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

namespace Command{
    void doSerialCommand(){
        char* command[COMMAND_MAXLENGTH] = {};
        if(!getSerialCommand(command)){
            return;
        }
        if(strcmp(command[0], "SETSPEED") == 0){
            int ls = command[1] == nullptr ? 0 : static_cast<int>(strtol(command[1], nullptr, 10));
            int rs = command[2] == nullptr ? 0 : static_cast<int>(strtol(command[2], nullptr, 10));
            DrivePolicy::force(ls, rs);
        }
        else if(strcmp(command[0], "SETPID") == 0){
            float p = command[1] == nullptr ? 0.0f : static_cast<float>(atof(command[1]));
            float i = command[2] == nullptr ? 0.0f : static_cast<float>(atof(command[2]));
            float d = command[3] == nullptr ? 0.0f : static_cast<float>(atof(command[3]));
            leftwheel.setPID(p, i, d);
            rightwheel.setPID(p, i, d);
        }
    }
}

namespace Update {
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
        Serial.println(F("=========="));
        Serial.print(F("Drivemode: "));
        Serial.println(DrivePolicy::drivemode);
        Serial.print(F("Left wheel: cur_duty "));
        Serial.print(leftwheel.getCurrentDuty());
        Serial.print(F(" / tgt_duty "));
        Serial.print(leftwheel.getTargetDuty());
        Serial.print(F(" / cur_RPM "));
        Serial.println(leftwheel.getEstimatedRPM());
        Serial.print(F("Right wheel: cur_duty "));
        Serial.print(rightwheel.getCurrentDuty());
        Serial.print(F(" / tgt_duty "));
        Serial.print(rightwheel.getTargetDuty());
        Serial.print(F(" / cur_RPM "));
        Serial.println(rightwheel.getEstimatedRPM());
        Serial.print(F("on-line?: "));
        Serial.print(DrivePolicy::lastIOL & 0b100? 'O':'X');
        Serial.print(F(" - "));
        Serial.print(DrivePolicy::lastIOL & 0b010? 'O':'X');
        Serial.print(F(" - "));
        Serial.println(DrivePolicy::lastIOL & 0b001? 'O':'X');
        Serial.print(F("Obstacle? "));
        if(DrivePolicy::onobstacle){
            Serial.println(F("yes"));
        }
        else{
            Serial.println(F("no"));
        }
        Serial.print(F("Current trace policy: "));
        switch(DrivePolicy::tracePolicy){
            case 0:
                Serial.println(F("Going straight"));
                break;
            case 1:
                Serial.println(F("Turning left"));
                break;
            case 2:
                Serial.println(F("Turning right"));
                break;
            default:
                Serial.println(F("Can't find the policy"));
                break;
        }
    }

    int updateCalc(){
        if(cmillis-lastcalmillis>=calperiod){
            leftwheel.estimateAverageRPM(cmillis-lastcalmillis);
            rightwheel.estimateAverageRPM(cmillis-lastcalmillis);
            
            /*if(obsensor.pollRange(DrivePolicy::range)){
                if(DrivePolicy::range>=0 && DrivePolicy::range<150){
                    DrivePolicy::onobstacle = true;
                }
                else{
                    DrivePolicy::onobstacle = false;
                }
            }*/

            lastcalmillis = cmillis;
            return 1;
        }
        return 0;
    }

    int updateFast(){
        if(cmillis-lastcalmillis_fast>=calperiod_fast){
            uint8_t state = ( 
                LineSensor::onLine_left() << 2 |
                LineSensor::onLine_center() << 1 |
                LineSensor::onLine_right() << 0
            );

            DrivePolicy::updateTracePolicy(state);

            lastcalmillis_fast = cmillis;
            return 1;
        }
        return 0;
    }

    int updateCon(){
        if(cmillis-lastconmillis>=conperiod){
            DrivePolicy::drive();
            leftwheel.updateRPM();
            rightwheel.updateRPM();
            leftwheel.followRPM(cmillis-lastconmillis);
            rightwheel.followRPM(cmillis-lastconmillis);

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
    Serial.println(F("Arduino Booting..."));
    leftwheel.setup();
    rightwheel.setup();
    attachInterrupt(digitalPinToInterrupt(leftwheel.getEncoder()), ISRencoder_left, FALLING);
    attachInterrupt(digitalPinToInterrupt(rightwheel.getEncoder()), ISRencoder_right, FALLING);
    Update::calperiod = 100;
    Update::calperiod_fast = 5;
    Update::conperiod = 20;
    Update::conperiod_fine = 10;
    //oled.init();
    //obsensor.init(100);
    LineSensor::setupSensors();
    DrivePolicy::drivemode = 1;
    Serial.println(F("Arduino ONLINE"));
}

void loop() {
    Command::doSerialCommand();

    Update::ready();
    Update::updateCalc();
    Update::updateFast();
    Update::updateCon();
    Update::updateFine();
    Update::updateLoop();
    Update::end();
}