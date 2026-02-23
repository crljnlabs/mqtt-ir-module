#pragma once

#include <Arduino.h>

namespace agent {

void onMqttMessage(char* topicChars, byte* payload, unsigned int length);
bool connectMqtt();

}  // namespace agent
