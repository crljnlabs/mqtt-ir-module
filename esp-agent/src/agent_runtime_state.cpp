#include "agent_runtime_state.h"

#include "agent_ir.h"
#include "agent_logs.h"
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

  // state/hub — pairing binding (retained)
  {
    JsonDocument doc;
    doc["id"] = gPairingHubId;
    mqttPublishJson(topicStateHub(), doc, true);
  }

  // state/version — firmware + protocol versions (retained)
  {
    JsonDocument doc;
    doc["sw_version"] = kFirmwareVersion;
    doc["system"] = kSystemVersion;
    doc["send"] = kSendVersion;
    doc["learn"] = kLearnVersion;
    mqttPublishJson(topicStateVersion(), doc, true);
  }

  // state/agent — static capabilities (retained)
  {
    JsonDocument doc;
    doc["agent_type"] = kAgentType;
    doc["can_send"] = canSend();
    doc["can_learn"] = canLearn();
    doc["ota_supported"] = true;
    mqttPublishJson(topicStateAgent(), doc, true);
  }

  // state/runtime — mutable operational state (retained)
  {
    JsonDocument doc;
    doc["debug"] = gDebugEnabled;
    doc["reboot_required"] = gRebootRequired;
    doc["ir_tx_pin"] = gRuntimeConfig.irTxPin;
    doc["ir_rx_pin"] = gRuntimeConfig.irRxPin;
    mqttPublishJson(topicStateRuntime(), doc, true);
  }

  // state/diagnostics — point-in-time data, not retained
  {
    JsonDocument doc;
    doc["free_heap"] = ESP.getFreeHeap();
    doc["last_reset_reason"] = currentResetReasonText();
    doc["last_reset_code"] = currentResetReasonCode();
    doc["last_reset_crash"] = currentResetIndicatesCrash();
    mqttPublishJson(topicStateDiagnostics(), doc, false);
  }

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
