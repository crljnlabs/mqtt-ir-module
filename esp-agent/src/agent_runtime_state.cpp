#include "agent_runtime_state.h"

#include "agent_ir.h"
#include "agent_state.h"

#include <WiFi.h>

namespace agent {

bool mqttPublishJson(const String& topic, JsonDocument& doc, bool retain) {
  if (!gMqttClient.connected()) {
    return false;
  }
  String payload;
  payload.reserve(1024);
  serializeJson(doc, payload);
  return gMqttClient.publish(topic.c_str(), payload.c_str(), retain);
}

void publishState() {
  if (!gMqttClient.connected()) {
    return;
  }
  JsonDocument doc;
  doc["pairing_hub_id"] = gPairingHubId;
  doc["debug"] = gDebugEnabled;
  doc["agent_type"] = kAgentType;
  doc["protocol_version"] = kProtocolVersion;
  doc["sw_version"] = kFirmwareVersion;
  doc["can_send"] = canSend();
  doc["can_learn"] = canLearn();
  doc["ota_supported"] = true;
  doc["reboot_required"] = gRebootRequired;
  doc["ir_tx_pin"] = gRuntimeConfig.irTxPin;
  doc["ir_rx_pin"] = gRuntimeConfig.irRxPin;
  doc["power_mode"] = gEcoMode ? "eco" : "active";
  doc["updated_at"] = nowSecondsText();
  JsonArray commands = doc["runtime_commands"].to<JsonArray>();
  commands.add("runtime/debug/get");
  commands.add("runtime/debug/set");
  commands.add("runtime/config/get");
  commands.add("runtime/config/set");
  commands.add("runtime/reboot");
  commands.add("runtime/ota/start");
  mqttPublishJson(topicState(), doc, true);
  gLastStatePublishMs = millis();
}

void applyPowerMode() {
  const bool shouldEco = !gLearningActive && (millis() > gActiveUntilMs);
  if (shouldEco == gEcoMode) {
    return;
  }
  gEcoMode = shouldEco;
  if (gEcoMode) {
    WiFi.setSleep(WIFI_PS_MIN_MODEM);
  } else {
    WiFi.setSleep(WIFI_PS_NONE);
  }
  publishState();
}

}  // namespace agent
