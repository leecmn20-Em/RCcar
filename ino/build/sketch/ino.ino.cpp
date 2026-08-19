#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
#include <Arduino.h>
#include "modules\Commands.h"
#include "modules\Servo1.h"
#include "modules\Displayer.h"
#include "modules\Arms.h"
#include "modules\Wheel.h"

const byte Encoder_Left = 2;
const byte Encoder_Right = 3;
const byte Motor_Left1 = 5;
const byte Motor_Left2 = 6;
const byte Motor_Right1 = 10;
const byte Motor_Right2 = 11;

Wheel leftwheel = Wheel(Motor_Left1,Motor_Left2,Encoder_Left,"LeftWheel");
Wheel rightwheel = Wheel(Motor_Right1,Motor_Right2,Encoder_Right,"RightWheel");
#line 17 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void ISRencoder_left();
#line 20 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void ISRencoder_right();
#line 126 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void setup();
#line 139 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void loop();
#line 17 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void ISRencoder_left(){
    leftwheel.onEncoderInterrupt();
}
void ISRencoder_right(){
    rightwheel.onEncoderInterrupt();
}

Displayer oled = Displayer();

namespace DrivePolicy {
    int drivemode = 0;

    void drive(){
        if(drivemode == 0){
            leftwheel.stop();
            rightwheel.stop();
        }
    }

    void drive(int mode){
        drivemode = mode;
        drive();
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
        leftwheel.stop();
        rightwheel.stop();
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
    uint32_t lastloopmillis = 0;
    uint32_t lastcalmillis = 0;
    uint32_t lastconmillis = 0;
    uint32_t lastconmillis_fine = 0;
    uint32_t calperiod = 1000;
    uint32_t conperiod = 1000;
    uint32_t conperiod_fine = 1000;

    void init(){
        lastloopmillis = 0;
        lastcalmillis = 0;
        lastconmillis = 0;
        lastconmillis_fine = 0;
    }

    int updateCalc(){
        if(millis()-lastcalmillis>=calperiod){
            leftwheel.estimateRPM(calperiod);
            rightwheel.estimateRPM(calperiod);
            lastcalmillis = millis();
            return 1;
        }
        return 0;
    }

    int updateCon(){
        if(millis()-lastconmillis>=conperiod){
            leftwheel.followRPM();
            rightwheel.followRPM();
            lastconmillis = millis();
            return 1;
        }
        return 0;
    }

    int updateFine(){
        if(millis()-lastconmillis_fine>=conperiod_fine){
            leftwheel.updateMotor();
            rightwheel.updateMotor();
            lastconmillis_fine = millis();
            return 1;
        }
        return 0;
    }

    int updateLoop(){
        if(millis()-lastloopmillis>=1000){
            lastloopmillis = millis();
            return 1;
        }
        return 0;
    }
}

void setup() {
    Serial.begin(115200);
    leftwheel.setup();
    rightwheel.setup();
    attachInterrupt(digitalPinToInterrupt(leftwheel.getEncoder()), ISRencoder_left, FALLING);
    attachInterrupt(digitalPinToInterrupt(rightwheel.getEncoder()), ISRencoder_right, FALLING);
    Update::calperiod = 100;
    Update::conperiod = 100;
    Update::conperiod_fine = 10;
    oled.init();
    DrivePolicy::drive(0);
}

void loop() {
    doSerialCommand();

    Update::updateCalc();
    Update::updateCon();
    Update::updateFine();
    Update::updateLoop();

}
