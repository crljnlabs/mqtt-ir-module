#include "agent_ota.h"

#include "agent_state.h"

#include <HTTPClient.h>
#include <Update.h>
#include <WiFi.h>
#include <mbedtls/sha256.h>

#include <algorithm>

namespace agent {

namespace {

String sha256ToHex(const uint8_t* digest, size_t length) {
  static const char* hex = "0123456789abcdef";
  String output;
  output.reserve(length * 2);
  for (size_t i = 0; i < length; i++) {
    const uint8_t value = digest[i];
    output += hex[(value >> 4) & 0x0F];
    output += hex[value & 0x0F];
  }
  return output;
}

}  // namespace

OtaResult performOta(const String& url, const String& expectedSha256, const OtaProgressCallback& onProgress) {
  OtaResult result;
  result.ok = false;

  HTTPClient http;
  if (!http.begin(url)) {
    result.errorCode = "ota_http_begin_failed";
    result.message = "Failed to open firmware URL";
    return result;
  }

  const int statusCode = http.GET();
  if (statusCode != HTTP_CODE_OK) {
    result.errorCode = "ota_http_status_invalid";
    result.message = String("HTTP status ") + statusCode;
    http.end();
    return result;
  }

  int remaining = http.getSize();
  const int totalBytes = remaining;
  WiFiClient* stream = http.getStreamPtr();
  if (!stream) {
    result.errorCode = "ota_stream_missing";
    result.message = "Firmware stream is not available";
    http.end();
    return result;
  }

  if (!Update.begin((remaining > 0) ? static_cast<size_t>(remaining) : UPDATE_SIZE_UNKNOWN)) {
    result.errorCode = "ota_update_begin_failed";
    result.message = Update.errorString();
    http.end();
    return result;
  }

  mbedtls_sha256_context shaCtx;
  mbedtls_sha256_init(&shaCtx);
  mbedtls_sha256_starts_ret(&shaCtx, 0);

  uint8_t buffer[1024];
  unsigned long lastDataAtMs = millis();
  unsigned long lastProgressAtMs = 0;
  size_t downloadedBytes = 0;

  auto emitProgress = [&](const String& status, int progressPct, const String& message, bool force) {
    if (!onProgress) {
      return;
    }
    int normalizedPct = progressPct;
    if (normalizedPct >= 0) {
      normalizedPct = std::max(0, std::min(100, normalizedPct));
    }
    const unsigned long nowMs = millis();
    if (!force) {
      if ((nowMs - lastProgressAtMs) < 1000UL) {
        return;
      }
    }
    lastProgressAtMs = nowMs;
    onProgress(status, normalizedPct, message);
  };

  emitProgress("downloading", totalBytes > 0 ? 0 : -1, "Downloading firmware", true);

  while (http.connected() && (remaining > 0 || remaining == -1)) {
    const size_t available = stream->available();
    if (available == 0) {
      if (millis() - lastDataAtMs > 15000UL) {
        Update.abort();
        mbedtls_sha256_free(&shaCtx);
        result.errorCode = "ota_stream_timeout";
        result.message = "Firmware stream timed out";
        http.end();
        return result;
      }
      delay(1);
      continue;
    }

    const size_t readSize = std::min(available, sizeof(buffer));
    const int bytesRead = stream->readBytes(buffer, readSize);
    if (bytesRead <= 0) {
      delay(1);
      continue;
    }

    lastDataAtMs = millis();
    const size_t bytesWritten = Update.write(buffer, static_cast<size_t>(bytesRead));
    if (bytesWritten != static_cast<size_t>(bytesRead)) {
      Update.abort();
      mbedtls_sha256_free(&shaCtx);
      result.errorCode = "ota_flash_write_failed";
      result.message = Update.errorString();
      http.end();
      return result;
    }
    mbedtls_sha256_update_ret(&shaCtx, buffer, static_cast<size_t>(bytesRead));
    downloadedBytes += static_cast<size_t>(bytesRead);

    if (totalBytes > 0) {
      const uint64_t numerator = static_cast<uint64_t>(downloadedBytes) * 100ULL;
      const int progressPct = static_cast<int>(numerator / static_cast<uint64_t>(totalBytes));
      emitProgress("downloading", progressPct, "Downloading firmware", false);
    } else {
      emitProgress("downloading", -1, "Downloading firmware", false);
    }

    if (remaining > 0) {
      remaining -= bytesRead;
    }
    yield();
  }

  emitProgress("installing", -1, "Installing firmware", true);

  uint8_t digest[32];
  mbedtls_sha256_finish_ret(&shaCtx, digest);
  mbedtls_sha256_free(&shaCtx);

  result.actualSha256 = sha256ToHex(digest, sizeof(digest));
  const String normalizedExpected = normalizeSha256(expectedSha256);
  if (!normalizedExpected.isEmpty() && result.actualSha256 != normalizedExpected) {
    Update.abort();
    result.errorCode = "ota_checksum_mismatch";
    result.message = "Firmware checksum mismatch";
    http.end();
    return result;
  }

  if (!Update.end()) {
    result.errorCode = "ota_finalize_failed";
    result.message = Update.errorString();
    http.end();
    return result;
  }
  if (!Update.isFinished()) {
    result.errorCode = "ota_not_finished";
    result.message = "Firmware image is incomplete";
    http.end();
    return result;
  }

  result.ok = true;
  result.message = "OTA update completed";
  http.end();
  return result;
}

}  // namespace agent
