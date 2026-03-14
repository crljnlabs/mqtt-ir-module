#pragma once

#include <Arduino.h>

#include <IRrecv.h>

#include <vector>

namespace agent {

bool canSend();
bool canLearn();
void applyLearningReceiverState();
void initIrHardware();

String buildRawTextFromDecode(const decode_results& result);
bool parseRawSignal(const String& input, std::vector<uint16_t>& out);
uint32_t frameDurationUs(const std::vector<uint16_t>& frame);
void delayUsWithYield(uint32_t durationUs);
bool sendFrameRaw(const std::vector<uint16_t>& frame, uint16_t carrierHz);

// Send a protocol-encoded IR signal (NEC, Samsung32, SIRC, RC5, RC6, Kaseikyo, JVC).
// addressStr and commandStr are space-separated hex bytes as stored in the database,
// e.g. "20 00" for a two-byte address or "01 00" for a two-byte command.
// Returns false for unsupported protocols or parse errors.
bool sendFrameProtocol(const String& protocol, const String& addressStr, const String& commandStr);

}  // namespace agent
