#include <Arduino.h>
#include "modules\DebugLog.h"
#include "modules\Commands.h"
#include "modules\Wheel.h"
#include "modules\LineSensor.h"
#include "modules\ObstacleSensor.h"

#pragma region Constants
const byte Encoder_Left = 2;
const byte Encoder_Right = 3;
const byte Motor_Left1 = 6;
const byte Motor_Left2 = 5;
const byte Motor_Right1 = 10;
const byte Motor_Right2 = 11;

const byte LineSensor::Line_Sensor_Left = 7;
const byte LineSensor::Line_Sensor_Right = 4;
const byte LineSensor::Line_Sensor_Center = 8;

const byte HCSR04::trigPin = 13;
const byte HCSR04::echoPin = 12;
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
#pragma endregion

namespace Update{
    uint32_t cmillis = 0;
}

namespace DrivePolicy {
    int drivemode = 0;

    int range = -1;
    bool onobstacle = false;
    const int obstacleStopDistanceMm = 120;

    enum TracePolicy : uint8_t {
        TRACE_STRAIGHT = 0,
        TRACE_TURN_LEFT = 1,
        TRACE_TURN_RIGHT = 2,
        TRACE_TURN_LEFT_SOFT = 3,
        TRACE_TURN_RIGHT_SOFT = 4
    };

    TracePolicy tracePolicy = TRACE_STRAIGHT;
    uint8_t lastIOL = 0;
    
    const int RPM_base = 120;
    const int RPM_softturn_inner = 10;
    const int RPM_softturn_outer = 120;
    const int RPM_sharpturn_inner = 0;
    const int RPM_sharpturn_outer = 120;
    const uint32_t WaitForsharpTurn = 600;
    uint32_t sinceSoftTurn = 0;

    const uint32_t lostTimeOut = 5000;
    uint32_t lastIOLTime = 0;

    void updateTracePolicy(uint8_t state){
        bool IRchanged = state!=lastIOL;

        if(!IRchanged){
            if(!(state & 0b010)){
                switch(tracePolicy){
                    case TRACE_TURN_LEFT_SOFT:
                        if(Update::cmillis-sinceSoftTurn>=WaitForsharpTurn){
                            tracePolicy = TRACE_TURN_LEFT;
                        }
                        break;
                    case TRACE_TURN_RIGHT_SOFT:
                        if(Update::cmillis-sinceSoftTurn>=WaitForsharpTurn){
                            tracePolicy = TRACE_TURN_RIGHT;
                        }
                        break;
                    default:
                        break;
                }
            }
        }
        else{
            switch(tracePolicy){
                case TRACE_STRAIGHT:
                    if(state & 0b100){
                        tracePolicy = TRACE_TURN_LEFT_SOFT;
                        sinceSoftTurn = Update::cmillis;
                    }
                    else if(state & 0b001){
                        tracePolicy = TRACE_TURN_RIGHT_SOFT;
                        sinceSoftTurn = Update::cmillis;
                    }
                    break;
                case TRACE_TURN_LEFT:
                case TRACE_TURN_LEFT_SOFT:
                    if(state & 0b010){
                        tracePolicy = TRACE_STRAIGHT;
                    }
                    else if(state & 0b001){
                        tracePolicy = TRACE_TURN_RIGHT_SOFT;
                        sinceSoftTurn = Update::cmillis;
                    }
                    break;
                case TRACE_TURN_RIGHT:
                case TRACE_TURN_RIGHT_SOFT:
                    if(state & 0b100){
                        tracePolicy = TRACE_TURN_LEFT_SOFT;
                        sinceSoftTurn = Update::cmillis;
                    }
                    else if(state & 0b010){
                        tracePolicy = TRACE_STRAIGHT;
                    }
                    break;
                default:
                    break;
            }

            lastIOL = state;
        }
    }

