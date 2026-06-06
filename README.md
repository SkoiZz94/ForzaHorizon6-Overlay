# Forza Horizon 6 RPM Overlay

A frameless, always-on-top Windows overlay for Forza Horizon 6 that displays rev lights and real-time controller telemetry — built in Python with PyQt6.

> **The distributed exe is clean.** It is a Python script compiled with PyInstaller. Some antivirus tools flag PyInstaller-built executables as suspicious by default — this is a well-documented false positive. Every line of source code in this repository is open for inspection. If you prefer not to use the pre-built exe, build it yourself: `python -m PyInstaller FH6Overlay.spec`.

---

## Architecture

```
overlay.py          — PyQt6 frameless always-on-top window; paint loop; ghost handles; scale/drag
telemetry.py        — UDP listener; packet parser; adaptive RPM calibration; rev light logic
controller.py       — XInput poller; trigger/button state; hide-overlay rising-edge detection
config.py           — Config dataclass (27 fields); INI read/write
setup_wizard.py     — First-run dialog; transmission type + XInput button capture (5 steps)
settings_panel.py   — Live settings panel; colour picker; visibility toggles; calibration reset
```

At runtime two daemon threads run in parallel:

- **UDP thread** (`telemetry.py`) — receives raw bytes from the game, parses them into `TelemetryState`
- **XInput thread** (`controller.py`) — polls the gamepad at ~60 Hz into `ControllerState`

The main thread runs the Qt event loop. A `QTimer` fires every 50 ms (20 fps), reads both state objects, and calls `QWidget.update()` to trigger a repaint.

---

## Module Reference

### `telemetry.py`

#### UDP Packet Format

FH6 broadcasts a **324-byte Car Dash packet** over UDP in little-endian format (same as FH4/FH5).

| Offset | Type    | Field                |
|--------|---------|----------------------|
| 8      | float32 | `engine_max_rpm`     |
| 12     | float32 | `engine_idle_rpm`    |
| 16     | float32 | `current_engine_rpm` |
| 319    | uint8   | `gear`               |

`parse_packet()` extracts these four values. Packets shorter than 20 bytes raise `struct.error`. Packets shorter than 320 bytes return `gear=0`.

**Gear encoding:** `0` = reverse, `1–10` = forward gears. The raw value `255` (int8 `−1`) is normalised to `11`; both `0` and `11` are treated as reverse by the display layer.

#### `TelemetryState`

| Field           | Type  | Description                                                    |
|-----------------|-------|----------------------------------------------------------------|
| `ratio`         | float | Current RPM position in `[0.0, 1.0]`                          |
| `connected`     | bool  | True while packets are arriving                                |
| `is_electric`   | bool  | True when `idle_rpm < 100` (electric motors have no idle)      |
| `gear`          | int   | Raw gear from packet                                           |
| `display_gear`  | int   | Like `gear` but suppresses transient `gear=11` bursts          |

**`check_timeout(timeout_seconds=2.0)`** — called on every paint tick. If no packet has arrived within the timeout, sets `connected = False` and resets calibration state so the next car is re-evaluated cleanly.

**`reset_calibration()`** — clears all in-memory calibration state and deletes `calibration.json`. Called by the settings panel's Reset calibration button.

#### Adaptive RPM Calibration

Forza's `engine_max_rpm` field over-reports the actual redline. The overlay learns the true effective maximum by observing real driving.

**Calibration key** — `"<rounded_max_rpm>,<idle_rpm_rounded_to_10>"` — uniquely identifies a car model. Stored in `calibration.json` next to the executable.

**Before calibration** — `effective_max = engine_max_rpm × 0.90` (90% fallback).

**Primary trigger** — on every upshift while `peak_rpm > engine_max_rpm × 0.65`, the peak RPM seen since the last shift is saved:
```
effective_max = peak_rpm × 1.03
```

**Fallback trigger** — if RPM plateaus at the rev limiter for 250 ms at `> 65%` of reported max, the plateau value is used. The stability timer only resets on a significant new peak (`> 2%` increase).

