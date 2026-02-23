#include "agent_pairing.h"

#include "agent_ir.h"
#include "agent_logs.h"
#include "agent_runtime_state.h"
#include "agent_state.h"

namespace agent {

namespace {

void publishPairingOffer(const String& sessionId, const String& nonce) {
  JsonDocument doc;
  doc["session_id"] = sessionId;
  doc["nonce"] = nonce;
  doc["agent_uid"] = gAgentId;
  const unsigned int idSuffixStart = (gAgentId.length() > 6U) ? (gAgentId.length() - 6U) : 0U;
  doc["readable_name"] = String("ESP32 IR Agent ") + gAgentId.substring(idSuffixStart);
  doc["base_topic"] = String("ir/agents/") + gAgentId;
  doc["sw_version"] = kFirmwareVersion;
  doc["can_send"] = canSend();
  doc["can_learn"] = canLearn();
  doc["agent_type"] = kAgentType;
  doc["protocol_version"] = kProtocolVersion;
  doc["ota_supported"] = true;
  doc["offered_at"] = nowSecondsText();

  const String topic = String("ir/pairing/offer/") + sessionId + "/" + gAgentId;
  mqttPublishJson(topic, doc, false);
}

}  // namespace

bool isHubAuthorized(const String& hubId) {
  if (gPairingHubId.isEmpty()) {
    return false;
  }
  return hubId == gPairingHubId;
}

void handlePairingOpen(const byte* payload, unsigned int length) {
  if (!gPairingHubId.isEmpty()) {
    logDebug("pairing", "Pairing open ignored because agent is already paired");
    return;
  }
  JsonDocument doc;
  if (!parsePayloadObject(payload, length, doc)) {
    return;
  }

  const String sessionId = String(doc["session_id"] | "");
  const String nonce = String(doc["nonce"] | "");
  if (sessionId.isEmpty() || nonce.isEmpty()) {
    logWarn("pairing", "Pairing open payload missing session_id or nonce", "pairing_payload_invalid");
    return;
  }
  const String hubVersion = String(doc["sw_version"] | "");
  const int hubMajor = majorFromVersion(hubVersion);
  const int agentMajor = majorFromVersion(String(kFirmwareVersion));
  if (hubMajor >= 0 && agentMajor >= 0 && hubMajor != agentMajor) {
    logWarn(
        "pairing",
        String("Pairing open ignored due to major version mismatch hub=") + hubVersion
            + " agent=" + String(kFirmwareVersion),
        "pairing_version_mismatch");
    return;
  }

  gPairingSessionId = sessionId;
  gPairingNonce = nonce;
  publishPairingOffer(sessionId, nonce);
  logInfo("pairing", String("Pairing offer published session_id=") + sessionId);
}

void handlePairingAccept(const String& topic, const byte* payload, unsigned int length) {
  if (!gPairingHubId.isEmpty()) {
    logDebug("pairing", "Pairing accept ignored because agent is already paired");
    return;
  }
  String sessionFromTopic;
  if (!parseAcceptTopic(topic, sessionFromTopic)) {
    return;
  }
  JsonDocument doc;
  if (!parsePayloadObject(payload, length, doc)) {
    return;
  }
  const String payloadSession = String(doc["session_id"] | "");
  const String payloadNonce = String(doc["nonce"] | "");
  const String hubId = String(doc["hub_id"] | "");
  if (payloadSession.isEmpty() || payloadNonce.isEmpty() || hubId.isEmpty()) {
    logWarn("pairing", "Pairing accept payload is invalid", "pairing_payload_invalid");
    return;
  }
  if (payloadSession != sessionFromTopic) {
    logWarn("pairing", "Pairing accept ignored due to session mismatch", "pairing_session_mismatch");
    return;
  }
  if (gPairingSessionId != payloadSession || gPairingNonce != payloadNonce) {
    logWarn("pairing", "Pairing accept ignored due to nonce/session mismatch", "pairing_nonce_mismatch");
    return;
  }

  savePairingHubId(hubId);
  gPairingSessionId = "";
  gPairingNonce = "";
  publishState();
  logInfo("pairing", String("Pairing accepted hub_id=") + hubId);
}

void handlePairingUnpair(const String& topic, const byte* payload, unsigned int length) {
  const String expected = topicPairingUnpair();
  if (topic != expected) {
    return;
  }
  JsonDocument doc;
  if (!parsePayloadObject(payload, length, doc)) {
    return;
  }
  const String commandId = String(doc["command_id"] | "");
  if (commandId.isEmpty()) {
    logWarn("pairing", "Unpair command missing command_id", "pairing_payload_invalid");
    return;
  }

  savePairingHubId("");
  gPairingSessionId = "";
  gPairingNonce = "";
  publishState();

  JsonDocument ack;
  ack["agent_uid"] = gAgentId;
  ack["command_id"] = commandId;
  ack["acked_at"] = nowSecondsText();
  mqttPublishJson(topicPairingUnpairAck(), ack, false);

  // Clear retained unpair command to avoid stale replays.
  gMqttClient.publish(topicPairingUnpair().c_str(), "", true);
  logWarn("pairing", "Agent unpaired by hub command", "agent_unpaired");
}

}  // namespace agent
