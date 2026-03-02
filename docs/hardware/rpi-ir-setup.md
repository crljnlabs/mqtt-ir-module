# Raspberry Pi IR (Receiver + Transmitter) - Setup (To-Do)

## Notes
- Hardware wiring is **module-dependent**. Wire modules according to the datasheet/manufacturer.
- GPIO pins below are **only an example** (receiver on pin 11, transmitter on pin 12).

---

## 1) Connect hardware (example)
- IR receiver: signal to **GPIO / Pin 11** (example)
- IR transmitter: data to **GPIO / Pin 12** (example)

---

## 2) Enable device tree overlays
1. Open file:
   - `/boot/firmware/config.txt`
2. Add overlays (example with GPIO17=Pin 11 and GPIO18=Pin 12):
   ```ini
   dtoverlay=gpio-ir,gpio_pin=17
   dtoverlay=gpio-ir-tx,gpio_pin=18
   ```
3. Reboot:
   ```bash
   sudo reboot
   ```

---

## 3) Check whether RX/TX were detected by the system
1. Check whether LIRC devices exist:
   ```bash
   ls -l /dev/lirc*
   ```
2. Check which RC devices exist and which `lirc*` they expose:
   ```bash
   for r in /sys/class/rc/rc*; do
     echo "== $r =="
     cat "$r/uevent" 2>/dev/null || true
     ls -1 "$r" | grep -E '^lirc' || true
   done
   ```

**Interpretation (no extra tools):**
- If `DRV_NAME=gpio-ir-tx` appears in `uevent`, that is the **transmitter (TX)**.
- If `DRV_NAME=gpio_ir_recv` appears in `uevent`, that is the **receiver (RX)**.
- The shown `lircX` is the matching device (e.g. `lirc0`, `lirc1`).

Example:
- `DRV_NAME=gpio-ir-tx` + `lirc0` -> **TX** is `/dev/lirc0`
- `DRV_NAME=gpio_ir_recv` + `lirc1` -> **RX** is `/dev/lirc1`

---

## 4) Docker: set devices and environment variables
### 4.1 Option: pass through paths 1:1 (recommended)
```yaml
services:
  mqtt-ir-module:
    image: <your-image>
    devices:
      - "/dev/lirc0:/dev/lirc0"
      - "/dev/lirc1:/dev/lirc1"
    environment:
      - IR_TX_DEVICE=/dev/lirc0
      - IR_RX_DEVICE=/dev/lirc1
```

### 4.2 If `lirc0/lirc1` are different on your system
- Set `IR_TX_DEVICE` to the `/dev/lircX` listed under `DRV_NAME=gpio-ir-tx`.
- Set `IR_RX_DEVICE` to the `/dev/lircX` listed under `DRV_NAME=gpio_ir_recv`.
- Adjust the `devices:` mappings accordingly.

---

## 5) Application
- Your app uses:
  - `IR_TX_DEVICE` for **sending**
  - `IR_RX_DEVICE` for **receiving**
