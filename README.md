# FH6 Overlay

A frameless, always-on-top Windows overlay for Forza Horizon 6 that displays rev lights and real-time controller telemetry - built in Python with PyQt6.

> **The distributed exe is clean.** It is a Python script compiled with PyInstaller. Some antivirus tools flag PyInstaller-built executables as suspicious by default - this is a well-documented false positive. Every line of source code in this repository is open for inspection. If you prefer not to use the pre-built exe, build it yourself: `python -m PyInstaller FH6Overlay.spec`.

---

## Architecture

```
overlay.py          - PyQt6 top-bar window; paint loop; layout constants
telemetry.py        - UDP listener; packet parser; adaptive RPM calibration; rev light logic
controller.py       - XInput poller; trigger/button state
config.py           - Config dataclass; INI read/write
setup_wizard.py     - First-run PyQt6 dialog; XInput button capture
```

At runtime, two daemon threads run in parallel:

- **UDP thread** (`telemetry.py`) - receives raw bytes from the game, parses them into `TelemetryState`
- **XInput thread** (`controller.py`) - polls the gamepad at ~60 Hz into `ControllerState`

The main thread runs the Qt event loop. A `QTimer` fires every 50 ms (20 fps), reads both state objects, and calls `QWidget.update()` to trigger a repaint.

---

## Module Reference

### `telemetry.py`

#### UDP Packet Format

FH6 broadcasts a **324-byte Car Dash packet** over UDP in little-endian format. This is the same format used by FH4 and FH5.

| Offset | Type    | Field               |
|--------|---------|---------------------|
| 8      | float32 | `engine_max_rpm`    |
| 12     | float32 | `engine_idle_rpm`   |
| 16     | float32 | `current_engine_rpm`|
| 319    | uint8   | `gear`              |

`parse_packet()` extracts these four values. Packets shorter than 20 bytes raise `struct.error`. Packets shorter than 320 bytes return `gear=0`.

**Gear encoding:** `0` = reverse, `1–10` = forward gears. The raw value `255` (int8 `−1`) is normalised to `11`; both `0` and `11` are treated as reverse by the display layer.

#### `TelemetryState`

Shared mutable object written by the UDP daemon thread and read by the Qt paint thread.

| Field           | Type  | Description                                                    |
|-----------------|-------|----------------------------------------------------------------|
| `ratio`         | float | Current RPM position in `[0.0, 1.0]`                          |
| `connected`     | bool  | True while packets are arriving                                |
| `is_electric`   | bool  | True when `idle_rpm < 100` (electric motors have no idle)      |
| `gear`          | int   | Raw gear from packet                                           |
| `display_gear`  | int   | Like `gear` but suppresses transient `gear=11` bursts          |

**`check_timeout(timeout_seconds=2.0)`** - called on every paint tick. If no packet has arrived within the timeout, sets `connected = False` and resets calibration state so the next car is re-evaluated cleanly.

#### Adaptive RPM Calibration

Forza's `engine_max_rpm` field over-reports the actual redline. The overlay learns the true effective maximum by observing real driving.

**Calibration key** - `"<rounded_max_rpm>,<idle_rpm_rounded_to_10>"` - uniquely identifies a car model. Stored in `calibration.json` next to the executable.

**Before calibration** - `effective_max = engine_max_rpm × 0.90` (90% fallback).

**Primary trigger** - on every upshift while `peak_rpm > engine_max_rpm × 0.65`, the peak RPM seen since the last shift is saved as the effective max with a 3% headroom buffer:
```
effective_max = peak_rpm × 1.03
```

**Fallback trigger** - if RPM plateaus at the rev limiter for 250 ms at `> 65%` of reported max (and no upshift calibration has happened yet), the plateau value is used instead. The stability timer is only reset by a *significant* new peak (`> 2%` increase) so rapid limiter bouncing doesn't starve the timer.

**Electric cars** - calibration is skipped entirely; `ratio` is always `0.0`.

