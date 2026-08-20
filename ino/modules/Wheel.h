#pragma once

const uint16_t Encoder_Slots = 20;

class Wheel {
public:
    Wheel(byte pin1, byte pin2, byte pinencoder){
        in1 = pin1;
        in2 = pin2;
        enc = pinencoder;
        enc_count = 0;
        rpm_tgt = 0.0f;
        rpm_est = 0.0f;
        duty_cur = 0;
        duty_tgt = 0;
        dir_tgt = 0;
        dir_est = 1;
        rpm_prev = 0.0f;
        rpm_pp = 0.0f;
        err_prev = 0.0f;
        duty_comp = 0.0f;
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
    double getEstimatedRPM(){
        return rpm_est;
    }
    void onEncoderInterrupt(){
        enc_count++;
    }
    void estimateRPM(uint32_t timespan){
        if(timespan==0){
            return;
        }
        uint32_t c;
        noInterrupts();
        c = enc_count;
        enc_count =0;
        interrupts();
        rpm_pp = rpm_prev;
        rpm_prev = rpm_est;
        rpm_est = float(c)/Encoder_Slots * float(60000)/timespan;
    }
    void setTargetRPM(float rpm){
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
    void resetController(){
        duty_comp = 0.0f;
        duty_tgt = 0;
        err_prev = 0.0f;
    }
    void stop(){
        setTargetRPM(0);
        setMotorPower(0);
        duty_cur=0;
        resetController();
    }
    void followRPM(uint32_t dtmillis){
        if(dtmillis == 0){
            return;
        }
        if(rpm_tgt == 0.0f){
            duty_tgt = 0;
            return;
        }
        const float dt = dtmillis * 0.001f;
        const float err = rpm_tgt - rpm_est;

        float p_term = Kp*(err-err_prev);

        float d_term = -Kd*(rpm_est-2.0f*rpm_prev+rpm_pp)/dt;
        d_term = constrain(d_term,D_MIN,D_MAX);

        float i_term = Ki*err*dt;
        i_term = constrain(i_term,I_MIN,I_MAX);

        float comp = p_term + i_term + d_term;
        comp = constrain(comp, comp_MIN, comp_MAX);
        
        duty_comp += comp;
        duty_comp = constrain(duty_comp, (float)duty_Min, (float)duty_Max);

        duty_tgt = constrain((int)duty_comp,duty_Min,duty_Max);

        err_prev = err;
    }
    void updateMotor(){
        if(dir_tgt == dir_est){
            int duty_err = duty_tgt - duty_cur;
            if(duty_err>0){
                duty_cur += min(10,duty_err);
            }
            else if(duty_err<0){
                duty_cur -= min(10,-duty_err);
            }
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
    int getTargetDuty(){
        return duty_tgt;
    }
    void setPID(float p,float i,float d){
        Kp = p;
        Ki = i;
        Kd = d;
    }
    float getPID(){
        return Kp, Ki, Kd;
    }
private:
    byte in1;
    byte in2;
    byte enc;
    volatile uint32_t enc_count;
    float rpm_est;
    float rpm_tgt;
    int dir_tgt;
    int dir_est;
    int duty_cur;
    int duty_tgt;

    float Kp = 0.25f;
    float Kd = 0.0f;
    float Ki = 0.1f;
    float err_prev;
    float duty_comp;
    float rpm_prev;
    float rpm_pp;
    static const float D_MAX = 5.0f;
    static const float D_MIN = -5.0f;
    static const float I_MAX = 20.0f;
    static const float I_MIN = -20.0f;
    static const int comp_MAX = 30;
    static const int comp_MIN = -30;

    static const int duty_Max = 255;
    static const int duty_Min = 0;
};