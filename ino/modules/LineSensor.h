#pragma once

namespace LineSensor{
    extern const byte Line_Sensor_Left;
    extern const byte Line_Sensor_BodyCenter;
    extern const byte Line_Sensor_Right;

    const uint16_t DEBOUNCE_MS = 20;

    struct SensorState {
        bool raw;
        bool stable;
        uint32_t changedAt;
    };

    SensorState leftState = {false, false, 0};
    SensorState bodyCenterState = {false, false, 0};
    SensorState rightState = {false, false, 0};

    inline void initializeState(SensorState &state, byte pin){
        bool reading = digitalRead(pin) == HIGH;
        state.raw = reading;
        state.stable = reading;
        state.changedAt = millis();
    }

    void setupSensors(){
        pinMode(Line_Sensor_Left, INPUT);
        pinMode(Line_Sensor_BodyCenter, INPUT);
        pinMode(Line_Sensor_Right, INPUT);

        initializeState(leftState, Line_Sensor_Left);
        initializeState(bodyCenterState, Line_Sensor_BodyCenter);
        initializeState(rightState, Line_Sensor_Right);
    }

    inline void updateState(SensorState &state, bool reading, uint32_t now){
        if(reading != state.raw){
            state.raw = reading;
            state.changedAt = now;
        }

        if(state.stable != state.raw && now-state.changedAt >= DEBOUNCE_MS){
            state.stable = state.raw;
        }
    }

    inline void update(uint32_t now){
        updateState(leftState, digitalRead(Line_Sensor_Left) == HIGH, now);
        updateState(bodyCenterState, digitalRead(Line_Sensor_BodyCenter) == HIGH, now);
        updateState(rightState, digitalRead(Line_Sensor_Right) == HIGH, now);
    }

    inline bool onLine_left(){
        return leftState.stable;
    }

    inline bool onLine_bodyCenter(){
        return bodyCenterState.stable;
    }

    inline bool onLine_right(){
        return rightState.stable;
    }
}
