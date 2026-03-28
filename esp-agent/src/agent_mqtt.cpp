#include "agent_mqtt.h"

#include "agent_commands.h"
#include "agent_ir.h"
#include "agent_logs.h"
#include "agent_pairing.h"
#include "agent_runtime_state.h"
#include "agent_state.h"

#include <algorithm>
#include <mbedtls/base64.h>

namespace agent {

namespace {

// Track retained state receipt separately for hub binding and runtime fields.
bool gRetainedHubStateReceived = false;
bool gRetainedRuntimeStateReceived = false;
constexpr unsigned long kRetainedStateTimeoutMs = 1200;

struct PendingTransfer {
  bool active = false;
  String transferId;
  String command;
  uint8_t chunkCount = 0;
  uint8_t receivedCount = 0;
  std::vector<String> chunks;
};

PendingTransfer gPendingTransfer;

// Accumulates a chunk and, when all chunks are received, reassembles and dispatches the command.
void handleCommandChunk(const String& command, JsonObjectConst payload) {
  const String transferId = String(payload["transfer_id"] | "");
  const int rawIndex = payload["chunk_index"] | -1;
  const int rawCount = payload["chunk_count"] | 0;
  const String chunkData = String(payload["chunk_data"] | "");

  if (transferId.isEmpty() || rawIndex < 0 || rawCount <= 0 || rawCount > 255 || chunkData.isEmpty()) {
    return;
  }
  const uint8_t chunkCount = static_cast<uint8_t>(rawCount);
  const uint8_t chunkIndex = static_cast<uint8_t>(rawIndex);

  // Start a new transfer or discard a stale one if the transfer_id changed.
  if (!gPendingTransfer.active || gPendingTransfer.transferId != transferId) {
    gPendingTransfer.active = true;
    gPendingTransfer.transferId = transferId;
    gPendingTransfer.command = command;
    gPendingTransfer.chunkCount = chunkCount;
    gPendingTransfer.receivedCount = 0;
    gPendingTransfer.chunks.assign(chunkCount, "");
  }

  if (chunkIndex < gPendingTransfer.chunkCount && gPendingTransfer.chunks[chunkIndex].isEmpty()) {
    gPendingTransfer.chunks[chunkIndex] = chunkData;
    gPendingTransfer.receivedCount++;
  }

  if (gPendingTransfer.receivedCount < gPendingTransfer.chunkCount) {
    return;  // Still waiting for remaining chunks.
  }

  // All chunks received — reassemble.
  String fullB64;
  for (const String& c : gPendingTransfer.chunks) {
    fullB64 += c;
  }
  const String savedCommand = gPendingTransfer.command;
  gPendingTransfer.active = false;
  gPendingTransfer.chunks.clear();
  gPendingTransfer.receivedCount = 0;

  const size_t b64Len = fullB64.length();
  const size_t maxDecoded = (b64Len / 4) * 3 + 4;
  std::vector<unsigned char> decoded(maxDecoded);
  size_t decodedLen = 0;
  if (mbedtls_base64_decode(decoded.data(), maxDecoded, &decodedLen,
                              reinterpret_cast<const unsigned char*>(fullB64.c_str()),
                              b64Len) != 0) {
    return;
  }

  JsonDocument assembledDoc;
  const DeserializationError err =
      deserializeJson(assembledDoc, decoded.data(), decodedLen);
  if (err != DeserializationError::Ok) {
    return;
  }

  handleCommand(savedCommand, assembledDoc.as<JsonObjectConst>());
}

void waitForRetainedStateSnapshot() {
  // Wait until both retained subtopics are received or the timeout expires.
  const unsigned long deadline = millis() + kRetainedStateTimeoutMs;
  while ((!gRetainedHubStateReceived || !gRetainedRuntimeStateReceived) && millis() < deadline) {
    gMqttClient.loop();
    delay(2);
  }
}

}  // namespace

void onMqttMessage(char* topicChars, byte* payload, unsigned int length) {
  const String topic(topicChars ? topicChars : "");

  // Restore hub binding from retained state/hub on connect.
  if (topic == topicStateHub()) {
    gRetainedHubStateReceived = true;
    JsonDocument doc;
    if (!parsePayloadObject(payload, length, doc)) {
      return;
    }
    const String hubId = String(doc["id"] | "");
    gPairingHubId = hubId;
    gPairingHubId.trim();
    return;
  }

  // Restore operational state from retained state/runtime on connect.
  if (topic == topicStateRuntime()) {
    gRetainedRuntimeStateReceived = true;
    JsonDocument doc;
    if (!parsePayloadObject(payload, length, doc)) {
      return;
    }
    if (applyRuntimeStateSnapshot(doc.as<JsonObjectConst>())) {
      // Pins differ from NVS defaults (e.g. first boot after factory flash).
      // Persist and reboot — RMT teardown at runtime causes a hardware panic.
      saveRuntimeConfig();
      scheduleReboot(kRebootDelayMs);
    }
    return;
  }
  if (topic == "ir/pairing/open") {
    handlePairingOpen(payload, length);
    return;
  }
  if (topic.startsWith("ir/pairing/accept/")) {
    handlePairingAccept(topic, payload, length);
    return;
  }
  if (topic.startsWith("ir/pairing/unpair/")) {
    handlePairingUnpair(topic, payload, length);
    return;
  }
  if (topic.startsWith("ir/pairing/reclaim/")) {
    handlePairingReclaim(topic, payload, length);
    return;
  }

  String command;
  if (!parseCommandTopic(topic, command)) {
    return;
  }

  JsonDocument doc;
  if (!parsePayloadObject(payload, length, doc)) {
    return;
  }

  // If the payload carries chunk metadata, accumulate and reassemble before dispatching.
  if (!doc["chunk_count"].isNull()) {
    handleCommandChunk(command, doc.as<JsonObjectConst>());
    return;
  }

  handleCommand(command, doc.as<JsonObjectConst>());
}

bool connectMqtt() {
  static bool warnedMissingHost = false;
  if (gRuntimeConfig.mqttHost.isEmpty()) {
    if (!warnedMissingHost) {
      logWarn("transport", "MQTT host is empty; skipping connection attempts", "mqtt_host_missing");
      warnedMissingHost = true;
    }
    return false;
  }
  warnedMissingHost = false;

  gMqttClient.setServer(gRuntimeConfig.mqttHost.c_str(), gRuntimeConfig.mqttPort);
  gMqttClient.setBufferSize(kMqttBufferSize);
  gMqttClient.setKeepAlive(60);
  gMqttClient.setCallback(onMqttMessage);

  bool connected = false;
  if (gRuntimeConfig.mqttUser.length() > 0) {
    connected = gMqttClient.connect(
        gAgentId.c_str(),
        gRuntimeConfig.mqttUser.c_str(),
        gRuntimeConfig.mqttPass.c_str(),
        topicStateAvailability().c_str(),
        1,
        true,
        "offline");
  } else {
    connected = gMqttClient.connect(gAgentId.c_str(), topicStateAvailability().c_str(), 1, true, "offline");
  }

  if (!connected) {
    logWarn(
        "transport",
        String("MQTT connect failed state=") + String(gMqttClient.state()) + " host=" + gRuntimeConfig.mqttHost
            + ":" + String(gRuntimeConfig.mqttPort),
        "mqtt_connect_failed");
    return false;
  }

  gMqttClient.publish(topicStateAvailability().c_str(), "online", true);
  gRetainedHubStateReceived = false;
  gRetainedRuntimeStateReceived = false;
  gMqttClient.subscribe(topicStateHub().c_str());
  gMqttClient.subscribe(topicStateRuntime().c_str());
  waitForRetainedStateSnapshot();
  gMqttClient.subscribe("ir/pairing/open");
  gMqttClient.subscribe(topicPairingAccept().c_str());
  gMqttClient.subscribe(topicPairingUnpair().c_str());
  gMqttClient.subscribe(topicPairingReclaim().c_str());
  gMqttClient.subscribe(topicCommands().c_str());
  publishState();
  flushQueuedLogs();
  logInfo(
      "transport",
      String("MQTT connected host=") + gRuntimeConfig.mqttHost + ":" + String(gRuntimeConfig.mqttPort));
  markActivity();
  applyPowerMode();
  return true;
}

}  // namespace agent
