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

uint32_t lastloopmillis = 0;
uint32_t lastcalmillis = 0;
uint32_t lastconmillis = 0;
uint32_t lastconmillis_fine = 0;
uint32_t calperiod = 0;
uint32_t conperiod = 0;
uint32_t conperiod_fine = 0;


Wheel leftwheel = Wheel(Motor_Left1,Motor_Left2,Encoder_Left,"LeftWheel");
Wheel rightwheel = Wheel(Motor_Right1,Motor_Right2,Encoder_Right,"RightWheel");
#line 26 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void ISRencoder_left();
#line 29 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void ISRencoder_right();
#line 35 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
int updateCalc();
#line 45 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
int updateCon();
#line 55 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
int updateFine();
#line 65 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
int updateLoop();
#line 73 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void setup();
#line 85 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void loop();
#line 26 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\ino.ino"
void ISRencoder_left(){
    leftwheel.onEncoderInterrupt();
}
void ISRencoder_right(){
    rightwheel.onEncoderInterrupt();
}

Displayer oled = Displayer();

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

void setup() {
    Serial.begin(115200);
    leftwheel.setup();
    rightwheel.setup();
    attachInterrupt(digitalPinToInterrupt(leftwheel.getEncoder()), ISRencoder_left, FALLING);
    attachInterrupt(digitalPinToInterrupt(rightwheel.getEncoder()), ISRencoder_right, FALLING);
    calperiod = 100;
    conperiod = 100;
    conperiod_fine = 10;
    oled.init();
}

void loop() {
    //doSerialCommand();

    //updateCalc();
    //updateCon();
    //updateFine();
    //updateLoop();
    
    //leftwheel.stop();
    //rightwheel.stop();
}
