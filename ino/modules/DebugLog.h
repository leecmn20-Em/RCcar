#pragma once

#include <Arduino.h>

#ifndef ENABLE_AGV_DEBUG
#define ENABLE_AGV_DEBUG 0
#endif

#if ENABLE_AGV_DEBUG
#define AGV_DEBUG_PRINT(...) Serial.print(__VA_ARGS__)
#define AGV_DEBUG_PRINTLN(...) Serial.println(__VA_ARGS__)
#else
#define AGV_DEBUG_PRINT(...) do { } while (false)
#define AGV_DEBUG_PRINTLN(...) do { } while (false)
#endif
