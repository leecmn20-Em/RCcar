#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\Servo1.h"
#pragma once

#include <Servo.h>

class Servo1 : public Servo {
public:
    Servo1() : Servo() {};
    Servo1(int P) : Servo(), pin(P) {};
    void setPin(int n){
        pin = n;
    }
    int getPin(){
        return pin;
    }
    void attach(){
        Servo::attach(pin);
    }
    void write(int angle){
        angle_tgt = angle;
    }
    void follow(){
        int angle_cur=read();
        if(angle_tgt>angle_cur){
            angle_cur += 1;
            Servo::write(angle_cur);
        }
        else if (angle_tgt<angle_cur){
            angle_cur -= 1;
            Servo::write(angle_cur);
        }
        
    }
private:
    int angle_tgt;
    int pin;
};