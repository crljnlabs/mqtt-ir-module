#pragma once

#include <Arduino.h>

#include <ArduinoJson.h>

namespace agent {

bool mqttPublishJson(const String& topic, JsonDocument& doc, bool retain);
void publishState();
void applyPowerMode();

}  // namespace agent
