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