#### `lights_state(ratio, connected) → list[str]`

Returns 9 hex colour strings for the rev lights:

| Condition              | Output                                |
|------------------------|---------------------------------------|
| `not connected`        | All `#1f2937` (unlit dark grey)       |
| `ratio >= 0.93`        | All `#ff1a1a` (bright flash red)      |
| Otherwise              | Proportional fill (see below)         |

Proportional fill - each light `i` lights up when `ratio >= (i+1) × (0.93/9)`:
- Lights 0–2: `#22c55e` (green)
- Lights 3–5: `#eab308` (yellow)
- Lights 6–8: `#ef4444` (red)

---

### `controller.py`

Polls `xinput1_4.dll` via `ctypes` at ~60 Hz (`_POLL_S = 0.016 s`). On controller disconnect, retries every 1 second. Non-fatal if `xinput1_4.dll` is missing - the controller section still renders but stays in the disconnected state.

#### `ControllerState`

| Field        | Type  | Description                                   |
|--------------|-------|-----------------------------------------------|
| `lt_pct`     | int   | Left trigger (brake), 0–100                   |
| `rt_pct`     | int   | Right trigger (throttle), 0–100               |
| `shift_up`   | bool  | Shift-up button held                          |
| `shift_down` | bool  | Shift-down button held                        |
| `clutch`     | bool  | Clutch button held (`False` if unassigned)    |
| `connected`  | bool  | Controller present                            |

`start_controller_listener(state, shift_up_button, shift_down_button, clutch_button)` - button values are XInput bitmasks read from `config.ini`.

---

### `config.py`

`CONFIG_PATH` resolves to the directory containing `sys.executable` when frozen by PyInstaller, or the directory containing `config.py` otherwise. This means `config.ini` always lives next to `FH6Overlay.exe`.

#### `Config` dataclass

| Field               | Default  | INI key              | Description                          |
|---------------------|----------|----------------------|--------------------------------------|
| `udp_port`          | `20777`  | `[network] udp_port` | UDP port the game sends data to      |
| `shift_up_button`   | `0x2000` | `[buttons] shift_up` | XInput bitmask for shift-up button   |
| `shift_down_button` | `0x4000` | `[buttons] shift_down`| XInput bitmask for shift-down button |
| `clutch_button`     | `0`      | `[buttons] clutch`   | XInput bitmask for clutch (`0` = off)|

`load_config(path)` - falls back to the dataclass default for any missing or non-integer value. Returns `Config()` if the file does not exist.

`save_config(path, config)` - writes an INI file with an inline XInput button cheat-sheet in the comments.

#### XInput Button Bitmasks Reference

| Button       | Value  |
|--------------|--------|
| A            | 4096   |
| B            | 8192   |
| X            | 16384  |
| Y            | 32768  |
| LB           | 256    |
| RB           | 512    |
| Back         | 32     |
| Start        | 16     |
| Left Thumb   | 64     |
| Right Thumb  | 128    |

---

### `setup_wizard.py`

Shown automatically on first launch when `config.ini` does not exist. Uses its own private XInput structs (no dependency on `controller.py`) to avoid threading conflicts.

**Button capture** - uses edge detection: `new_pressed = current_buttons & ~previous_buttons`. The lowest set bit of `new_pressed` is recorded so that holding multiple buttons simultaneously only captures one.

**Steps:**
1. `(1/3) Press your SHIFT UP button` - not skippable
2. `(2/3) Press your SHIFT DOWN button` - not skippable
3. `(3/3) Press your CLUTCH button` - has a "Skip (no clutch)" button

If `xinput1_4.dll` is unavailable, the wizard immediately saves a config with default button values and closes.

---

### `overlay.py`

#### Window

| Property       | Value                                                    |
|----------------|----------------------------------------------------------|
| Flags          | Frameless, always-on-top, `Tool` (no taskbar entry)      |
| Background     | Fully transparent (`WA_TranslucentBackground`)           |
| Position       | Top-centre of primary screen, 10 px from top             |
| Update rate    | 50 ms timer (20 fps)                                     |

