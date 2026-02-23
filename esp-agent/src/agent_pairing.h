#pragma once

#include <Arduino.h>

namespace agent {

bool isHubAuthorized(const String& hubId);
void handlePairingOpen(const byte* payload, unsigned int length);
void handlePairingAccept(const String& topic, const byte* payload, unsigned int length);
void handlePairingUnpair(const String& topic, const byte* payload, unsigned int length);

}  // namespace agent
