#include "agent_commands.h"

#include "agent_ir.h"
#include "agent_logs.h"
#include "agent_ota.h"
#include "agent_pairing.h"
#include "agent_runtime_state.h"
#include "agent_state.h"

#include <cmath>
#include <functional>
#include <vector>

namespace agent {

namespace {

struct PendingOtaRequest {
  bool active = false;
  bool running = false;
  bool cancelRequested = false;
  String requestId;
  String targetVersion;
  String url;
  String expectedSha256;
};

PendingOtaRequest gPendingOtaRequest;

void sendCommandResponse(
    const String& hubId,
    const String& requestId,
    bool ok,
    std::function<void(JsonObject)> fillResult,
    const String& errorCode,
    const String& errorMessage,
    int statusCode) {
  JsonDocument responseDoc;
  responseDoc["request_id"] = requestId;
  responseDoc["ok"] = ok;
  if (ok) {
    JsonObject resultObject = responseDoc["result"].to<JsonObject>();
    fillResult(resultObject);
  } else {
    JsonObject errorObject = responseDoc["error"].to<JsonObject>();
    errorObject["code"] = errorCode;
    errorObject["message"] = errorMessage;
    errorObject["status_code"] = statusCode;
  }
  responseDoc["responded_at"] = nowSecondsText();
  mqttPublishJson(topicResponse(hubId, requestId), responseDoc, false);
}

bool executeSendCommand(
    JsonObjectConst payload,
    JsonObject result,
    String& errorCode,
    String& errorMessage,
    int& statusCode) {
  if (!canSend()) {
    errorCode = "runtime_error";
    errorMessage = "IR sender is not available";
    statusCode = 409;
    return false;
  }

  const String mode = String(payload["mode"] | "");
  const String normalizedMode = mode.length() ? mode : "press";
  const uint16_t carrierHz = static_cast<uint16_t>(payload["carrier_hz"] | 38000);
  const String pressInitial = String(payload["press_initial"] | "");
  if (pressInitial.isEmpty()) {
    errorCode = "validation_error";
    errorMessage = "press_initial is required";
    statusCode = 400;
    return false;
  }

  std::vector<uint16_t> pressFrame;
  if (!parseRawSignal(pressInitial, pressFrame)) {
    errorCode = "validation_error";
    errorMessage = "Invalid press_initial format";
    statusCode = 400;
    return false;
  }

  markActivity();

  if (normalizedMode == "press") {
    if (!sendFrameRaw(pressFrame, carrierHz)) {
      errorCode = "runtime_error";
      errorMessage = "Failed to send press frame";
      statusCode = 409;
      return false;
    }
    result["mode"] = "press";
    result["repeats"] = 0;
    result["gap_us"] = nullptr;
    return true;
  }

  if (normalizedMode != "hold") {
    errorCode = "validation_error";
    errorMessage = "mode must be press or hold";
    statusCode = 400;
    return false;
  }

  const int holdMs = payload["hold_ms"] | 0;
  if (holdMs <= 0) {
    errorCode = "validation_error";
    errorMessage = "hold_ms must be > 0";
    statusCode = 400;
    return false;
  }

  const String holdInitial = String(payload["hold_initial"] | "");
  const String holdRepeat = String(payload["hold_repeat"] | "");
  const int holdGapUs = payload["hold_gap_us"] | 0;
  if (holdInitial.isEmpty() || holdRepeat.isEmpty() || holdGapUs <= 0) {
    errorCode = "validation_error";
    errorMessage = "hold_initial, hold_repeat and hold_gap_us are required";
    statusCode = 400;
    return false;
  }

  std::vector<uint16_t> holdInitialFrame;
  std::vector<uint16_t> holdRepeatFrame;
  if (!parseRawSignal(holdInitial, holdInitialFrame) || !parseRawSignal(holdRepeat, holdRepeatFrame)) {
    errorCode = "validation_error";
    errorMessage = "Invalid hold frame format";
    statusCode = 400;
    return false;
  }

  if (!sendFrameRaw(holdInitialFrame, carrierHz)) {
    errorCode = "runtime_error";
    errorMessage = "Failed to send hold initial frame";
    statusCode = 409;
    return false;
  }

  const uint32_t targetUs = static_cast<uint32_t>(holdMs) * 1000UL;
  const uint32_t initialUs = frameDurationUs(holdInitialFrame);
  const uint32_t repeatUs = frameDurationUs(holdRepeatFrame);
  const uint32_t periodUs = repeatUs + static_cast<uint32_t>(holdGapUs);
  const uint32_t remainingUs = (targetUs > initialUs) ? (targetUs - initialUs) : 0;
  uint32_t repeatCount = 1;
  if (periodUs > 0 && remainingUs > 0) {
    repeatCount = static_cast<uint32_t>(std::ceil(static_cast<float>(remainingUs) / static_cast<float>(periodUs)));
    if (repeatCount == 0) {
      repeatCount = 1;
    }
  }

  for (uint32_t i = 0; i < repeatCount; i++) {
    delayUsWithYield(static_cast<uint32_t>(holdGapUs));
    if (!sendFrameRaw(holdRepeatFrame, carrierHz)) {
      errorCode = "runtime_error";
      errorMessage = "Failed to send hold repeat frame";
      statusCode = 409;
      return false;
    }
  }

  result["mode"] = "hold";
  result["hold_ms"] = holdMs;
  result["gap_us"] = holdGapUs;
  result["repeats"] = repeatCount;
  return true;
}

bool executeLearnCaptureCommand(
    JsonObjectConst payload,
    JsonObject result,
    String& errorCode,
    String& errorMessage,
    int& statusCode) {
  if (!gLearningActive) {
    errorCode = "runtime_error";
    errorMessage = "Learning session is not running";
    statusCode = 409;
    return false;
  }
  if (!canLearn()) {
    errorCode = "runtime_error";
    errorMessage = "IR receiver is not available";
    statusCode = 409;
    return false;
  }
  const int timeoutMs = payload["timeout_ms"] | 0;
  if (timeoutMs <= 0) {
    errorCode = "validation_error";
    errorMessage = "timeout_ms must be > 0";
    statusCode = 400;
    return false;
  }

  markActivity();
  applyLearningReceiverState();

  const unsigned long startMs = millis();
  while (millis() - startMs < static_cast<unsigned long>(timeoutMs)) {
    if (gIrReceiver->decode(&gDecodeResults)) {
      const String raw = buildRawTextFromDecode(gDecodeResults);
      gIrReceiver->resume();
      result["raw"] = raw;
      result["stdout"] = "";
      result["stderr"] = "";
      return true;
    }
    gMqttClient.loop();
    delay(2);
  }

  errorCode = "timeout";
  errorMessage = "Learn capture timed out";
  statusCode = 408;
  return false;
}

bool executeRuntimeConfigSet(
    JsonObjectConst payload,
    JsonObject result,
    String& errorCode,
    String& errorMessage,
    int& statusCode) {
  const JsonVariantConst rxPin = payload["ir_rx_pin"];
  const JsonVariantConst txPin = payload["ir_tx_pin"];
  bool hasRx = !rxPin.isUnbound();
  bool hasTx = !txPin.isUnbound();
  if (!hasRx && !hasTx) {
    errorCode = "validation_error";
    errorMessage = "At least one pin must be provided";
    statusCode = 400;
    return false;
  }

  int nextRx = gRuntimeConfig.irRxPin;
  int nextTx = gRuntimeConfig.irTxPin;
  if (hasRx) {
    if (!rxPin.is<int>()) {
      errorCode = "validation_error";
      errorMessage = "ir_rx_pin must be an integer";
      statusCode = 400;
      return false;
    }
    nextRx = rxPin.as<int>();
    if (!isValidPin(nextRx)) {
      errorCode = "validation_error";
      errorMessage = "ir_rx_pin is out of range";
      statusCode = 400;
      return false;
    }
  }
  if (hasTx) {
    if (!txPin.is<int>()) {
      errorCode = "validation_error";
      errorMessage = "ir_tx_pin must be an integer";
      statusCode = 400;
      return false;
    }
    nextTx = txPin.as<int>();
    if (!isValidPin(nextTx)) {
      errorCode = "validation_error";
      errorMessage = "ir_tx_pin is out of range";
      statusCode = 400;
      return false;
    }
  }

  const bool changed = (nextRx != gRuntimeConfig.irRxPin) || (nextTx != gRuntimeConfig.irTxPin);
  gRuntimeConfig.irRxPin = nextRx;
  gRuntimeConfig.irTxPin = nextTx;
  if (changed) {
    initIrHardware();
  }
  saveRebootRequired(false);
  publishState();

  result["ir_rx_pin"] = gRuntimeConfig.irRxPin;
  result["ir_tx_pin"] = gRuntimeConfig.irTxPin;
  result["reboot_required"] = gRebootRequired;
  return true;
}

void publishInstallationStatus(
    const String& requestId,
    const String& status,
    int progressPct,
    const String& targetVersion,
    const String& message,
    const String& errorCode) {
  JsonDocument statusDoc;
  statusDoc["request_id"] = requestId;
  statusDoc["status"] = status;
  if (progressPct >= 0) {
    statusDoc["progress_pct"] = progressPct;
  }
  statusDoc["target_version"] = targetVersion;
  statusDoc["current_version"] = kFirmwareVersion;
  statusDoc["message"] = message;
  statusDoc["error_code"] = errorCode;
  statusDoc["updated_at"] = nowSecondsText();
  mqttPublishJson(topicInstallationState(), statusDoc, true);
}

void clearPendingOtaRequest() {
  gPendingOtaRequest.active = false;
  gPendingOtaRequest.running = false;
  gPendingOtaRequest.cancelRequested = false;
  gPendingOtaRequest.requestId = "";
  gPendingOtaRequest.targetVersion = "";
  gPendingOtaRequest.url = "";
  gPendingOtaRequest.expectedSha256 = "";
}

bool executeRuntimeOtaStart(
    JsonObjectConst payload,
    JsonObject result,
    String& errorCode,
    String& errorMessage,
    int& statusCode) {
  if (gPendingOtaRequest.active) {
    errorCode = "ota_in_progress";
    errorMessage = "OTA update is already in progress";
    statusCode = 409;
    return false;
  }

  const String url = String(payload["url"] | "");
  const String version = String(payload["version"] | "");
  const String expectedSha = normalizeSha256(String(payload["sha256"] | ""));
  const String requestId = String(payload["request_id"] | "");
  if (requestId.isEmpty()) {
    errorCode = "validation_error";
    errorMessage = "request_id is required";
    statusCode = 400;
    return false;
  }
  if (url.isEmpty() || version.isEmpty()) {
    errorCode = "validation_error";
    errorMessage = "url and version are required";
    statusCode = 400;
    return false;
  }
  if (expectedSha.isEmpty() || !isHexSha256(expectedSha)) {
    errorCode = "validation_error";
    errorMessage = "sha256 must be a 64-char lowercase hex string";
    statusCode = 400;
    return false;
  }

  gPendingOtaRequest.active = true;
  gPendingOtaRequest.running = false;
  gPendingOtaRequest.cancelRequested = false;
  gPendingOtaRequest.requestId = requestId;
  gPendingOtaRequest.targetVersion = version;
  gPendingOtaRequest.url = url;
  gPendingOtaRequest.expectedSha256 = expectedSha;

  publishInstallationStatus(requestId, "started", 0, version, "OTA started", "");
  result["accepted"] = true;
  result["request_id"] = requestId;
  result["target_version"] = version;
  return true;
}

bool executeRuntimeOtaCancel(
    JsonObject result,
    String& errorCode,
    String& errorMessage,
    int& statusCode) {
  if (!gPendingOtaRequest.active) {
    errorCode = "ota_not_in_progress";
    errorMessage = "No OTA update is in progress";
    statusCode = 409;
    return false;
  }

  if (!gPendingOtaRequest.running) {
    const String requestId = gPendingOtaRequest.requestId;
    const String targetVersion = gPendingOtaRequest.targetVersion;
    clearPendingOtaRequest();
    publishInstallationStatus(requestId, "cancelled", -1, targetVersion, "OTA update cancelled", "ota_cancelled");
    result["cancel_requested"] = true;
    result["running"] = false;
    return true;
  }

  gPendingOtaRequest.cancelRequested = true;
  result["cancel_requested"] = true;
  result["running"] = true;
  return true;
}

void processPendingOtaRequest() {
  if (!gPendingOtaRequest.active || gPendingOtaRequest.running) {
    return;
  }

  gPendingOtaRequest.running = true;
  markActivity();
  const bool wasEcoMode = gEcoMode;
  applyPowerMode();  // Switch WiFi to active mode now — modem sleep stalls HTTP+MQTT during blocking OTA download.
  if (wasEcoMode && !gEcoMode) {
    // WiFi PS mode change is asynchronous — the radio needs time to fully wake up.
    // Without this, the HTTP stream starts during the transition and drops partway through.
    for (int i = 0; i < 10; i++) {
      gMqttClient.loop();
      delay(30);  // 300ms total
    }
  }

  const String requestId = gPendingOtaRequest.requestId;
  const String targetVersion = gPendingOtaRequest.targetVersion;
  const String url = gPendingOtaRequest.url;
  const String expectedSha256 = gPendingOtaRequest.expectedSha256;
  OtaResult ota = performOta(
      url,
      expectedSha256,
      [&](const String& phase, int progressPct, const String& phaseMessage) {
        publishInstallationStatus(requestId, phase, progressPct, targetVersion, phaseMessage, "");
      },
      [&]() {
        return gPendingOtaRequest.cancelRequested;
      });

  if (!ota.ok) {
    if (ota.errorCode == "ota_cancelled") {
      publishInstallationStatus(requestId, "cancelled", -1, targetVersion, "OTA update cancelled", "ota_cancelled");
      logWarn("runtime", String("OTA cancelled request_id=") + requestId, "ota_cancelled");
    } else {
      const String code = ota.errorCode.length() ? ota.errorCode : "runtime_error";
      const String message = ota.message.length() ? ota.message : "OTA update failed";
      publishInstallationStatus(requestId, "failure", -1, targetVersion, message, code);
      logWarn(
          "runtime",
          String("OTA failed request_id=") + requestId + " error=" + code + " message=" + message,
          code);
    }
    clearPendingOtaRequest();
    return;
  }

  saveRebootRequired(false);
  publishInstallationStatus(requestId, "finished", 100, targetVersion, "OTA update completed", "");
  logInfo(
      "runtime",
      String("OTA update completed request_id=") + requestId + " target_version=" + targetVersion);
  clearPendingOtaRequest();
  scheduleReboot(kRebootDelayMs);
}

}  // namespace

void handleCommand(const String& command, JsonObjectConst payload) {
  const String requestId = String(payload["request_id"] | "");
  const String hubId = String(payload["hub_id"] | "");
  if (requestId.isEmpty() || hubId.isEmpty()) {
    logWarn("runtime", "Ignoring command without request_id or hub_id", "command_invalid_envelope");
    return;
  }
  if (!isHubAuthorized(hubId)) {
    logWarn(
        "runtime",
        String("Ignoring unauthorized command hub_id=") + hubId + " pairing_hub_id=" + gPairingHubId,
        "hub_unauthorized");
    return;
  }

  String errorCode;
  String errorMessage;
  int statusCode = 500;
  bool commandOk = false;
  bool shouldReboot = false;
  JsonDocument resultDoc;
  JsonObject result = resultDoc.to<JsonObject>();

  if (command == "send") {
    commandOk = executeSendCommand(payload, result, errorCode, errorMessage, statusCode);
  } else if (command == "learn/start") {
    gLearningActive = true;
    markActivity();
    applyLearningReceiverState();
    result["ok"] = true;
    commandOk = true;
  } else if (command == "learn/stop") {
    gLearningActive = false;
    applyLearningReceiverState();
    result["ok"] = true;
    commandOk = true;
  } else if (command == "learn/capture") {
    commandOk = executeLearnCaptureCommand(payload, result, errorCode, errorMessage, statusCode);
  } else if (command == "runtime/debug/get") {
    result["debug"] = gDebugEnabled;
    commandOk = true;
  } else if (command == "runtime/debug/set") {
    if (payload["debug"].isUnbound()) {
      commandOk = false;
      errorCode = "validation_error";
      errorMessage = "debug is required";
      statusCode = 400;
    } else {
      const bool enabled = payload["debug"].as<bool>();
      saveDebugFlag(enabled);
      publishState();
      result["debug"] = gDebugEnabled;
      commandOk = true;
    }
  } else if (command == "runtime/config/get") {
    result["ir_rx_pin"] = gRuntimeConfig.irRxPin;
    result["ir_tx_pin"] = gRuntimeConfig.irTxPin;
    result["reboot_required"] = gRebootRequired;
    commandOk = true;
  } else if (command == "runtime/config/set") {
    commandOk = executeRuntimeConfigSet(payload, result, errorCode, errorMessage, statusCode);
  } else if (command == "runtime/reboot") {
    saveRebootRequired(false);
    publishState();
    result["rebooting"] = true;
    shouldReboot = true;
    commandOk = true;
  } else if (command == "runtime/ota/start") {
    commandOk = executeRuntimeOtaStart(payload, result, errorCode, errorMessage, statusCode);
  } else if (command == "runtime/ota/cancel") {
    commandOk = executeRuntimeOtaCancel(result, errorCode, errorMessage, statusCode);
  } else {
    commandOk = false;
    errorCode = "validation_error";
    errorMessage = "Unknown command";
    statusCode = 400;
  }

  sendCommandResponse(
      hubId,
      requestId,
      commandOk,
      [&](JsonObject responseResult) {
        responseResult.set(result);
      },
      errorCode,
      errorMessage,
      statusCode);

  if (commandOk) {
    logDebug(
        "runtime",
        String("Command handled command=") + command + " request_id=" + requestId + " ok=true");
  } else {
    const String code = errorCode.length() ? errorCode : "runtime_error";
    logWarn(
        "runtime",
        String("Command failed command=") + command + " request_id=" + requestId + " error=" + code,
        code);
  }

  if (commandOk && shouldReboot) {
    scheduleReboot(kRebootDelayMs);
  }
}

void processBackgroundTasks() {
  processPendingOtaRequest();
}

}  // namespace agent