    void lineTrace(){
        if(onobstacle){
            leftwheel.stop();
            rightwheel.stop();
            lastIOLTime = Update::cmillis;
            return;
        }

        switch(tracePolicy){
            case TRACE_STRAIGHT:
                leftwheel.setTargetRPM(RPM_base);
                rightwheel.setTargetRPM(RPM_base);
                break;
            case TRACE_TURN_LEFT:
                leftwheel.setTargetRPM(RPM_sharpturn_inner);
                rightwheel.setTargetRPM(RPM_sharpturn_outer);
                break;
            case TRACE_TURN_RIGHT:
                leftwheel.setTargetRPM(RPM_sharpturn_outer);
                rightwheel.setTargetRPM(RPM_sharpturn_inner);
                break;
            case TRACE_TURN_LEFT_SOFT:
                leftwheel.setTargetRPM(RPM_softturn_inner);
                rightwheel.setTargetRPM(RPM_softturn_outer);
                break;
            case TRACE_TURN_RIGHT_SOFT:
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
        AGV_DEBUG_PRINT(F("left wheel RPM set to: "));
        AGV_DEBUG_PRINTLN(ls);
        AGV_DEBUG_PRINT(F("right wheel RPM set to: "));
        AGV_DEBUG_PRINTLN(rs);
    }

    void emergencystop(){
        drivemode = -1;
        leftwheel.stop();
        rightwheel.stop();
        AGV_DEBUG_PRINTLN(F("EMERGENCYSTOPPED"));
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

namespace IOstream{
    constexpr float STOP_ENTER_RPM = 3.0f;
    constexpr float STOP_EXIT_RPM = 5.0f;
    constexpr uint32_t STOP_ENTER_CONFIRM_MS = 400;
    constexpr uint32_t STOP_EXIT_CONFIRM_MS = 400;

    bool stopCandidateActive = false;
    bool moveCandidateActive = false;
    bool stopConfirmed = false;
    uint32_t stopCandidateStartedMs = 0;
    uint32_t moveCandidateStartedMs = 0;

    bool updateMotionStopState(float leftRpm, float rightRpm, uint32_t nowMs){
        if(stopConfirmed){
            if(leftRpm>=STOP_EXIT_RPM || rightRpm>=STOP_EXIT_RPM){
                if(!moveCandidateActive){
                    moveCandidateActive = true;
                    moveCandidateStartedMs = nowMs;
                }
                else if(nowMs-moveCandidateStartedMs>=STOP_EXIT_CONFIRM_MS){
                    stopConfirmed = false;
                    moveCandidateActive = false;
                }
            }
            else{
                moveCandidateActive = false;
            }
            return stopConfirmed;
        }

        moveCandidateActive = false;
        if(leftRpm<=STOP_ENTER_RPM && rightRpm<=STOP_ENTER_RPM){
            if(!stopCandidateActive){
                stopCandidateActive = true;
                stopCandidateStartedMs = nowMs;
            }
            else if(nowMs-stopCandidateStartedMs>=STOP_ENTER_CONFIRM_MS){
                stopConfirmed = true;
                stopCandidateActive = false;
            }
        }
        else{
            stopCandidateActive = false;
        }

        return stopConfirmed;
    }

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
        else if(strcmp(command[0], "EMERGENCYSTOP") == 0){
            DrivePolicy::emergencystop();
        }
        else if(strcmp(command[0], "LINETRACE") == 0){
            DrivePolicy::drivemode = 1;
        }
        else if(strcmp(command[0], "STOP") == 0){
            DrivePolicy::drivemode = 0;
        }
    }
    void reportStatus(){
        static bool previousObstacle = false;
        const bool enteredObstacle =
            DrivePolicy::onobstacle && !previousObstacle;
        previousObstacle = DrivePolicy::onobstacle;

        const float leftRpm = leftwheel.getEstimatedRPM();
        const float rightRpm = rightwheel.getEstimatedRPM();
        const bool stopped =
            updateMotionStopState(leftRpm, rightRpm, Update::cmillis);

        const char* event = enteredObstacle
            ? "OBSTACLE"
            : stopped ? "STOP" : "TRACING";
        Serial.print(F("AGV,"));
        Serial.print(event);
        Serial.print(',');
        Serial.print(DrivePolicy::range);
        Serial.print(',');
        Serial.print((DrivePolicy::lastIOL >> 2) & 0x01);
        Serial.print(',');
        Serial.print((DrivePolicy::lastIOL >> 1) & 0x01);
        Serial.print(',');
        Serial.print(DrivePolicy::lastIOL & 0x01);
        Serial.print(',');
        Serial.print(leftRpm, 2);
        Serial.print(',');
        Serial.println(rightRpm, 2);
    }
}

namespace Update {
    uint32_t lastcalmillis = 0;
    uint32_t lastcalmillis_fast = 0;
    uint32_t lastconmillis = 0;
    uint32_t lastconmillis_fine = 0;
    uint32_t lastserialmillis = 0;
    uint32_t calperiod = 1000;
    uint32_t calperiod_fast = 1000;
    uint32_t conperiod = 1000;
    uint32_t conperiod_fine = 1000;
    uint32_t serialperiod = 200;

    void init(){
        lastserialmillis = 0;
        lastcalmillis = 0;
        lastcalmillis_fast = 0;
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
        AGV_DEBUG_PRINTLN(F("=========="));
        AGV_DEBUG_PRINT(F("Drivemode: "));
        AGV_DEBUG_PRINTLN(DrivePolicy::drivemode);
        AGV_DEBUG_PRINT(F("Left wheel: cur_duty "));
        AGV_DEBUG_PRINT(leftwheel.getCurrentDuty());
        AGV_DEBUG_PRINT(F(" / tgt_duty "));
        AGV_DEBUG_PRINT(leftwheel.getTargetDuty());
        AGV_DEBUG_PRINT(F(" / cur_RPM "));
        AGV_DEBUG_PRINTLN(leftwheel.getEstimatedRPM());
        AGV_DEBUG_PRINT(F("Right wheel: cur_duty "));
        AGV_DEBUG_PRINT(rightwheel.getCurrentDuty());
        AGV_DEBUG_PRINT(F(" / tgt_duty "));
        AGV_DEBUG_PRINT(rightwheel.getTargetDuty());
        AGV_DEBUG_PRINT(F(" / cur_RPM "));
        AGV_DEBUG_PRINTLN(rightwheel.getEstimatedRPM());
        AGV_DEBUG_PRINT(F("on-line?: "));
        AGV_DEBUG_PRINT(DrivePolicy::lastIOL & 0b100? 'O':'X');
        AGV_DEBUG_PRINT(F(" - "));
        AGV_DEBUG_PRINT(DrivePolicy::lastIOL & 0b010? 'O':'X');
        AGV_DEBUG_PRINT(F(" - "));
        AGV_DEBUG_PRINTLN(DrivePolicy::lastIOL & 0b001? 'O':'X');
        AGV_DEBUG_PRINT(F("Obstacle? "));
        if(DrivePolicy::onobstacle){
            AGV_DEBUG_PRINTLN(F("yes"));
        }
        else{
            AGV_DEBUG_PRINTLN(F("no"));
        }
        AGV_DEBUG_PRINT(F("Current trace policy: "));
        switch(DrivePolicy::tracePolicy){
            case DrivePolicy::TRACE_STRAIGHT:
                AGV_DEBUG_PRINTLN(F("Going straight"));
                break;
            case DrivePolicy::TRACE_TURN_LEFT:
                AGV_DEBUG_PRINTLN(F("Turning left"));
                break;
            case DrivePolicy::TRACE_TURN_RIGHT:
                AGV_DEBUG_PRINTLN(F("Turning right"));
                break;
            case DrivePolicy::TRACE_TURN_LEFT_SOFT:
                AGV_DEBUG_PRINTLN(F("Turning left softly"));
                break;
            case DrivePolicy::TRACE_TURN_RIGHT_SOFT:
                AGV_DEBUG_PRINTLN(F("Turning right softly"));
                break;
            default:
                AGV_DEBUG_PRINTLN(F("Can't find the policy"));
                break;
        }
    }

    int updateCalc(){
        if(cmillis-lastcalmillis>=calperiod){
            leftwheel.estimateAverageRPM(cmillis-lastcalmillis);
            rightwheel.estimateAverageRPM(cmillis-lastcalmillis);

            lastcalmillis = cmillis;
            return 1;
        }
        return 0;
    }

    int updateFast(){
        if(cmillis-lastcalmillis_fast>=calperiod_fast){
            if(HCSR04::readDistance(DrivePolicy::range)){
                if(DrivePolicy::range>=0){
                    DrivePolicy::onobstacle =
                        DrivePolicy::range >= 0 &&
                        DrivePolicy::range<DrivePolicy::obstacleStopDistanceMm;
                }
            }

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

    int updateSerial(){
        if(cmillis-lastserialmillis>=serialperiod){
            //monitor();
            IOstream::reportStatus();

            lastserialmillis = cmillis;
            return 1;
        }
        return 0;
    }

    void updateInstant(){
        HCSR04::updateMeasurement();
    }
}

void setup() {
    Serial.begin(115200);
    AGV_DEBUG_PRINTLN(F("Arduino Booting..."));
    leftwheel.setup();
    rightwheel.setup();
    attachInterrupt(digitalPinToInterrupt(leftwheel.getEncoder()), ISRencoder_left, FALLING);
    attachInterrupt(digitalPinToInterrupt(rightwheel.getEncoder()), ISRencoder_right, FALLING);
    Update::calperiod = 100;
    Update::calperiod_fast = 5;
    Update::conperiod = 20;
    Update::conperiod_fine = 10;
    Update::serialperiod = 200;
    HCSR04::setup();
    LineSensor::setupSensors();
    DrivePolicy::drivemode = 1;
    AGV_DEBUG_PRINTLN(F("Arduino ONLINE"));
}

void loop() {
    IOstream::doSerialCommand();

    Update::ready();
    Update::updateCalc();
    Update::updateFast();
    Update::updateCon();
    Update::updateFine();
    Update::updateSerial();
    Update::updateInstant();
    Update::end();
}