**Width calculation:**
```
16 (pad) + 9×44 + 8×7 (rev lights) + 14 + 1 + 14 (gap/divider) + 90+6+28+6+90 (controller) + 16 (pad)
```

#### Rev Lights

Nine circles drawn with three glow halos each. Halos are concentric ellipses progressively smaller with decreasing alpha:

| Layer  | Extra size | Alpha |
|--------|-----------|-------|
| Outer  | +14 px    | 18    |
| Middle | +9 px     | 38    |
| Inner  | +5 px     | 65    |

**Shift flash** - when `ratio >= SHIFT_RATIO (0.93)`, all lights are suppressed on alternating paint ticks (every 3 ticks × 50 ms ≈ 6.7 Hz blink). The entire light row is hidden on the "off" phase so the transparent background shows through rather than drawing dark circles.

#### Controller Widget

```
[  BRAKE BAR (LT %)  ] [▲] [  THROTTLE BAR (RT %)  ]
                       [gear]
                       [▼]
```

- **Brake bar** (left, 90 px) - red gradient, fills left → right proportional to `lt_pct`
- **Throttle bar** (right, 90 px) - green gradient, fills right → left proportional to `rt_pct`
- **Shift ▲ / ▼** (12 px tall each) - yellow fill that fades out over 300 ms after button release
- **Gear box** (22 px tall) - shows current gear; overrides to yellow `"C"` while clutch is held

**Gear label mapping:**

| Condition              | Label |
|------------------------|-------|
| `not connected`        | `–`   |
| `display_gear == 0`    | `R`   |
| `is_electric`          | `D`   |
| Otherwise              | gear number as string |

---

## Configuration File

`config.ini` is created next to the executable on first run. Delete it to re-run the button setup wizard.

```ini
# FH6 Overlay configuration
# Delete this file to re-run the button setup wizard
#
# Common XInput button values:
#   A=4096   B=8192   X=16384  Y=32768
#   LB=256   RB=512   Back=32  Start=16

[network]
udp_port = 20777

[buttons]
shift_up = 8192
shift_down = 16384
clutch = 0
```

---

## Calibration File

`calibration.json` is created and updated automatically during normal driving. It maps a car identification key to a learned effective max RPM.

```json
{
  "9000,800": 8847.3
}
```

The key format is `"<rounded_max_rpm>,<idle_rpm_rounded_to_10>"`. The value is the effective redline in RPM (peak observed RPM × 1.03). Delete this file to clear all learned calibrations.

---

## Building

Requires PyInstaller 6+:

```
python -m PyInstaller FH6Overlay.spec
```

Output: `dist/FH6Overlay.exe` - single-file, no Python installation required.

The spec uses `console=False` (no console window) and bundles all PyQt6 dependencies.

---

## Command-Line Arguments

```
FH6Overlay.exe [--port PORT]
```

| Argument | Default              | Description                                      |
|----------|----------------------|--------------------------------------------------|
| `--port` | from `config.ini`    | Override the UDP listen port for this session only |

Useful when running alongside `telemetry_server.py` (dev tool, not included in this release) to receive relayed packets on port 20778 instead of 20777.

---

## Runtime Files

| File               | Created by     | Description                                              |
|--------------------|----------------|----------------------------------------------------------|
| `config.ini`       | Setup wizard   | Button assignments and UDP port. Delete to reset wizard. |
| `calibration.json` | Telemetry loop | Learned effective redlines per car. Delete to reset.     |

Both files are written next to the executable regardless of the current working directory.

---

## Dependencies

| Package  | Version  | Purpose                    |
|----------|----------|----------------------------|
| PyQt6    | 6.x      | GUI framework, paint loop  |
| Python   | 3.13     | Runtime (not needed for exe)|

No third-party packages beyond PyQt6. All other modules (`socket`, `struct`, `ctypes`, `threading`, `configparser`, `json`) are Python stdlib.
