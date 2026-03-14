#include "agent_ir.h"

#include "agent_logs.h"
#include "agent_state.h"

#include <IRremoteESP8266.h>
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
  logWarn("ir", String("initIrHardware: start has_sender=") + (gIrSender ? "1" : "0") + " has_receiver=" + (gIrReceiver ? "1" : "0"));
  if (gIrSender) {
    logWarn("ir", "initIrHardware: deleting sender");
    delete gIrSender;
    gIrSender = nullptr;
    logWarn("ir", "initIrHardware: sender deleted");
  }
  if (gIrReceiver) {
    logWarn("ir", String("initIrHardware: disabling receiver enabled=") + (gIrReceiverEnabled ? "1" : "0"));
    if (gIrReceiverEnabled) {
      gIrReceiver->disableIRIn();
      gIrReceiverEnabled = false;
      logWarn("ir", "initIrHardware: receiver disabled");
    }
    logWarn("ir", "initIrHardware: deleting receiver");
    delete gIrReceiver;
    gIrReceiver = nullptr;
    logWarn("ir", "initIrHardware: receiver deleted");
  }
  if (isValidPin(gRuntimeConfig.irTxPin)) {
    logWarn("ir", String("initIrHardware: creating sender pin=") + gRuntimeConfig.irTxPin);
    gIrSender = new IRsend(static_cast<uint16_t>(gRuntimeConfig.irTxPin));
    logWarn("ir", "initIrHardware: calling sender begin");
    gIrSender->begin();
    logWarn("ir", "initIrHardware: sender ready");
  }
  if (isValidPin(gRuntimeConfig.irRxPin)) {
    logWarn("ir", String("initIrHardware: creating receiver pin=") + gRuntimeConfig.irRxPin);
    gIrReceiver = new IRrecv(static_cast<uint16_t>(gRuntimeConfig.irRxPin), 1024, 15, true);
    gIrReceiverEnabled = false;
    logWarn("ir", "initIrHardware: receiver created");
  }
  logWarn("ir", "initIrHardware: calling applyLearningReceiverState");
  applyLearningReceiverState();
  logWarn("ir", "initIrHardware: done");
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

// Parse space-separated hex byte tokens (e.g. "20 00") into a byte vector.
// Returns false if any token is malformed or the result is empty.
static bool parseHexBytes(const String& input, std::vector<uint8_t>& out) {
  out.clear();
  String text = input;
  text.trim();
  if (text.isEmpty()) {
    return false;
  }
  int start = 0;
  while (start < static_cast<int>(text.length())) {
    while (start < static_cast<int>(text.length()) && text.charAt(start) == ' ') {
      start++;
    }
    if (start >= static_cast<int>(text.length())) {
      break;
    }
    int end = text.indexOf(' ', start);
    if (end < 0) {
      end = static_cast<int>(text.length());
    }
    const String token = text.substring(start, end);
    char* endPtr = nullptr;
    const long val = strtol(token.c_str(), &endPtr, 16);
    if (endPtr == token.c_str() || *endPtr != '\0') {
      return false;
    }
    out.push_back(static_cast<uint8_t>(val & 0xFF));
    start = end + 1;
  }
  return !out.empty();
}

bool sendFrameProtocol(const String& protocol, const String& addressStr, const String& commandStr) {
  if (!gIrSender) {
    return false;
  }

  std::vector<uint8_t> addr;
  std::vector<uint8_t> cmd;
  if (!parseHexBytes(addressStr, addr) || !parseHexBytes(commandStr, cmd)) {
    return false;
  }
  if (addr.empty() || cmd.empty()) {
    return false;
  }

  // Helper to safely index into byte vectors with a fallback.
  auto b = [](const std::vector<uint8_t>& v, size_t i, uint8_t fallback = 0) -> uint8_t {
    return i < v.size() ? v[i] : fallback;
  };

  if (protocol == "NEC") {
    gIrSender->sendNEC(
        gIrSender->encodeNEC(static_cast<uint16_t>(b(addr, 0)), static_cast<uint16_t>(b(cmd, 0))),
        kNECBits);
    return true;
  }

  if (protocol == "NECext") {
    // 16-bit address: address[0] = high byte, address[1] = low byte (Flipper little-endian byte order).
    const uint16_t addr16 = static_cast<uint16_t>(b(addr, 0)) |
                            (static_cast<uint16_t>(b(addr, 1)) << 8);
    gIrSender->sendNEC(
        gIrSender->encodeNEC(addr16, static_cast<uint16_t>(b(cmd, 0))),
        kNECBits);
    return true;
  }

  if (protocol == "Samsung32") {
    gIrSender->sendSAMSUNG(
        gIrSender->encodeSAMSUNG(b(addr, 0), b(cmd, 0)),
        kSamsungBits);
    return true;
  }

  if (protocol == "SIRC") {
    // Sony 12-bit: 7-bit command, 5-bit address.
    gIrSender->sendSony(
        gIrSender->encodeSony(kSony12Bits, b(cmd, 0), b(addr, 0) & 0x1Fu),
        kSony12Bits,
        kSonyMinRepeat);
    return true;
  }

  if (protocol == "SIRC15") {
    // Sony 15-bit: 7-bit command, 8-bit address.
    gIrSender->sendSony(
        gIrSender->encodeSony(kSony15Bits, b(cmd, 0), b(addr, 0)),
        kSony15Bits,
        kSonyMinRepeat);
    return true;
  }

  if (protocol == "SIRC20") {
    // Sony 20-bit: 7-bit command, 5-bit device address, 8-bit sub-device.
    // Flipper stores device in addr[0] (low 5 bits) and sub-device in addr[1].
    gIrSender->sendSony(
        gIrSender->encodeSony(kSony20Bits, b(cmd, 0), b(addr, 0) & 0x1Fu, b(addr, 1)),
        kSony20Bits,
        kSonyMinRepeat);
    return true;
  }

  if (protocol == "RC5") {
    gIrSender->sendRC5(
        gIrSender->encodeRC5(b(addr, 0) & 0x1Fu, b(cmd, 0) & 0x3Fu),
        kRC5Bits);
    return true;
  }

  if (protocol == "RC6") {
    gIrSender->sendRC6(
        gIrSender->encodeRC6(static_cast<uint32_t>(b(addr, 0)), b(cmd, 0)),
        kRC6Mode0Bits);
    return true;
  }

  if (protocol == "Kaseikyo") {
    // Flipper stores: addr[0..1] = manufacturer code (little-endian),
    // addr[2] = device, addr[3] = sub-device, cmd[0] = function.
    const uint16_t manufacturer = static_cast<uint16_t>(b(addr, 0)) |
                                  (static_cast<uint16_t>(b(addr, 1)) << 8);
    const uint64_t encoded = gIrSender->encodePanasonic(
        manufacturer, b(addr, 2), b(addr, 3), b(cmd, 0));
    // sendPanasonic takes the 16-bit OEM code and the 32-bit data word separately.
    const uint16_t pa_address = static_cast<uint16_t>(encoded >> 32);
    const uint32_t pa_data = static_cast<uint32_t>(encoded & 0xFFFFFFFFULL);
    gIrSender->sendPanasonic(pa_address, pa_data);
    return true;
  }

  if (protocol == "JVC") {
    gIrSender->sendJVC(
        gIrSender->encodeJVC(b(addr, 0), b(cmd, 0)),
        kJvcBits,
        1);
    return true;
  }

  return false;  // Protocol not supported by this firmware version.
}

}  // namespace agent
