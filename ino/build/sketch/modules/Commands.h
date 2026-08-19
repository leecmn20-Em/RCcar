#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\Commands.h"
#pragma once

const uint16_t COMMAND_MAXLENGTH = 5;

inline void splitCommand(String commandline, char delimeter, String command[], int maxlength = 5){
    for (int i=0;i<maxlength;i++){
        int parser = commandline.indexOf(delimeter);
        if(parser<0){
            command[i] = commandline;
            break;
        }
        command[i] = commandline.substring(0,parser);
        commandline = commandline.substring(parser+1);
    }
}

inline bool getSerialCommand(String command[]){
    if(Serial.available()){
        String input = Serial.readString();
        input.trim();
        if(input.length()==0){
            return false;
        }
        Serial.print("Command received: ");
        Serial.println(input);
        splitCommand(input, ':', command, COMMAND_MAXLENGTH);
        return true;
    }
}