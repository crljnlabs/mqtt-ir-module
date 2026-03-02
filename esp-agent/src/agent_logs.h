#pragma once

#include <Arduino.h>

namespace agent {

void logInfo(const String& category, const String& message, const String& errorCode = "");
void logWarn(const String& category, const String& message, const String& errorCode = "");
void logError(const String& category, const String& message, const String& errorCode = "");
void logDebug(const String& category, const String& message, const String& errorCode = "");

void flushQueuedLogs();
void logBootSummary();
String currentResetReasonText();
int currentResetReasonCode();
bool currentResetIndicatesCrash();

}  // namespace agent
