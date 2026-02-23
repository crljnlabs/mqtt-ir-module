#include "agent_logs.h"

#include "agent_runtime_state.h"
#include "agent_state.h"

#include <esp_system.h>

namespace agent {

namespace {

constexpr size_t kQueuedLogCapacity = 16;

struct QueuedLogEvent {
  float ts = 0.0f;
  String level;
  String category;
  String message;
  String errorCode;
};

QueuedLogEvent gQueuedLogs[kQueuedLogCapacity];
size_t gQueuedHead = 0;
size_t gQueuedCount = 0;

String normalizeLevel(const String& value) {
  String level = value;
  level.trim();
  level.toLowerCase();
  if (level == "debug" || level == "info" || level == "warn" || level == "error") {
    return level;
  }
  if (level == "warning") {
    return "warn";
  }
  return "info";
}

String normalizeText(const String& value, size_t maxLength) {
  String text = value;
  text.trim();
  if (text.length() <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength);
}

void enqueueLog(const QueuedLogEvent& event) {
  if (gQueuedCount < kQueuedLogCapacity) {
    const size_t index = (gQueuedHead + gQueuedCount) % kQueuedLogCapacity;
    gQueuedLogs[index] = event;
    gQueuedCount++;
    return;
  }
  gQueuedLogs[gQueuedHead] = event;
  gQueuedHead = (gQueuedHead + 1U) % kQueuedLogCapacity;
}

bool publishLogEvent(const QueuedLogEvent& event) {
  JsonDocument doc;
  doc["ts"] = event.ts;
  doc["level"] = event.level;
  doc["category"] = event.category;
  doc["message"] = event.message;
  if (event.errorCode.length() > 0U) {
    doc["error_code"] = event.errorCode;
  }
  return mqttPublishJson(topicLogs(), doc, false);
}

void emitLogEvent(const String& level, const String& category, const String& message, const String& errorCode) {
  QueuedLogEvent event;
  event.ts = static_cast<float>(millis()) / 1000.0f;
  event.level = normalizeLevel(level);
  event.category = normalizeText(category, 40);
  if (event.category.isEmpty()) {
    event.category = "runtime";
  }
  event.message = normalizeText(message, 180);
  if (event.message.isEmpty()) {
    return;
  }
  event.errorCode = normalizeText(errorCode, 80);

  Serial.printf(
      "[agent][%s][%s] %s\n",
      event.level.c_str(),
      event.category.c_str(),
      event.message.c_str());

  if (!gMqttClient.connected() || !publishLogEvent(event)) {
    enqueueLog(event);
  }
}

String resetReasonText(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON:
      return "poweron";
    case ESP_RST_EXT:
      return "external";
    case ESP_RST_SW:
      return "software";
    case ESP_RST_PANIC:
      return "panic";
    case ESP_RST_INT_WDT:
      return "int_wdt";
    case ESP_RST_TASK_WDT:
      return "task_wdt";
    case ESP_RST_WDT:
      return "wdt";
    case ESP_RST_DEEPSLEEP:
      return "deepsleep";
    case ESP_RST_BROWNOUT:
      return "brownout";
    case ESP_RST_SDIO:
      return "sdio";
#ifdef ESP_RST_USB
    case ESP_RST_USB:
      return "usb";
#endif
#ifdef ESP_RST_JTAG
    case ESP_RST_JTAG:
      return "jtag";
#endif
#ifdef ESP_RST_EFUSE
    case ESP_RST_EFUSE:
      return "efuse";
#endif
#ifdef ESP_RST_PWR_GLITCH
    case ESP_RST_PWR_GLITCH:
      return "power_glitch";
#endif
#ifdef ESP_RST_CPU_LOCKUP
    case ESP_RST_CPU_LOCKUP:
      return "cpu_lockup";
#endif
    case ESP_RST_UNKNOWN:
    default:
      return "unknown";
  }
}

bool resetReasonIndicatesCrash(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_PANIC:
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:
    case ESP_RST_BROWNOUT:
#ifdef ESP_RST_CPU_LOCKUP
    case ESP_RST_CPU_LOCKUP:
#endif
      return true;
    default:
      return false;
  }
}

}  // namespace

void logInfo(const String& category, const String& message, const String& errorCode) {
  emitLogEvent("info", category, message, errorCode);
}

void logWarn(const String& category, const String& message, const String& errorCode) {
  emitLogEvent("warn", category, message, errorCode);
}

void logError(const String& category, const String& message, const String& errorCode) {
  emitLogEvent("error", category, message, errorCode);
}

void logDebug(const String& category, const String& message, const String& errorCode) {
  if (!gDebugEnabled) {
    return;
  }
  emitLogEvent("debug", category, message, errorCode);
}

void flushQueuedLogs() {
  if (!gMqttClient.connected()) {
    return;
  }
  while (gQueuedCount > 0U) {
    const QueuedLogEvent event = gQueuedLogs[gQueuedHead];
    if (!publishLogEvent(event)) {
      return;
    }
    gQueuedHead = (gQueuedHead + 1U) % kQueuedLogCapacity;
    gQueuedCount--;
  }
}

void logBootSummary() {
  const esp_reset_reason_t reason = esp_reset_reason();
  const String reasonText = resetReasonText(reason);
  const bool crashed = resetReasonIndicatesCrash(reason);
  const String message = String("Boot completed reset_reason=") + reasonText + " code=" + String(static_cast<int>(reason))
      + " free_heap=" + String(ESP.getFreeHeap());
  if (crashed) {
    logError("system", message, String("reset_") + reasonText);
    return;
  }
  logInfo("system", message);
}

String currentResetReasonText() {
  return resetReasonText(esp_reset_reason());
}

int currentResetReasonCode() {
  return static_cast<int>(esp_reset_reason());
}

bool currentResetIndicatesCrash() {
  return resetReasonIndicatesCrash(esp_reset_reason());
}

}  // namespace agent
