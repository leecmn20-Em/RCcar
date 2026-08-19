#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_SSD1306.h>

const byte Encoder_Left = 2;
const byte Encoder_Right = 3;
const byte Motor_Left1 = 5;
const byte Motor_Left2 = 6;
const byte Motor_Right1 = 10;
const byte Motor_Right2 = 11;

const uint16_t Encoder_Slots = 20;

uint32_t lastloopmillis = 0;
uint32_t lastcalmillis = 0;
uint32_t lastconmillis = 0;
uint32_t lastconmillis_fine = 0;
uint32_t calperiod = 0;
uint32_t conperiod = 0;
uint32_t conperiod_fine = 0;


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

Wheel leftwheel = Wheel(Motor_Left1,Motor_Left2,Encoder_Left,"LeftWheel");
Wheel rightwheel = Wheel(Motor_Right1,Motor_Right2,Encoder_Right,"RightWheel");
void ISRencoder_left(){
    leftwheel.onEncoderInterrupt();
}
void ISRencoder_right(){
    rightwheel.onEncoderInterrupt();
}

void monitor(){
    Serial.println("---");
    Serial.print("encoder_left: ");
    Serial.println(leftwheel.getEncoderCount());
    Serial.print("encoder_right: ");
    Serial.println(rightwheel.getEncoderCount());
    Serial.print("rpm_left: ");
    Serial.println(leftwheel.getEstimatedRPM());
    Serial.print("rpm_right: ");
    Serial.println(rightwheel.getEstimatedRPM());
    Serial.print("duty_left: ");
    Serial.println(leftwheel.getCurrentDuty());
    Serial.print("duty_right: ");
    Serial.println(rightwheel.getCurrentDuty());
    Serial.println("---");
}

class CarDisplay : public Adafruit_SSD1306 {
public:
    using Adafruit_SSD1306::Adafruit_SSD1306;
    void setup(){
        setTextSize(1);
        setTextColor(WHITE);
        singleline("Display initialized.");
    }
    void updateWheel(Wheel &obj){
        print("Wheel: ");
        println(obj.getname());
        print("encoder: ");
        println(obj.getEncoderCount());
        print("rpm: ");
        println(obj.getEstimatedRPM());
        print("duty: ");
        println(obj.getCurrentDuty());
    }
    void displayBitmap(const unsigned char* bitmap){
        clearDisplay();
        drawBitmap(0,0,bitmap,128,64,1);
        display();
    }
    void singleline(String text){
        clearDisplay();
        setCursor(0,5);
        println(text);
        display();
    }
private:
};

CarDisplay oled(128,64,&Wire,-1);

void doSerialCommand(){
    if(Serial.available()){
        String input = Serial.readString();
        input.trim();
        Serial.print("Command received: ");
        Serial.println(input);
        String command[5] = {};
        for (int i=0;i<5;i++){
            int parser = input.indexOf(':');
            if(parser<0){
                command[i] = input;
                Serial.print("stored = ");
                Serial.println(command[i]);
                break;
            }
            command[i] = input.substring(0,parser);
            Serial.print("stored = ");
            Serial.println(command[i]);
            input = input.substring(parser+1);
        }

        for (int i=0;i<5;i++){
            Serial.println(command[i]);
        }

        if (command[0] == "LEFT"){
            leftwheel.setTargetRPM(command[1].toInt());
            Serial.print("Left Motor duty set to: ");
            Serial.println(command[1]);
        }
        else if (command[0] == "RIGHT"){
            rightwheel.setTargetRPM(command[1].toInt());
            Serial.print("Right Motor duty set to: ");
            Serial.println(command[1]);
        }
    }
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
        oled.clearDisplay();
        oled.setCursor(0,5);
        oled.updateWheel(leftwheel);
        oled.updateWheel(rightwheel);
        oled.display();
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
    if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED initialization failed");
        for(;;);
    }
    delay(2000);
    oled.setup();
}

void loop() {
    doSerialCommand();

    updateCalc();
    //updateCon();
    //updateFine();
    updateLoop();
    
    //leftwheel.stop();
    //rightwheel.stop();
}




