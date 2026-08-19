#line 1 "C:\\Users\\121\\Desktop\\0727\\RCcar\\ino\\modules\\Commands.h"
#pragma once

String* splitCommand(String commandline, char delimeter, int maxlength = 5){
    String command[maxlength] = {};
        for (int i=0;i<maxlength;i++){
            int parser = commandline.indexOf(delimeter);
            if(parser<0){
                command[i] = commandline;
                break;
            }
            command[i] = commandline.substring(0,parser);
            commandline = commandline.substring(parser+1);
        }
    return command;
}

String* getSerialCommand(){
    if(Serial.available()){
        String input = Serial.readString();
        input.trim();
        Serial.print("Command received: ");
        Serial.println(input);
        return splitCommand(input, ':', 5);
    }
    return;
}