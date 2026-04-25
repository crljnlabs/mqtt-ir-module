#include "agent_bootstrap.h"

#include "agent_logs.h"
#include "agent_state.h"

#include <WiFi.h>
#include <WiFiManager.h>

namespace agent {

namespace {

constexpr uint8_t kSetupButtonPin = 0;
constexpr unsigned long kSetupButtonHoldMs = 5000;
unsigned long gSetupButtonPressStartMs = 0;
bool gSetupResetTriggered = false;

bool isSetupButtonPressed() {
  return digitalRead(kSetupButtonPin) == LOW;
}

void clearNetworkProvisioningState() {
  WiFiManager wm;
  wm.resetSettings();

  gRuntimeConfig.mqttHost = "";
  gRuntimeConfig.mqttPort = kDefaultMqttPort;
  gRuntimeConfig.mqttUser = "";
  gRuntimeConfig.mqttPass = "";
  saveRuntimeConfig();

  gMqttClient.disconnect();
  WiFi.disconnect(true, true);
  logWarn("system", "Wi-Fi and MQTT provisioning reset triggered", "provisioning_reset");
}

bool shouldForceConfigPortal() {
  pinMode(kSetupButtonPin, INPUT_PULLUP);
  if (!isSetupButtonPressed()) {
    return false;
  }

  const unsigned long holdStart = millis();
  while (millis() - holdStart < kSetupButtonHoldMs) {
    if (!isSetupButtonPressed()) {
      Serial.println("Setup trigger canceled (BOOT released before 5s).");
      return false;
    }
    delay(20);
  }

  Serial.println("Setup trigger accepted (BOOT held for 5s). Resetting Wi-Fi and MQTT settings.");
  clearNetworkProvisioningState();
  return true;
}

}  // namespace

void configureWifiAndRuntime() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(WIFI_PS_NONE);

  const bool forceConfigPortal = shouldForceConfigPortal();
  String mqttHost = gRuntimeConfig.mqttHost;
  String mqttPort = String(gRuntimeConfig.mqttPort);
  String mqttUser = gRuntimeConfig.mqttUser;
  String mqttPass = gRuntimeConfig.mqttPass;

  WiFiManagerParameter paramMqttHost("mqtt_host", "MQTT Host", mqttHost.c_str(), 64);
  WiFiManagerParameter paramMqttPort("mqtt_port", "MQTT Port", mqttPort.c_str(), 6);
  WiFiManagerParameter paramMqttUser("mqtt_user", "MQTT User", mqttUser.c_str(), 64);
  WiFiManagerParameter paramMqttPass("mqtt_pass", "MQTT Password", mqttPass.c_str(), 64);

  WiFiManager wm;
  wm.setConnectTimeout(20);
  wm.setConfigPortalTimeout(240);
  wm.addParameter(&paramMqttHost);
  wm.addParameter(&paramMqttPort);
  wm.addParameter(&paramMqttUser);
  wm.addParameter(&paramMqttPass);

  const unsigned int idSuffixStart = (gAgentId.length() > 4U) ? (gAgentId.length() - 4U) : 0U;
  const String apSsid = String("ESP32-IR-Setup-") + gAgentId.substring(idSuffixStart);
  const bool wifiOk = forceConfigPortal ? wm.startConfigPortal(apSsid.c_str()) : wm.autoConnect(apSsid.c_str());
  if (!wifiOk) {
    logError("transport", "Wi-Fi setup failed or timed out; restarting", "wifi_setup_failed");
    delay(1000);
    ESP.restart();
    return;
  }

  gRuntimeConfig.mqttHost = String(paramMqttHost.getValue());
  gRuntimeConfig.mqttHost.trim();
  gRuntimeConfig.mqttPort = parseMqttPort(String(paramMqttPort.getValue()), gRuntimeConfig.mqttPort);
  gRuntimeConfig.mqttUser = String(paramMqttUser.getValue());
  gRuntimeConfig.mqttUser.trim();
  gRuntimeConfig.mqttPass = String(paramMqttPass.getValue());
  gRuntimeConfig.mqttPass.trim();
  saveRuntimeConfig();
}

void pollWifiConnection() {
  static unsigned long sLastReconnectAtMs = 0;
  if (WiFi.status() == WL_CONNECTED) {
    sLastReconnectAtMs = 0;
    return;
  }
  const unsigned long now = millis();
  if (sLastReconnectAtMs != 0 && now - sLastReconnectAtMs < kWifiReconnectIntervalMs) {
    return;
  }
  sLastReconnectAtMs = now;
  logWarn("transport", "Wi-Fi disconnected; attempting reconnect", "wifi_reconnect");
  WiFi.reconnect();
}

void pollSetupButton() {
  if (gSetupResetTriggered) {
    return;
  }

  pinMode(kSetupButtonPin, INPUT_PULLUP);
  if (!isSetupButtonPressed()) {
    gSetupButtonPressStartMs = 0;
    return;
  }

  if (gSetupButtonPressStartMs == 0) {
    gSetupButtonPressStartMs = millis();
    return;
  }

  if (millis() - gSetupButtonPressStartMs < kSetupButtonHoldMs) {
    return;
  }

  gSetupResetTriggered = true;
  Serial.println("Setup trigger accepted in runtime (BOOT held for 5s). Resetting Wi-Fi and MQTT settings.");
  clearNetworkProvisioningState();
  logWarn("system", "Restarting after setup-button provisioning reset", "provisioning_reset");
  delay(100);
  ESP.restart();
}

}  // namespace agent
