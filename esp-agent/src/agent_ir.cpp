#include "agent_ir.h"

#include "agent_state.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace agent {

namespace {
bool gIrReceiverEnabled = false;
}

bool canSend() {
  return gIrSender != nullptr;
}

bool canLearn() {
  return gIrReceiver != nullptr;
}

void applyLearningReceiverState() {
  if (!gIrReceiver) {
    gIrReceiverEnabled = false;
    return;
  }
  if (gLearningActive) {
    if (!gIrReceiverEnabled) {
      gIrReceiver->enableIRIn();
      gIrReceiverEnabled = true;
    }
  } else if (gIrReceiverEnabled) {
    gIrReceiver->disableIRIn();
    gIrReceiverEnabled = false;
  }
}

void initIrHardware() {
  if (gIrSender) {
    delete gIrSender;
    gIrSender = nullptr;
  }
  if (gIrReceiver) {
    delete gIrReceiver;
    gIrReceiver = nullptr;
    gIrReceiverEnabled = false;
  }

  if (isValidPin(gRuntimeConfig.irTxPin)) {
    gIrSender = new IRsend(static_cast<uint16_t>(gRuntimeConfig.irTxPin));
    gIrSender->begin();
  }
  if (isValidPin(gRuntimeConfig.irRxPin)) {
    gIrReceiver = new IRrecv(static_cast<uint16_t>(gRuntimeConfig.irRxPin), 1024, 15, true);
    gIrReceiverEnabled = false;
  }
  applyLearningReceiverState();
}

String buildRawTextFromDecode(const decode_results& result) {
  String raw;
  raw.reserve(result.rawlen * 8);
  for (uint16_t i = 1; i < result.rawlen; i++) {
    const uint32_t usec = result.rawbuf[i] * kRawTick;
    if (i > 1) {
      raw += ' ';
    }
    raw += (i % 2 == 1) ? '+' : '-';
    raw += String(usec);
  }
  return raw;
}

bool parseRawSignal(const String& input, std::vector<uint16_t>& out) {
  out.clear();
  String text = input;
  text.trim();
  if (text.isEmpty()) {
    return false;
  }
  int start = 0;
  while (start < text.length()) {
    while (start < text.length() && text.charAt(start) == ' ') {
      start++;
    }
    if (start >= text.length()) {
      break;
    }
    int end = text.indexOf(' ', start);
    if (end < 0) {
      end = text.length();
    }
    const String token = text.substring(start, end);
    char* endPtr = nullptr;
    const long value = strtol(token.c_str(), &endPtr, 10);
    if (endPtr == token.c_str() || *endPtr != '\0' || value == 0) {
      return false;
    }
    if (out.empty() && value < 0) {
      return false;
    }
    const uint32_t absolute = static_cast<uint32_t>(std::abs(value));
    const uint16_t duration = static_cast<uint16_t>(std::min<uint32_t>(absolute, 65535));
    out.push_back(duration);
    start = end + 1;
  }
  return !out.empty();
}

uint32_t frameDurationUs(const std::vector<uint16_t>& frame) {
  uint32_t total = 0;
  for (const uint16_t value : frame) {
    total += value;
  }
  return total;
}

void delayUsWithYield(uint32_t durationUs) {
  if (durationUs == 0) {
    return;
  }
  uint32_t remaining = durationUs;
  while (remaining > 1000) {
    delayMicroseconds(1000);
    remaining -= 1000;
    yield();
  }
  if (remaining > 0) {
    delayMicroseconds(remaining);
  }
}

bool sendFrameRaw(const std::vector<uint16_t>& frame, uint16_t carrierHz) {
  if (!gIrSender || frame.empty()) {
    return false;
  }
  const uint16_t khz = static_cast<uint16_t>(std::max<uint16_t>(1, carrierHz / 1000));
  gIrSender->sendRaw(frame.data(), static_cast<uint16_t>(frame.size()), khz);
  return true;
}

}  // namespace agent