**Electric cars** — calibration is skipped; `ratio` is always `0.0`.

#### `lights_state(ratio, connected, config) → list[str]`

Returns 9 hex colour strings for the rev lights using colours from `config`:

| Condition       | Output                                          |
|-----------------|-------------------------------------------------|
| `not connected` | All `#1f2937` (unlit dark grey)                 |
| `ratio >= 0.93` | All `#ff1a1a` (bright flash red)                |
| Otherwise       | Proportional fill across zone1/zone2/zone3 colours |

---

### `controller.py`

Polls `xinput1_4.dll` via `ctypes` at ~60 Hz (`_POLL_S = 0.016 s`). On controller disconnect, retries every 1 second. Non-fatal if `xinput1_4.dll` is missing.

#### `ControllerState`

| Field         | Type  | Description                                        |
|---------------|-------|----------------------------------------------------|
| `lt_pct`      | int   | Left trigger (brake), 0–100                        |
| `rt_pct`      | int   | Right trigger (throttle), 0–100                    |
| `shift_up`    | bool  | Shift-up button held                               |
| `shift_down`  | bool  | Shift-down button held                             |
| `clutch`      | bool  | Clutch button held (`False` if unassigned)         |
| `connected`   | bool  | Controller present                                 |
| `toggle_hide` | bool  | True for exactly one tick on rising edge of hide combo |

`start_controller_listener(state, shift_up_button, shift_down_button, clutch_button, hide_button)` — button values are XInput bitmasks from `config.ini`. `hide_button` is a bitmask; holding all matching bits fires `toggle_hide` on the rising edge.

---

### `config.py`

`CONFIG_PATH` resolves to the directory containing `sys.executable` when frozen, or the directory containing `config.py` otherwise — so `config.ini` always lives next to `FH6Overlay.exe`.

#### `Config` dataclass

| Field                   | Default     | Section     | Description                                    |
|-------------------------|-------------|-------------|------------------------------------------------|
| `udp_port`              | `20777`     | network     | UDP port the game sends data to                |
| `shift_up_button`       | `0x2000`    | buttons     | XInput bitmask for shift-up                    |
| `shift_down_button`     | `0x4000`    | buttons     | XInput bitmask for shift-down                  |
| `clutch_button`         | `0`         | buttons     | XInput bitmask for clutch (`0` = off)          |
| `transmission`          | `"manual"`  | general     | `"automatic"`, `"manual"`, or `"manual_clutch"` |
| `hide_button`           | `0`         | buttons     | XInput bitmask combo to toggle overlay visibility |
| `overlay_x`             | `-1`        | overlay     | X position; `-1` = auto-centre on primary screen |
| `overlay_y`             | `10`        | overlay     | Y position in pixels from top of screen        |
| `overlay_scale`         | `1.0`       | overlay     | Scale factor (`0.5`–`3.0`)                     |
| `show_rev_lights`       | `True`      | overlay     | Whether to render the 9 rev lights             |
| `show_gear`             | `True`      | overlay     | Whether to render the gear indicator           |
| `show_shift_indicators` | `True`      | overlay     | Whether to render the shift-up/down arrows     |
| `show_brake_bar`        | `True`      | overlay     | Whether to render the brake bar                |
| `show_throttle_bar`     | `True`      | overlay     | Whether to render the throttle bar             |
| `show_brake_label`      | `False`     | overlay     | Whether to show the brake % text label         |
| `show_throttle_label`   | `False`     | overlay     | Whether to show the throttle % text label      |
| `colour_rev_zone1`      | `#22c55e`   | colours     | Rev lights — green zone (lights 0–2)           |
| `colour_rev_zone2`      | `#eab308`   | colours     | Rev lights — yellow zone (lights 3–5)          |
| `colour_rev_zone3`      | `#ef4444`   | colours     | Rev lights — red zone (lights 6–8)             |
| `colour_brake_start`    | `#991b1b`   | colours     | Brake bar — gradient start (left)              |
| `colour_brake_end`      | `#ef4444`   | colours     | Brake bar — gradient end (right)               |
| `colour_throttle_start` | `#15803d`   | colours     | Throttle bar — gradient start (right)          |
| `colour_throttle_end`   | `#22c55e`   | colours     | Throttle bar — gradient end (left)             |
| `colour_shift_active`   | `#facc15`   | colours     | Shift indicator active fill colour             |
| `colour_gear_bg`        | `#0f172a`   | colours     | Gear box background colour                     |
| `colour_gear_text`      | `#e2e8f0`   | colours     | Gear box text colour                           |
| `colour_overlay_bg`     | `#0f172a`   | colours     | Overlay panel background colour                |

