#pragma once

#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

const uint8_t COMMAND_MAXLENGTH = 5;
const uint8_t COMMAND_BUFFER_SIZE = 64;

inline void splitCommand(char* commandline, char delimeter, char* command[], int maxlength = 5){
    for(int i=0; i<maxlength; i++){
        command[i] = commandline;

        char* parser = strchr(commandline, delimeter);
        if(parser == nullptr){
            break;
        }

        *parser = '\0';
        commandline = parser + 1;
    }
}

inline bool getSerialCommand(char* command[]){
    static char input[COMMAND_BUFFER_SIZE];
    static uint8_t inputLength = 0;
    static uint32_t lastByteMillis = 0;
    static bool receiving = false;
    static bool overflow = false;

    while(Serial.available() > 0){
        char received = static_cast<char>(Serial.read());

        receiving = true;
        lastByteMillis = millis();

        // Arduino String concatenation ignores embedded null characters.
        if(received == '\0'){
            continue;
        }

        if(inputLength < COMMAND_BUFFER_SIZE - 1){
            input[inputLength++] = received;
        }
        else{
            overflow = true;
        }
    }

    if(!receiving || millis() - lastByteMillis < Serial.getTimeout()){
        return false;
    }

    receiving = false;

    if(overflow){
        inputLength = 0;
        overflow = false;
        return false;
    }

    input[inputLength] = '\0';

    char* first = input;
    while(*first != '\0' && isspace(static_cast<unsigned char>(*first))){
        first++;
    }

    char* last = input + inputLength;
    while(last > first && isspace(static_cast<unsigned char>(last[-1]))){
        last--;
    }
    *last = '\0';

    if(first != input){
        memmove(input, first, static_cast<size_t>(last - first) + 1);
    }

    inputLength = 0;

    if(input[0] == '\0'){
        return false;
    }

    Serial.print(F("Command received: "));
    Serial.println(input);

    splitCommand(input, ':', command, COMMAND_MAXLENGTH);
    return true;
}
