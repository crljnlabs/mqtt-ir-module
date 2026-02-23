#include <Arduino.h>

#include "agent_bootstrap.h"
#include "agent_ir.h"
#include "agent_mqtt.h"
#include "agent_runtime_state.h"
#include "agent_state.h"

#include <algorithm>

void setup() {
  Serial.begin(115200);
  delay(100);

  agent::gAgentId = agent::buildAgentId();
  agent::loadPersistedState();
  agent::configureWifiAndRuntime();
  agent::initIrHardware();

  agent::gMqttClient.setClient(agent::gNetClient);
  agent::gMqttClient.setCallback(agent::onMqttMessage);
  agent::gMqttClient.setBufferSize(agent::kMqttBufferSize);

  agent::markActivity();
  agent::applyPowerMode();
}

void loop() {
  agent::pollSetupButton();

  if (!agent::gMqttClient.connected()) {
    const unsigned long now = millis();
    if (now >= agent::gNextReconnectAtMs) {
      if (agent::connectMqtt()) {
        agent::gReconnectDelayMs = agent::kMqttReconnectMinMs;
        agent::gNextReconnectAtMs = now + agent::gReconnectDelayMs;
      } else {
        agent::gReconnectDelayMs = std::min(agent::gReconnectDelayMs * 2UL, agent::kMqttReconnectMaxMs);
        agent::gNextReconnectAtMs = now + agent::gReconnectDelayMs;
      }
    }
  } else {
    agent::gMqttClient.loop();
    if (millis() - agent::gLastStatePublishMs > agent::kStateHeartbeatMs) {
      agent::publishState();
    }
  }

  agent::applyPowerMode();

  if (agent::gPendingReboot && millis() >= agent::gRebootAtMs) {
    delay(50);
    ESP.restart();
  }

  if (agent::gEcoMode) {
    delay(25);
  } else {
    delay(5);
  }
}
