#pragma once

#include <Arduino.h>

#include <ArduinoJson.h>

namespace agent {

void handleCommand(const String& command, JsonObjectConst payload);

}  // namespace agent
