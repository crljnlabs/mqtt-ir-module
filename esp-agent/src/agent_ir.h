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

}  // namespace agent
