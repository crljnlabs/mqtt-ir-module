# ESP32 Agent Flash, Drivers, Catalog, and OTA Guide

This project supports two firmware workflows for ESP32 clients:

- Initial USB flashing through ESP Web Tools (Hub UI, Settings page)
- OTA updates triggered from the Hub (Agents page)

## 1. Initial USB flash (first install)

Use this when an ESP32 client is blank or has no compatible firmware yet.

### Requirements

- Chrome or Edge on desktop
- Secure browser context: `https://...` or `http://localhost`
- A USB data cable (charging-only cables will not expose a serial port)
- Latest installable firmware available in the Hub catalog

### Where to install from the Hub UI

1. Open `Settings`.
2. Find the card `ESP32 flash`.
3. Check `Latest installable firmware`.
4. Click `Install ESP32 IR Client`.
5. Select the ESP serial port in the browser prompt.
6. Wait until flashing is complete, then allow reboot.

If the install button is not shown, no installable firmware is currently available.

### Browser install URL (HTTPS)

Use the Hub UI over HTTPS in a desktop browser:

- `https://<hub-host>/settings`

ESP Web Tools installation in browser requires a secure context (`https://` or `http://localhost`).

### If HTTPS is not available: direct firmware download

If browser-based install is not available, download firmware directly and flash with a USB tool/workflow.
For first install on a blank device, use the merged `factory` image.

