# Raspberry Pi 5 IR (Receive + Send) - Quick setup

## Goal
- **Receive:** Read IR codes from a remote as pulse timing over a GPIO and decode/store as button events.
- **Send:** Re-emit stored codes as 38 kHz modulated bursts via an IR LED.

---

## Parts

### Receive (Receiver)
- **IR receiver:** TSOP38238 (38 kHz)
  Converts IR light into a **digital signal** (high/low pulses over time).
- **Capacitor:** 100 nF ceramic (0.1 uF)
  Place directly at the TSOP between VCC and GND to stabilize the supply.

### Send (Transmitter)
- **IR LED:** TSAL6200 (940 nm)
- **NPN transistor:** BC337-40
  Switches the LED current from 5 V; a GPIO cannot supply the LED current directly.
- **Base resistor:** 330 ohm (on hand)
  Limits current from the GPIO into the transistor base.
- **Series resistor (IR LED):** 33 ohm (start value)
  For testing: 47 ohm (less current), 22 ohm (more current).

---

## Wiring

### Receive (TSOP -> Raspberry Pi)
- TSOP **VCC** -> Pi **3V3** (power pin)
- TSOP **GND** -> Pi **GND**
- TSOP **OUT** -> Pi **GPIO_IN** (any GPIO input)
- **100 nF**: TSOP VCC <-> TSOP GND (as close to the TSOP as possible)

```mermaid
flowchart LR
  subgraph Raspberry_Pi_5
    P3V3[3V3 (Power)]
    PGND[GND]
    GPIOIN[GPIO_IN]
  end

  subgraph TSOP38238
    TVCC[VCC]
    TGND[GND]
    TOUT[OUT]
  end

  C100nF[100 nF ceramic]

  P3V3 --- TVCC
  PGND --- TGND
  GPIOIN --- TOUT
  TVCC --- C100nF --- TGND
```

### Send (Raspberry Pi -> Transistor -> IR LED)
- Pi **5V** -> **Rled (33 ohm)** -> **IR LED anode (+)**
- **IR LED cathode (-)** -> **Collector** (BC337)
- **Emitter** (BC337) -> Pi **GND**
- Pi **GPIO_OUT** (ideally GPIO18) -> **Rbase (330 ohm)** -> **Base** (BC337)
- **Ground must be shared** (Pi GND <-> board GND).

```mermaid
flowchart LR
  subgraph Raspberry_Pi_5
    P5V[5V (Power)]
    PGND2[GND]
    GPIOOUT[GPIO_OUT (e.g. GPIO18)]
  end

  Rbase[330 ohm]
  Rled[33 ohm (start)]
  Q1[BC337-40\nNPN]
  LED[TSAL6200\nIR LED]

  P5V --- Rled --- LED
  LED --- Q1
  Q1 --- PGND2
  GPIOOUT --- Rbase --- Q1
```

---

## Operation and tuning (if it does not work)

### Basic idea
- The sender uses a **38 kHz carrier frequency** (very fast on/off of the IR LED).
- The code is a pattern of **bursts** (carrier on) and **pauses** (carrier off).

### Target current and series resistor
- For good range, **~100 mA pulse current** is a typical target.
- Start with **33 ohm**.

**If range is too short:** 33 ohm -> **22 ohm**.  
**If you want to be conservative or something gets warm:** 33 ohm -> **47 ohm**.

### Measuring (multimeter)
1) Measure voltage **across Rled** (directly on the resistor leads).
2) Compute current: **I = U / R**.

Example: U = 3.0 V across 33 ohm -> I ~= 3.0 / 33 ~= 0.091 A (91 mA).

### VF (forward voltage) quick note
- **VF** is the voltage drop across the LED when it is on.
- For the TSAL6200, VF is roughly **~1.6 V** at ~100 mA. The rest of the 5 V drops across the resistor and transistor.

### Resistors you actually need
- For the series resistor, these are usually enough: **47 ohm, 33 ohm, 22 ohm**.
- Base resistor: **330 ohm**.

---

## Software: LIRC (Linux Infrared Remote Control)

### What it is
- System software (service + tools) that decodes receive signals and generates transmit signals including 38 kHz.

### How it works (roughly)
- **Receive:** Pulse/space lengths from the TSOP are measured and emitted as button events.
- **Send:** 38 kHz is generated and gated on/off in bursts for the desired code.

### Typical usage
- **Create mapping/profile:** Learn a remote (e.g. `irrecord`, depending on OS/setup).
- **Inspect receive:** `irw` (shows detected buttons).
- **Send:** `irsend SEND_ONCE <remote> <key>`.

### Python integration (minimal)
- Start `irw` as a process and read lines (event stream).
- Call `irsend` via `subprocess` to send a button.

---

## Wires from the Pi to an external board
Typically **5 wires**:
1) **GND**
2) **5V** (IR LED stage)
3) **3V3** (TSOP)
4) **GPIO_OUT** (transistor base via 330 ohm)
5) **GPIO_IN** (TSOP OUT)
