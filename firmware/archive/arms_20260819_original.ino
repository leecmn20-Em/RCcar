#include <Servo.h>
#include "displayer.h"

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

Servo1 base(3);
Servo1 shoulder(5);
Servo1 forearm(6);
Servo1 upperarm(9);
Servo1 gripper;

int baseAngle = 90;
int shoulderAngle = 90;
int upperarmAngle = 90;
int forearmAngle = 90;
int gripperAngle = 90;

Displayer oled = Displayer(128,64,&Wire,-1);

uint32_t now = 0;

uint32_t lastloopmillis = 0;
uint16_t loopperiod = 1000;
bool do_loop = true;
int updateLoop(bool do_for){
    if(!do_for) return 2;
    if(now-lastloopmillis>=loopperiod){
        oled.clear();
        oled.print("Base: ");
        oled.println(base.read());
        oled.print("Shoulder: ");
        oled.println(shoulder.read());
        oled.print("Forearm: ");
        oled.println(forearm.read());
        oled.print("Upperarm: ");
        oled.println(upperarm.read());
        oled.display();
        lastloopmillis = now;
        return 1;
    }
    return 0;
}

uint32_t lastconmillis = 0;
uint16_t conperiod = 100;
bool do_con = true;
int updateCon(bool do_for){
    if(!do_for) return 2;
    if(now-lastconmillis>=conperiod){
        base.follow();
        shoulder.follow();
        forearm.follow();
        upperarm.follow();
        lastconmillis = now;
        return 1;
    }
    return 0;
}

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
                break;
            }
            command[i] = input.substring(0,parser);
            input = input.substring(parser+1);
        }

        for (int i=0;i<5;i++){
            Serial.print(command[i]);
        }
        Serial.println();

        if(command[0] == "pause"){
            do_con = false;
            base.detach();
            shoulder.detach();
            forearm.detach();
            upperarm.detach();
            Serial.println("paused");
        }
        else if(command[0] == "resume"){
            base.attach();
            shoulder.attach();
            forearm.attach();
            upperarm.attach();
            do_con = true;
            Serial.println("resumed");
        }
        else{
            base.write(command[0].toInt());
            shoulder.write(command[1].toInt());
            forearm.write(command[2].toInt());
            upperarm.write(command[3].toInt());
        }
    }
}

void setup() {
  Serial.begin(115200);
  base.attach();
  base.write(baseAngle);
  shoulder.attach();
  shoulder.write(shoulderAngle);
  forearm.attach();
  forearm.write(forearmAngle);
  upperarm.attach();
  upperarm.write(upperarmAngle);
  oled.init();
}

void loop() {
  now = millis();
  doSerialCommand();
  updateLoop(do_loop);
  shoulder.Servo::write(70);
  updateCon(do_con);
}