`load_config(path)` — falls back to dataclass defaults for any missing or invalid key.  
`save_config(path, config)` — writes all sections with an XInput button reference in the header comment.

#### XInput Button Bitmasks

| Button      | Value  |
|-------------|--------|
| A           | 4096   |
| B           | 8192   |
| X           | 16384  |
| Y           | 32768  |
| LB          | 256    |
| RB          | 512    |
| Back        | 32     |
| Start       | 16     |
| Left Thumb  | 64     |
| Right Thumb | 128    |

---

### `setup_wizard.py`

Shown automatically on first launch when `config.ini` does not exist. Uses its own private XInput structs (no dependency on `controller.py`) to avoid threading conflicts.

**Steps:**

| Step | Prompt | Skippable |
|------|--------|-----------|
| 1/5  | Choose transmission type (Automatic / Manual / Manual w/ Clutch) | No — radio button selection |
| 2/5  | Press SHIFT UP button | No |
| 3/5  | Press SHIFT DOWN button | No |
| 4/5  | Press CLUTCH button | Yes — skipped automatically for non-`manual_clutch` |
| 5/5  | Press HIDE button or combo | Yes |

Steps 2–3 are skipped entirely for Automatic (saved as `0`). Step 4 is skipped unless transmission is `manual_clutch`. If `xinput1_4.dll` is unavailable, the wizard immediately saves defaults and closes.

**Button capture** — rising-edge detection: `new_pressed = current_buttons & ~previous_buttons`. Single-button steps isolate the lowest set bit; the hide combo captures all bits currently held at the moment of press.

---

### `overlay.py`

#### Window

| Property    | Value                                                          |
|-------------|----------------------------------------------------------------|
| Flags       | Frameless, always-on-top, Tool (no taskbar entry)              |
| Background  | Fully transparent (`WA_TranslucentBackground`)                 |
| Position    | Saved in `config.ini`; `overlay_x = -1` auto-centres          |
| Scale       | Saved in `config.ini` as `overlay_scale` (0.5–3.0)            |
| Update rate | 50 ms timer (20 fps)                                           |

All drawing is wrapped in `painter.scale(s, s)` — every coordinate and size in the paint code is in logical units and multiplied by `_scale` at render time.

#### Ghost Handles

A 32 px wide handle strip sits to the right of the content area. It is always painted with `QColor(0, 0, 0, 1)` (alpha = 1) so Windows routes mouse events to it even when the overlay is otherwise transparent.

| Handle   | Icon | Action                                              |
|----------|------|-----------------------------------------------------|
| Move     | ⣿    | Drag to reposition; position saved on mouse release |
| Resize   | ⟺   | Drag right/left to scale; scale saved on release    |
| Settings | ⚙    | Opens `SettingsPanel`                               |
| Close    | ✕    | Quits the application                               |

Handles are visible only when the mouse is over the overlay. Hit-testing is done in logical (pre-scale) coordinates.

#### Rev Lights

Nine circles drawn with three glow halos each. Halos are concentric ellipses with decreasing alpha:

| Layer  | Extra size | Alpha |
|--------|------------|-------|
| Outer  | +14 px     | 18    |
| Middle | +9 px      | 38    |
| Inner  | +5 px      | 65    |

**Shift flash** — when `ratio >= 0.93`, all lights blink at ~6.7 Hz (alternating every 3 paint ticks × 50 ms). On the "off" phase the transparent background shows through rather than dark circles.

#### Controller Widget

