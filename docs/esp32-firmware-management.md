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
| `v0.0.1` | `http://<hub-host>/firmware/esp32-ir-client-v0.0.1.factory.bin` | `d9e11f0d1f4433e9072e96a3738704479ae36f62ac7f7a005de4315debfc3600` | `88.3%` (used `1157841` bytes from `1310720` bytes) | `14.8%` (used `48432` bytes from `327680` bytes) |

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

## 5. Build and publish firmware to the Hub catalog

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

### v1 resource usage reference (`0.0.1`)

Build output baseline for firmware `0.0.1` on `ESP32-WROOM-32D` (`esp32dev`):

- RAM: `14.8%` (used `48432` bytes from `327680` bytes)
- Flash: `88.3%` (used `1157841` bytes from `1310720` bytes)

Use this as a quick regression reference when updating dependencies or adding features.

Default runtime firmware layout in Hub container:

- Files directory: `/data/firmware/files/`
- Catalog file: `/data/firmware/catalog.json`

Container startup seeds firmware layout from `/opt/app/firmware_template`.
`catalog.json` in runtime is overwritten from template on startup.

Compute SHA-256:

```bash
sha256sum /data/firmware/files/esp32-ir-client-v0.1.0.bin
```

or

```bash
shasum -a 256 /data/firmware/files/esp32-ir-client-v0.1.0.bin
```

Example catalog entry:

```json
{
  "agent_type": "esp32",
  "version": "0.1.0",
  "installable": true,
  "ota_file": "esp32-ir-client-v0.1.0.bin",
  "ota_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "factory_file": "esp32-ir-client-v0.1.0.factory.bin",
  "factory_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "notes": "stable"
}
```

## 6. Verify firmware catalog and Web Tools manifest

Catalog API:

```bash
curl http://<hub-host>/api/firmware?agent_type=esp32
```

ESP Web Tools manifest:

```bash
curl http://<hub-host>/api/firmware/webtools-manifest?agent_type=esp32
```
