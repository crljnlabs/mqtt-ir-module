#pragma once

#include <Arduino.h>

#include <ArduinoJson.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>

namespace agent {

#ifndef AGENT_FIRMWARE_VERSION
#define AGENT_FIRMWARE_VERSION "0.0.1"
#endif

constexpr const char* kFirmwareVersion = AGENT_FIRMWARE_VERSION;
// Protocol version integers — increment the relevant constant for any breaking change.
constexpr int kSystemVersion = 1;
constexpr int kSendVersion = 1;
constexpr int kLearnVersion = 1;
constexpr const char* kPrefsNamespace = "esp32-ir";
constexpr const char* kAgentType = "esp32";
constexpr uint16_t kDefaultMqttPort = 1883;
constexpr uint8_t kDefaultIrTxPin = 4;
constexpr uint8_t kDefaultIrRxPin = 34;
constexpr size_t kMqttBufferSize = 32768;
constexpr unsigned long kMqttReconnectMinMs = 1000;
constexpr unsigned long kMqttReconnectMaxMs = 60000;
constexpr unsigned long kWifiReconnectIntervalMs = 30000;
constexpr unsigned long kActiveWindowMs = 5UL * 60UL * 1000UL;
constexpr unsigned long kStateHeartbeatMs = 30000;
constexpr unsigned long kRebootDelayMs = 350;

struct RuntimeConfig {
  String mqttHost;
  uint16_t mqttPort = kDefaultMqttPort;
  String mqttUser;
  String mqttPass;
  int irTxPin = kDefaultIrTxPin;
  int irRxPin = kDefaultIrRxPin;
};

extern Preferences gPrefs;
extern WiFiClient gNetClient;
extern PubSubClient gMqttClient;

extern RuntimeConfig gRuntimeConfig;
extern String gAgentId;
extern String gPairingHubId;
extern bool gDebugEnabled;
extern bool gRebootRequired;
extern bool gLearningActive;
extern bool gEcoMode;
extern unsigned long gActiveUntilMs;
extern unsigned long gLastStatePublishMs;
extern unsigned long gNextReconnectAtMs;
extern unsigned long gReconnectDelayMs;
extern bool gPendingReboot;
extern unsigned long gRebootAtMs;
extern String gPairingSessionId;
extern String gPairingNonce;

extern IRsend* gIrSender;
extern IRrecv* gIrReceiver;
extern decode_results gDecodeResults;

bool isValidPin(int pin);
String normalizeSha256(const String& value);
bool isHexSha256(const String& value);
String nowSecondsText();

// State subtopics (all retained except diagnostics)
String topicStateAvailability();  // LWT: "online" / "offline"
String topicStateHub();           // {"id": "..."}
String topicStateVersion();       // {"sw_version": "...", "system": 1, "send": 1, "learn": 1}
String topicStateAgent();         // {"agent_type": "...", "can_send": true, ...}
String topicStateRuntime();       // {"debug": false, "reboot_required": false, "ir_rx_pin": ..., "ir_tx_pin": ...}
String topicStateDiagnostics();   // {"free_heap": ..., "last_reset_reason": ...} — not retained
String topicCommands();
String topicInstallationState();
String topicLogs();
String topicPairingAccept();
String topicPairingUnpair();
String topicPairingUnpairAck();
String topicPairingReclaim();
String topicResponse(const String& hubId, const String& requestId);

void saveRuntimeConfig();
void savePairingHubId(const String& hubId);
void saveDebugFlag(bool enabled);
void saveRebootRequired(bool required);
void loadPersistedState();
bool applyRuntimeStateSnapshot(JsonObjectConst payload);

uint16_t parseMqttPort(const String& value, uint16_t fallback);
int parsePin(const String& value, int fallback);

void markActivity();
void scheduleReboot(unsigned long delayMs);

bool parseCommandTopic(const String& topic, String& commandOut);
bool parseAcceptTopic(const String& topic, String& sessionOut);
bool parsePayloadObject(const byte* payload, unsigned int length, JsonDocument& doc);
int majorFromVersion(const String& version);
String buildAgentId();

}  // namespace agent