```
[ BRAKE BAR (LT %) ] [▲] [ THROTTLE BAR (RT %) ]
                    [gear]
                    [ ▼ ]
```

- **Brake bar** (left) — red gradient, fills left → right proportional to `lt_pct`
- **Throttle bar** (right) — green gradient, fills right → left proportional to `rt_pct`
- **Shift ▲ / ▼** — active fill colour fades out over 300 ms after button release
- **Gear box** — shows current gear; overrides to yellow `"C"` while clutch is held

**Gear label mapping:**

| Condition              | Label |
|------------------------|-------|
| `not connected`        | `–`   |
| `display_gear == 0`    | `R`   |
| `is_electric`          | `D`   |
| Otherwise              | gear number |

---

### `settings_panel.py`

A non-blocking `QDialog` opened via the ⚙ ghost handle. All changes are applied live to the overlay and persisted to `config.ini` immediately.

**Sections:**

| Section             | Controls                                                              |
|---------------------|-----------------------------------------------------------------------|
| Transmission        | Radio buttons: Automatic / Manual / Manual w/ Clutch                 |
| Overlay elements    | Toggle switches for each of the 7 visible elements                   |
| Colours             | Colour swatches opening a custom HSV colour picker                   |
| Controller buttons  | Re-capture buttons for Shift Up / Down / Clutch / Hide               |
| Calibration         | Reset all learned RPM redlines                                        |
| Restore defaults    | Resets all colours, visibility, position, scale, and transmission     |
| Network             | UDP port (requires restart)                                           |

**Custom colour picker** (`_ColourPicker`) — frameless dark-themed dialog with:
- HSV saturation/value square
- Vertical hue bar
- Hex input field
- 12 preset swatches
- Cancel / OK — Apply buttons

---

## Configuration File

`config.ini` is created next to the executable on first run. Delete it to re-run the setup wizard.

```ini
[general]
transmission = manual

[network]
udp_port = 20777

[buttons]
shift_up = 8192
shift_down = 16384
clutch = 0
hide_button = 0

[overlay]
x = -1
y = 10
scale = 1.0
show_rev_lights = true
show_gear = true
show_shift_indicators = true
show_brake_bar = true
show_throttle_bar = true
show_brake_label = false
show_throttle_label = false

[colours]
rev_zone1 = #22c55e
rev_zone2 = #eab308
rev_zone3 = #ef4444
brake_start = #991b1b
brake_end = #ef4444
throttle_start = #15803d
throttle_end = #22c55e
shift_active = #facc15
gear_bg = #0f172a
gear_text = #e2e8f0
overlay_bg = #0f172a
```

---

## Calibration File

`calibration.json` is created and updated automatically during normal driving. It maps a car identification key to a learned effective max RPM.

```json
{ "9000,800": 8847.3 }
```

Key format: `"<rounded_max_rpm>,<idle_rpm_rounded_to_10>"`. Value: effective redline in RPM (peak × 1.03). Delete the file or use the Settings panel to clear all learned calibrations.

---

## Building

Requires PyInstaller 6+:

```
python -m PyInstaller FH6Overlay.spec
```

Output: `dist/FH6Overlay.exe` — single-file, no Python installation required. The spec uses `console=False` and bundles all PyQt6 dependencies.

---

## Dependencies

| Package | Version | Purpose                      |
|---------|---------|------------------------------|
| PyQt6   | 6.x     | GUI framework, paint loop    |
| Python  | 3.13    | Runtime (not needed for exe) |

No third-party packages beyond PyQt6. All other modules (`socket`, `struct`, `ctypes`, `threading`, `configparser`, `json`) are Python stdlib.

---

## Tests

```
pytest tests/
```

| File                        | What it covers                                      |
|-----------------------------|-----------------------------------------------------|
| `test_config.py`            | Defaults, round-trip save/load, missing-key fallback |
| `test_telemetry_reset.py`   | Calibration reset clears state and deletes file      |
| `test_controller_hide.py`   | Rising-edge detection for hide combo                 |
| `test_overlay_geometry.py`  | Content size, scale, handle hit-testing              |
