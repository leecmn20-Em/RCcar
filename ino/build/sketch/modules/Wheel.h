#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\Wheel.h"
#pragma once

const uint16_t Encoder_Slots = 20;

class Wheel {
public:
    Wheel(byte pin1, byte pin2, byte pinencoder, String wheelname = "Null"){
        in1 = pin1;
        in2 = pin2;
        enc = pinencoder;
        name = wheelname;
        enc_count = 0;
        rpm_tgt = 0;
        duty_cur = 0;
        duty_tgt = 0;
        dir_tgt = 0;
        dir_est = 1;
    }
    void setup(){
        pinMode(in1, OUTPUT);
        pinMode(in2, OUTPUT);
        pinMode(enc, INPUT_PULLUP);
    }
    byte getInput1(){
        return in1;
    }
    byte getInput2(){
        return in2;
    }
    byte getEncoder(){
        return enc;
    }
    uint32_t getEncoderCount(){
        return enc_count;
    }
    uint32_t getEstimatedRPM(){
        return rpm_est;
    }
    String getname(){
        return name;
    }
    void onEncoderInterrupt(){
        enc_count++;
    }
    void estimateRPM(int timespan){
        rpm_est = double(enc_count)/Encoder_Slots * double(60000)/timespan;
        enc_count = 0;
    }
    void setMotorPower(int s){
        if(s>0){
            analogWrite(in1, s);
            analogWrite(in2, 0);
        }
        else if(s<0){
            analogWrite(in1, 0);
            analogWrite(in2, -s);
        }
        else{
            analogWrite(in1, 0);
            analogWrite(in2, 0);
        }
    }
    void stop(){
        analogWrite(in1, 0);
        analogWrite(in2, 0);
    }
    void setTargetRPM(double rpm){
        if(rpm>0){
            rpm_tgt = rpm;
            dir_tgt = 1;
        }
        else if(rpm<0){
            rpm_tgt = -rpm;
            dir_tgt = -1;
        }
        else{
            rpm_tgt = 0;
            dir_tgt = 0;
        }
    }
    void followRPM(){
        double rpm_err = rpm_tgt - rpm_est;
        if(rpm_err>0){
            duty_tgt += 1;
        }
        else if(rpm_err<0){
            duty_tgt -= 1;
        }
        else;
        if(duty_tgt>duty_Max){
            duty_tgt=duty_Max;
        }
        if(duty_tgt<duty_Min){
            duty_tgt=duty_Min;
        }
    }
    void updateMotor(){
        if(dir_tgt == dir_est){
            if(duty_tgt>duty_cur){
                duty_cur += 1;
            }
            else if(duty_tgt<duty_cur){
                duty_cur -= 1;
            }
            else;
            setMotorPower(duty_cur*dir_tgt);
        }
        else if (dir_tgt != dir_est){
            if (rpm_est<5 && duty_cur<10){
                setMotorPower(duty_cur*dir_tgt);
            }
            else{
                if(duty_cur>10){
                    duty_cur -= 10;
                }
                else{
                    duty_cur -= 1;
                }
                if(duty_cur<duty_Min){
                    duty_cur=duty_Min;
                }
                setMotorPower(duty_cur*dir_est);
            }
        }
    }
    int getCurrentDuty(){
        return duty_cur;
    }
private:
    byte in1;
    byte in2;
    byte enc;
    String name;
    volatile uint32_t enc_count;
    double rpm_est;
    double rpm_tgt;
    int dir_tgt;
    int dir_est;
    int duty_cur;
    int duty_tgt;

    static const int duty_Max = 255;
    static const int duty_Min = 0;
};