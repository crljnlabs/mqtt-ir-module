#include "agent_state.h"

#include <algorithm>
#include <cstdlib>
#include <cstdio>

namespace agent {

Preferences gPrefs;
WiFiClient gNetClient;
PubSubClient gMqttClient(gNetClient);

RuntimeConfig gRuntimeConfig;
String gAgentId;
String gPairingHubId;
bool gDebugEnabled = false;
bool gRebootRequired = false;
bool gLearningActive = false;
bool gEcoMode = false;
unsigned long gActiveUntilMs = 0;
unsigned long gLastStatePublishMs = 0;
unsigned long gNextReconnectAtMs = 0;
unsigned long gReconnectDelayMs = kMqttReconnectMinMs;
bool gPendingReboot = false;
unsigned long gRebootAtMs = 0;
String gPairingSessionId;
String gPairingNonce;

IRsend* gIrSender = nullptr;
IRrecv* gIrReceiver = nullptr;
decode_results gDecodeResults;

bool isValidPin(int pin) {
  return pin >= 0 && pin <= 39;
}

String normalizeSha256(const String& value) {
  String normalized = value;
  normalized.trim();
  normalized.toLowerCase();
  return normalized;
}

bool isHexSha256(const String& value) {
  if (value.length() != 64) {
    return false;
  }
  for (size_t i = 0; i < value.length(); i++) {
    const char c = value.charAt(i);
    const bool digit = (c >= '0' && c <= '9');
    const bool alpha = (c >= 'a' && c <= 'f');
    if (!digit && !alpha) {
      return false;
    }
  }
  return true;
}

String nowSecondsText() {
  const float seconds = static_cast<float>(millis()) / 1000.0f;
  return String(seconds, 3);
}

String topicState() {
  return String("ir/agents/") + gAgentId + "/state";
}

String topicStatus() {
  return String("ir/agents/") + gAgentId + "/status";
}

String topicCommands() {
  return String("ir/agents/") + gAgentId + "/cmd/#";
}

String topicInstallationState() {
  return String("ir/agents/") + gAgentId + "/installation/state";
}

String topicPairingAccept() {
  return String("ir/pairing/accept/+/") + gAgentId;
}

String topicPairingUnpair() {
  return String("ir/pairing/unpair/") + gAgentId;
}

String topicPairingUnpairAck() {
  return String("ir/pairing/unpair_ack/") + gAgentId;
}

String topicResponse(const String& hubId, const String& requestId) {
  return String("ir/hubs/") + hubId + "/agents/" + gAgentId + "/resp/" + requestId;
}

void saveRuntimeConfig() {
  gPrefs.begin(kPrefsNamespace, false);
  gPrefs.putString("mqtt_host", gRuntimeConfig.mqttHost);
  gPrefs.putUShort("mqtt_port", gRuntimeConfig.mqttPort);
  gPrefs.putString("mqtt_user", gRuntimeConfig.mqttUser);
  gPrefs.putString("mqtt_pass", gRuntimeConfig.mqttPass);
  gPrefs.end();
}

void savePairingHubId(const String& hubId) {
  gPairingHubId = hubId;
}

void saveDebugFlag(bool enabled) {
  gDebugEnabled = enabled;
}

void saveRebootRequired(bool required) {
  gRebootRequired = required;
}

void loadPersistedState() {
  gPrefs.begin(kPrefsNamespace, false);
  gRuntimeConfig.mqttHost = gPrefs.getString("mqtt_host", "");
  gRuntimeConfig.mqttPort = gPrefs.getUShort("mqtt_port", kDefaultMqttPort);
  if (gRuntimeConfig.mqttPort == 0) {
    gRuntimeConfig.mqttPort = kDefaultMqttPort;
  }
  gRuntimeConfig.mqttUser = gPrefs.getString("mqtt_user", "");
  gRuntimeConfig.mqttPass = gPrefs.getString("mqtt_pass", "");
  gPrefs.end();
}

namespace {

bool parseBoolStateValue(JsonVariantConst value, bool fallback) {
  if (value.is<bool>()) {
    return value.as<bool>();
  }
  if (value.is<int>()) {
    return value.as<int>() != 0;
  }
  if (value.is<unsigned int>()) {
    return value.as<unsigned int>() != 0U;
  }
  if (value.is<long>()) {
    return value.as<long>() != 0L;
  }
  if (value.is<unsigned long>()) {
    return value.as<unsigned long>() != 0UL;
  }
  if (value.is<float>()) {
    return value.as<float>() != 0.0f;
  }
  if (value.is<double>()) {
    return value.as<double>() != 0.0;
  }
  if (!value.is<const char*>()) {
    return fallback;
  }
  String text = String(value.as<const char*>());
  text.trim();
  text.toLowerCase();
  if (text == "1" || text == "true" || text == "yes" || text == "y" || text == "on") {
    return true;
  }
  if (text == "0" || text == "false" || text == "no" || text == "n" || text == "off") {
    return false;
  }
  return fallback;
}

int parseStatePin(JsonVariantConst value, int fallback) {
  if (value.is<int>()) {
    return value.as<int>();
  }
  if (value.is<unsigned int>()) {
    return static_cast<int>(value.as<unsigned int>());
  }
  if (value.is<long>()) {
    return static_cast<int>(value.as<long>());
  }
  if (value.is<unsigned long>()) {
    return static_cast<int>(value.as<unsigned long>());
  }
  if (value.is<const char*>()) {
    return parsePin(String(value.as<const char*>()), fallback);
  }
  return fallback;
}

}  // namespace

bool applyRuntimeStateSnapshot(JsonObjectConst payload) {
  if (payload.isNull()) {
    return false;
  }

  bool pinsChanged = false;
  const JsonVariantConst pairingHubId = payload["pairing_hub_id"];
  if (!pairingHubId.isUnbound()) {
    gPairingHubId = String(pairingHubId | "");
    gPairingHubId.trim();
  }
  const JsonVariantConst debugValue = payload["debug"];
  if (!debugValue.isUnbound()) {
    gDebugEnabled = parseBoolStateValue(debugValue, gDebugEnabled);
  }
  const JsonVariantConst rebootRequired = payload["reboot_required"];
  if (!rebootRequired.isUnbound()) {
    gRebootRequired = parseBoolStateValue(rebootRequired, gRebootRequired);
  }
  const JsonVariantConst rxPin = payload["ir_rx_pin"];
  if (!rxPin.isUnbound()) {
    const int nextRx = parseStatePin(rxPin, gRuntimeConfig.irRxPin);
    if (isValidPin(nextRx)) {
      pinsChanged = pinsChanged || (nextRx != gRuntimeConfig.irRxPin);
      gRuntimeConfig.irRxPin = nextRx;
    }
  }
  const JsonVariantConst txPin = payload["ir_tx_pin"];
  if (!txPin.isUnbound()) {
    const int nextTx = parseStatePin(txPin, gRuntimeConfig.irTxPin);
    if (isValidPin(nextTx)) {
      pinsChanged = pinsChanged || (nextTx != gRuntimeConfig.irTxPin);
      gRuntimeConfig.irTxPin = nextTx;
    }
  }

  return pinsChanged;
}

uint16_t parseMqttPort(const String& value, uint16_t fallback) {
  String trimmed = value;
  trimmed.trim();
  if (trimmed.isEmpty()) {
    return fallback;
  }
  const long parsed = strtol(trimmed.c_str(), nullptr, 10);
  if (parsed < 1 || parsed > 65535) {
    return fallback;
  }
  return static_cast<uint16_t>(parsed);
}

int parsePin(const String& value, int fallback) {
  String trimmed = value;
  trimmed.trim();
  if (trimmed.isEmpty()) {
    return fallback;
  }
  const long parsed = strtol(trimmed.c_str(), nullptr, 10);
  if (!isValidPin(static_cast<int>(parsed))) {
    return fallback;
  }
  return static_cast<int>(parsed);
}

void markActivity() {
  gActiveUntilMs = millis() + kActiveWindowMs;
}

void scheduleReboot(unsigned long delayMs) {
  gPendingReboot = true;
  gRebootAtMs = millis() + delayMs;
}

bool parseCommandTopic(const String& topic, String& commandOut) {
  const String prefix = String("ir/agents/") + gAgentId + "/cmd/";
  if (!topic.startsWith(prefix)) {
    return false;
  }
  commandOut = topic.substring(prefix.length());
  commandOut.trim();
  return !commandOut.isEmpty();
}

bool parseAcceptTopic(const String& topic, String& sessionOut) {
  const String prefix = "ir/pairing/accept/";
  if (!topic.startsWith(prefix)) {
    return false;
  }
  const int lastSlash = topic.lastIndexOf('/');
  if (lastSlash <= 0) {
    return false;
  }
  const String agentFromTopic = topic.substring(lastSlash + 1);
  if (agentFromTopic != gAgentId) {
    return false;
  }
  sessionOut = topic.substring(prefix.length(), lastSlash);
  sessionOut.trim();
  return !sessionOut.isEmpty();
}

bool parsePayloadObject(const byte* payload, unsigned int length, JsonDocument& doc) {
  const DeserializationError error = deserializeJson(doc, payload, length);
  return !error && doc.is<JsonObject>();
}

int majorFromVersion(const String& version) {
  String normalized = version;
  normalized.trim();
  if (normalized.isEmpty()) {
    return -1;
  }
  const int dotIndex = normalized.indexOf('.');
  if (dotIndex < 0) {
    return normalized.toInt();
  }
  return normalized.substring(0, dotIndex).toInt();
}

String buildAgentId() {
  const uint64_t chip = ESP.getEfuseMac();
  char buffer[13];
  snprintf(buffer, sizeof(buffer), "%012llx", static_cast<unsigned long long>(chip & 0xFFFFFFFFFFFFULL));
  return String("esp32-") + String(buffer);
}

}  // namespace agent
