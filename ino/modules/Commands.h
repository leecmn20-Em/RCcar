#pragma once

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
    }
}