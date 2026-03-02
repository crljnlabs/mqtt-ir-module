# Task: Add HTTPS OTA Support for ESP32 Agent

## Goal

Harden OTA transport from HTTP to HTTPS with certificate validation.

## Scope

- Keep existing MQTT OTA command contract (`runtime/ota/start`).
- Extend agent OTA download path to support TLS verification.
- Keep SHA-256 firmware checksum verification enabled.

## Proposed steps

1. Add HTTPS URL support to OTA command validation.
2. Define trust model:
   - pinned server certificate or
   - pinned CA certificate.
3. Load certificate data from firmware build config.
4. Use secure client (`WiFiClientSecure`) with certificate validation.
5. Reject OTA when TLS handshake/validation fails.
6. Keep fallback policy explicit:
   - either block plain HTTP entirely, or
   - allow HTTP only behind explicit flag.
7. Add user-visible status/error mapping in Hub UI for TLS failures.
8. Document certificate rotation workflow.

## Acceptance criteria

- OTA over HTTPS succeeds with valid certificate.
- OTA over HTTPS fails on invalid/untrusted certificate.
- SHA-256 mismatch still fails before finalize.
- Plain HTTP behavior matches selected policy (blocked or explicitly allowed).
