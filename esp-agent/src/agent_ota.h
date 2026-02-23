#pragma once

#include <Arduino.h>

#include <functional>

namespace agent {

struct OtaResult {
  bool ok = false;
  String errorCode;
  String message;
  String actualSha256;
};

using OtaProgressCallback = std::function<void(const String& status, int progressPct, const String& message)>;

OtaResult performOta(const String& url, const String& expectedSha256, const OtaProgressCallback& onProgress);

}  // namespace agent