| Version | Factory download | SHA-256 | Flash usage (`ESP32-WROOM-32D`, `esp32dev`) | RAM usage (`ESP32-WROOM-32D`, `esp32dev`) |
| --- | --- | --- | --- | --- |
| `v0.0.6` | [Download](https://github.com/Dev-CorliJoni/mqtt-ir-module/raw/refs/heads/main/backend/firmware_template/files/esp32-ir-client-v0.0.6.factory.bin) | `b0ef9cbb60c9c508af1a2b5210cd3b0d1c6b86c03106350389c2e54b99b9fa41` | `89.5%` (used `1173213` bytes from `1310720` bytes) | `15.1%` (used `49608` bytes from `327680` bytes) |
| `v0.0.5` | [Download](https://github.com/Dev-CorliJoni/mqtt-ir-module/raw/refs/heads/main/backend/firmware_template/files/esp32-ir-client-v0.0.5.factory.bin) | `1730fc39b75fd40e26a1920cc0c20aae318b0703e6b5d73896da5f8b5b6866e4` | `89.5%` (same binary size as v0.0.6) | `15.1%` (estimated) |
| `v0.0.4` | [Download](https://github.com/Dev-CorliJoni/mqtt-ir-module/raw/refs/heads/main/backend/firmware_template/files/esp32-ir-client-v0.0.4.factory.bin) | `511eb511c9023f1b84e9e50e9484df4bb0a573701d24b15e96b3c24e1ad2291c` | `89.4%` (used `1171693` bytes from `1310720` bytes) | `15.1%` (used `49608` bytes from `327680` bytes) |
| `v0.0.3` | [Download](https://github.com/Dev-CorliJoni/mqtt-ir-module/raw/refs/heads/main/backend/firmware_template/files/esp32-ir-client-v0.0.3.factory.bin) | `c6ead195e4219f0f6b7653c09929042673f0dd61dc3616c5e2b5fbe84f4958ba` | `~89.2%` (estimated from binary size) | — |
| `v0.0.2` | [Download](https://github.com/Dev-CorliJoni/mqtt-ir-module/raw/refs/heads/main/backend/firmware_template/files/esp32-ir-client-v0.0.2.factory.bin) | `ed84c15bcf166263cefa1e3c3fef6ddaf9db5ed0d61b59e73f8a901cadb5c79f` | `88.4%` (used `1158525` bytes from `1310720` bytes) | `14.8%` (used `48440` bytes from `327680` bytes) |
| `v0.0.1` | [Download](https://github.com/Dev-CorliJoni/mqtt-ir-module/raw/refs/heads/main/backend/firmware_template/files/esp32-ir-client-v0.0.1.factory.bin) | `1d55ed7db0ba9e269be3d572fdd9cd2773341e8cb8f9577f9487cf3486ad129b` | `88.3%` (used `1157841` bytes from `1310720` bytes) | `14.8%` (used `48432` bytes from `327680` bytes) |

## 2. USB driver selection and installation

### Important: ESP-WROOM-32D alone does not define the USB driver

`ESP-WROOM-32D` is the radio/MCU module. USB connectivity depends on the separate USB-to-UART chip on your board.

### Driver links

- CP2102 / CP210x:
  - https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers
- CH342 / CH343 / CH9102:
  - macOS: https://www.wch.cn/downloads/CH34XSER_MAC_ZIP.html
  - Windows: https://www.wch.cn/downloads/CH343SER_ZIP.html
- CH340 / CH341:
  - Windows: https://www.wch.cn/downloads/CH341SER_ZIP.html
  - macOS: https://www.wch.cn/downloads/CH341SER_MAC_ZIP.html

### How to know which driver you need

1. Check your board documentation/schematic (best source).
2. Read the USB bridge chip marking near the USB connector (`CP2102`, `CH340`, `CH343`, and so on).
3. Plug in the board and inspect detected serial names:
   - CP210x often appears as `SLAB_USBtoUART` / `cu.SLAB_USBtoUART`
   - CH34x often appears as `wchusbserial...` / `cu.wchusbserial...` / `usbserial...`

### Installation steps (Windows/macOS)

1. Download the matching driver package from the links above.
2. Run the installer package for your OS.
3. Unplug and reconnect the ESP board (reboot OS if driver installer requests it).
4. Verify a new serial port appears:
   - macOS: `ls /dev/cu.*`
   - Windows: Device Manager -> `Ports (COM & LPT)`

If the browser only shows Bluetooth or debug console ports, the ESP USB serial interface is still not detected (usually cable or driver issue).

## 3. What `Logs & Console` does

`Logs & Console` opens a serial console to the selected device. It is useful even before installation for:

- Checking whether the board is detected correctly
- Reading boot output/reset reasons
- Confirming serial communication works

It does not flash firmware and does not change device state by itself.

### Agent logs in Hub UI (MQTT stream)

For runtime debugging after pairing, use `Agents -> <agent> -> Logs`.

ESP32 agents publish runtime events to MQTT topic:

- `ir/agents/<agent_id>/logs`

Typical events include:

- Boot/reset summary (`reset_reason`, heap snapshot)
- MQTT connect failures/reconnect attempts
- Pairing/authorization issues (for example commands ignored due to wrong `pairing_hub_id`)
- Provisioning reset/reboot triggers

Important:

- Hard crashes can still interrupt log publishing at crash time.
- After reboot, the next boot log includes reset reason so post-mortem debugging is still possible.
- Runtime state (`/api/agents/<agent_id>`) also includes retained crash hints:
  - `runtime.last_reset_reason`
  - `runtime.last_reset_code`
  - `runtime.last_reset_crash`
  - `runtime.free_heap`

If you need full panic backtrace details (function/line level), use serial console output from `Logs & Console` during the crash/reboot cycle.

## 4. OTA update flow (after first USB flash)

After the first USB install, firmware updates can be done without USB:

1. Ensure the ESP32 client is online and paired in `Agents`.
2. Open the ESP32 client detail/update action.
3. Choose target version (latest installable is preselected).
4. Confirm update.
5. Agent downloads OTA file, verifies SHA-256, installs, and reboots.

Notes:

- Version format is strict `x.y.z`.
- Downgrades are allowed from UI.
- OTA is supported for ESP32 agents only.

## 5. Default IR pins

The firmware uses these GPIO pins by default:

| Signal | Default GPIO |
| --- | --- |
| IR transmitter (TX) | GPIO 4 |
| IR receiver (RX) | GPIO 34 |

Pin configuration can be changed after pairing via the Hub UI (Agent detail → configuration). No reflash needed.

## 6. Build and publish firmware to the Hub catalog

Use this section when preparing a new firmware version for installation/OTA.

### Option A (recommended): helper script

From repository root:

```bash
cd esp-agent
./build_and_publish.sh
```

The script can:

- Build `esp32dev` firmware
- Copy OTA image (`.bin`) to `backend/firmware_template/files/`
- Generate merged factory image (`.factory.bin`) for ESP Web Tools initial flash
- Upsert `backend/firmware_template/catalog.json` with OTA/factory checksum fields

### Option B: manual process

Build:

```bash
cd esp-agent
pio run -e esp32dev
```

Built binary location:

`esp-agent/.pio/build/esp32dev/firmware.bin`

## 7. Resource usage reference

See [FIRMWARE_CHANGELOG.md](FIRMWARE_CHANGELOG.md) for flash and RAM baselines per version.

Quick check for current build (requires xtensa toolchain):

```bash
~/.platformio/packages/toolchain-xtensa-esp32/bin/xtensa-esp32-elf-size -A \
  esp-agent/.pio/build/esp32dev/firmware.elf
```

RAM = `.dram0.data` + `.dram0.bss`
Flash = `.iram0.vectors` + `.iram0.text` + `.dram0.data` + `.flash.appdesc` + `.flash.rodata` + `.flash.text`

Default runtime firmware layout in Hub container:

- Files directory: `/data/firmware/files/`
- Catalog file: `/data/firmware/catalog.json`

Container startup seeds firmware layout from `/opt/app/firmware_template`.
`catalog.json` in runtime is overwritten from template on startup.

Compute SHA-256:

```bash
sha256sum /data/firmware/files/esp32-ir-client-v0.0.6.bin
```

or

```bash
shasum -a 256 /data/firmware/files/esp32-ir-client-v0.0.6.bin
```

Example catalog entry:

```json
{
  "agent_type": "esp32",
  "version": "0.0.6",
  "installable": true,
  "ota_file": "esp32-ir-client-v0.0.6.bin",
  "ota_sha256": "e00fc4d790de3437b168a3b7f4038adc95dfe11835df26e1d47b0e5e25f31677",
  "factory_file": "esp32-ir-client-v0.0.6.factory.bin",
  "factory_sha256": "b0ef9cbb60c9c508af1a2b5210cd3b0d1c6b86c03106350389c2e54b99b9fa41",
  "notes": "generated by esp-agent/build_and_publish.sh"
}
```

## 8. Verify firmware catalog and Web Tools manifest

Catalog API:

```bash
curl http://<hub-host>/api/firmware?agent_type=esp32
```

ESP Web Tools manifest:

```bash
curl http://<hub-host>/api/firmware/webtools-manifest?agent_type=esp32
```
