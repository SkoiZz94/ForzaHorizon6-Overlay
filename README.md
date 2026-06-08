# Forza Horizon 6 RPM Overlay

A frameless, always-on-top Windows overlay for Forza Horizon 6 that displays rev lights and real-time controller telemetry - built in Python with PyQt6 and Qt Quick.

> **The distributed exe is clean.** It is a Python script compiled with PyInstaller. Some antivirus tools flag PyInstaller-built executables as suspicious by default - this is a well-documented false positive. Every line of source code in this repository is open for inspection. If you prefer not to use the pre-built exe, build it yourself: `python -m PyInstaller FH6Overlay.spec` (outputs `dist/FH6RPMOverlay2.0.0.exe`).

---

## Architecture

```
overlay.py            - QQuickWindow host; tick timer; edit mode; hover controls; tray icon
elements/
  base.py             - BaseElement(QQuickPaintedItem): drag/resize/style menu; shared helpers
  bar_item.py         - BrakeItem + ThrottleItem (6 visual styles each)
  rpm_item.py         - RPMItem (7 visual styles)
  gear_item.py        - GearItem (6 visual styles)
  shift_item.py       - ShiftUpItem + ShiftDnItem (6 visual styles each)
telemetry.py          - UDP listener; packet parser; adaptive RPM calibration
controller.py         - XInput poller; trigger/button state; hide-overlay rising-edge detection
config.py             - Config dataclass; style catalogues; INI read/write
setup_wizard.py       - First-run dialog; transmission type + XInput button capture (5 steps)
settings_panel.py     - SettingsPanel (layout, transmission, controller, calibration, advanced); ElementsPanel (visibility, styles, colours - active during Edit Layout)
```

At runtime two daemon threads run in parallel:

- **UDP thread** (`telemetry.py`) - receives raw bytes from the game, parses them into `TelemetryState`
- **XInput thread** (`controller.py`) - polls the gamepad at ~60 Hz into `ControllerState`

The main thread runs the Qt Quick event loop. A 16 ms `QTimer` fires every frame, reads both state objects, and calls `update()` on each visible element to trigger repaints.

---

## Element System

The overlay window is a full-screen transparent `QQuickWindow`. Each display element is a `QQuickPaintedItem` child positioned independently. All element classes inherit from `BaseElement`.

| Class           | Key   | Styles |
|-----------------|-------|--------|
| `RPMItem`       | `rpm` | Dot Row, Continuous Bar, Segmented Tiles, Arc Gauge, F1 Split, Shift Light Only, Spectrum Bars |
| `BrakeItem`     | `brake` | Horizontal Bar, Vertical Bar, Quarter Arc, Numeric Only, Radial Fill, Stacked Blocks |
| `ThrottleItem`  | `throttle` | (same 6 as Brake) |
| `GearItem`      | `gear` | Box, Minimal, Gear + Mode Tag, Hexagon, Pill Badge, RPM Color Fill |
| `ShiftUpItem`   | `shift_up` | Triangle, Chevrons, Flash Bar, Text Label, Glow Pulse, Pulse Ring |
| `ShiftDnItem`   | `shift_dn` | (same 6 as Shift Up) |

### Edit Layout mode

Activating **Edit Layout** (via Settings panel or tray menu) sets each element into drag/resize mode:

- **Left-drag** - move element; position written to `config.ini` on mouse release
- **Right-drag corner** - resize element (bottom-right triangle grip)
- **Right-click** - context menu to change the element's visual style (saved immediately)
- **Apply** (floating Overlay Appearance panel) - writes all position/size changes to disk and exits edit mode
- **Cancel** (floating Overlay Appearance panel) - restores the pre-edit snapshot without writing

---

## Module Reference

### `telemetry.py`

#### UDP Packet Format

FH6 broadcasts a **324-byte Car Dash packet** over UDP in little-endian format (same layout as FH4/FH5).

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

**`check_timeout(timeout_seconds=2.0)`** - called on every tick. If no packet has arrived within the timeout, sets `connected = False` and resets calibration state so the next car is re-evaluated cleanly.

**`reset_calibration()`** - clears all in-memory calibration state and deletes `calibration.json`. Called by the Settings panel's Reset calibration button.

#### Adaptive RPM Calibration

Forza's `engine_max_rpm` field over-reports the actual redline. The overlay learns the true effective maximum by observing real driving.

**Calibration key** - `"<rounded_max_rpm>,<idle_rpm_rounded_to_10>"` - uniquely identifies a car model. Stored in `calibration.json` next to the executable.

**Before calibration** - `effective_max = engine_max_rpm × 0.90` (90% fallback).

**Primary trigger** - on every upshift while `peak_rpm > engine_max_rpm × 0.65`, the peak RPM seen since the last shift is saved:
```
effective_max = peak_rpm × 1.03
```

**Fallback trigger** - if RPM plateaus at the rev limiter for 250 ms at `> 65%` of reported max, the plateau value is used. The stability timer only resets on a significant new peak (`> 2%` increase).

**Downshift suppression** - when a downshift is detected (`gear` decreases), calibration updates are suspended for 15 packets (~750 ms) to prevent RPM spikes from inflating the effective max.

**Electric cars** - calibration is skipped; `ratio` is always `0.0`.

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

`start_controller_listener(state, shift_up_button, shift_down_button, clutch_button, hide_button)` - button values are XInput bitmasks from `config.ini`. `hide_button` is a bitmask; holding all matching bits fires `toggle_hide` on the rising edge.

---

### `config.py`

`CONFIG_PATH` resolves to the directory containing `sys.executable` when frozen, or the directory containing `config.py` otherwise - so `config.ini` always lives next to `FH6Overlay.exe`.

#### Style Catalogues

```python
RPM_STYLES      = ("dot_row", "cont_bar", "seg_tiles", "arc_gauge",
                   "f1_split", "shift_light", "spectrum_bars")
BRAKE_STYLES    = THROTTLE_STYLES = ("horiz_bar", "vert_bar", "quarter_arc",
                                      "numeric", "radial_fill", "stacked_blocks")
GEAR_STYLES     = ("box", "minimal", "mode_tag", "hexagon", "pill", "rpm_color_fill")
SHIFT_STYLES    = ("triangle", "chevrons", "flash_bar",
                   "text_label", "glow_pulse", "pulse_ring")
```

Invalid style values in `config.ini` fall back to the dataclass default.

#### `Config` dataclass

**General**

| Field                   | Default      | Section  | Description                                        |
|-------------------------|--------------|----------|----------------------------------------------------|
| `udp_port`              | `20777`      | network  | UDP port the game sends data to                    |
| `shift_up_button`       | `0x2000`     | buttons  | XInput bitmask for shift-up                        |
| `shift_down_button`     | `0x4000`     | buttons  | XInput bitmask for shift-down                      |
| `clutch_button`         | `0`          | buttons  | XInput bitmask for clutch (`0` = off)              |
| `transmission`          | `"manual"`   | general  | `"automatic"`, `"manual"`, or `"manual_clutch"`    |
| `hide_button`           | `0`          | buttons  | XInput bitmask combo to toggle overlay visibility  |
| `overlay_scale`         | `1.0`        | overlay  | Legacy scale factor (`0.5`–`3.0`)                  |
| `shift_ratio`           | `0.93`       | overlay  | RPM ratio that triggers the shift flash (0.80–0.98)|

**Visibility**

| Field                   | Default | Description                                              |
|-------------------------|---------|----------------------------------------------------------|
| `show_rev_lights`       | `True`  | Whether to render the RPM element                        |
| `show_gear`             | `True`  | Whether to render the gear element                       |
| `show_shift_indicators` | `True`  | Whether to render shift-up and shift-down elements       |
| `show_brake_bar`        | `True`  | Whether to render the brake element                      |
| `show_throttle_bar`     | `True`  | Whether to render the throttle element                   |
| `show_brake_label`      | `False` | Show % text label on the brake element                   |
| `show_throttle_label`   | `False` | Show % text label on the throttle element                |
| `brake_bar_reversed`    | `False` | Flip the fill direction of the brake element             |
| `throttle_bar_reversed` | `False` | Flip the fill direction of the throttle element          |

**Colours**

| Field                   | Default   | Description                                    |
|-------------------------|-----------|------------------------------------------------|
| `colour_rev_zone1`      | `#22c55e` | RPM - green zone (lights 0–2)                  |
| `colour_rev_zone2`      | `#eab308` | RPM - yellow zone (lights 3–5)                 |
| `colour_rev_zone3`      | `#ef4444` | RPM - red zone (lights 6–8)                    |
| `colour_brake_start`    | `#991b1b` | Brake - gradient start colour                  |
| `colour_brake_end`      | `#ef4444` | Brake - gradient end / accent colour           |
| `colour_throttle_start` | `#15803d` | Throttle - gradient start colour               |
| `colour_throttle_end`   | `#22c55e` | Throttle - gradient end / accent colour        |
| `colour_shift_active`   | `#facc15` | Shift indicator active fill colour             |
| `colour_gear_bg`        | `#0f172a` | Gear element background colour                 |
| `colour_gear_text`      | `#e2e8f0` | Gear element text colour                       |

**Styles**

| Field           | Default       | Valid values (see style catalogues above) |
|-----------------|---------------|-------------------------------------------|
| `rpm_style`     | `"dot_row"`   | Any entry in `RPM_STYLES`                 |
| `brake_style`   | `"horiz_bar"` | Any entry in `BRAKE_STYLES`               |
| `throttle_style`| `"horiz_bar"` | Any entry in `THROTTLE_STYLES`            |
| `gear_style`    | `"box"`       | Any entry in `GEAR_STYLES`                |
| `shift_up_style`| `"triangle"`  | Any entry in `SHIFT_STYLES`               |
| `shift_dn_style`| `"triangle"`  | Any entry in `SHIFT_STYLES`               |

**Layout** (per element: `{key}_x`, `{key}_y`, `{key}_w`, `{key}_h`)

`x`/`y` default to `-1` (auto-positioned by `_apply_default_layout` relative to screen centre). `w`/`h` are minimum-clamped on load.

| Element    | Default w×h | Min w | Min h |
|------------|-------------|-------|-------|
| `rpm`      | 500 × 56    | 40    | 20    |
| `brake`    | 110 × 40    | 40    | 20    |
| `throttle` | 110 × 40    | 40    | 20    |
| `gear`     | 60 × 60     | 30    | 20    |
| `shift_up` | 60 × 32     | 30    | 14    |
| `shift_dn` | 60 × 32     | 30    | 14    |

`load_config(path)` - falls back to dataclass defaults for any missing or invalid key.  
`save_config(path, config)` - writes all sections with an XInput button reference in the header comment.

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
| 1/5  | Choose transmission type (Automatic / Manual / Manual w/ Clutch) | No - radio button selection |
| 2/5  | Press SHIFT UP button | No |
| 3/5  | Press SHIFT DOWN button | No |
| 4/5  | Press CLUTCH button | Yes - skipped automatically for non-`manual_clutch` |
| 5/5  | Press HIDE button or combo | Yes |

Steps 2–3 are skipped entirely for Automatic (saved as `0`). Step 4 is skipped unless transmission is `manual_clutch`. If `xinput1_4.dll` is unavailable, the wizard immediately saves defaults and closes.

**Button capture** - rising-edge detection: `new_pressed = current_buttons & ~previous_buttons`. Single-button steps isolate the lowest set bit; the hide combo captures all bits currently held at the moment of press.

---

### `overlay.py`

#### Window

| Property    | Value                                                          |
|-------------|----------------------------------------------------------------|
| Type        | `QQuickWindow` (full-screen, frameless, always-on-top)         |
| Background  | Fully transparent                                              |
| Update rate | 16 ms `QTimer` (~60 fps)                                       |

The window hosts all element items as children of `contentItem()`. A separate always-on-top `QWidget` (`_HoverControls`) provides the Settings and Close buttons; it appears on mouse-over and hides in edit mode.

#### `_HoverControls`

A slim `Tool` window pinned to the right of the element band. In rest state it shows only a 5 px strip; on hover it reveals a ⚙ Settings button and a ✕ Close button.

#### `_GridOverlay`

A `QQuickPaintedItem` (`z = −1`) that fills the screen during Edit Layout mode. Paints a subtle 8 px snap grid: minor lines at alpha 18, major lines (every 5 cells) at alpha 42.

#### `ElementsPanel`

A frameless, always-on-top `QDialog` (`settings_panel.py`) opened automatically during Edit Layout mode. Centred on screen, draggable by its header. Contains visibility toggles, style dropdowns, and colour swatches - all changes apply live. Footer **Apply** button writes the layout to disk and exits edit mode; **Cancel** restores the pre-edit snapshot without writing.

#### Flash Hysteresis

`_flash_active` boolean in `OverlayWindow` controls the shift-flash state:

- **Enter flash** when `ratio >= shift_ratio`
- **Exit flash** only when `ratio < shift_ratio × 0.94`

The 6% hysteresis prevents zone colours from bleeding through between rev-limiter cuts (ECU RPM bounce).

#### Gear Label Mapping

| Condition              | Label |
|------------------------|-------|
| `not connected`        | `–`   |
| `display_gear == 0`    | `R`   |
| `is_electric`          | `D`   |
| `clutch held`          | `C`   |
| Otherwise              | gear number |

---

### `elements/base.py`

`BaseElement(QQuickPaintedItem)` - shared base for all elements.

**Edit-mode overlay** - coloured tinted background + border + key label + resize-grip triangle, colour-coded per element type.

**Drag/resize** - `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent`. Position and size written to `config` only when geometry changes (`_dirty` flag). `ungrabMouse()` only called when a grab was actually initiated.

**Style context menu** - right-click in edit mode opens a `QMenu` showing all valid styles for the element. Selecting one writes the new style to `config` and calls `save_config` immediately.

**Shared helpers:**

- `_glow(painter, cx, cy, radius, color, alpha)` - radial gradient glow ellipse
- `_annular_arc(cx, cy, r_out, r_in, start_deg, sweep_deg)` - returns a `QPainterPath` for a donut arc segment; angles follow QPainter convention (0° = 3 o'clock, positive = CCW, negative = CW)

**Degenerate-size guard** - `paint()` returns immediately when `width() < 4` or `height() < 4` to prevent font calculations on zero-size elements during construction.

---

### `settings_panel.py`

Two non-blocking `QDialog` classes manage the overlay settings.

**`SettingsPanel`** - opened via the ⚙ hover button:

| Section            | Controls                                                                        |
|--------------------|---------------------------------------------------------------------------------|
| Layout             | **Edit Layout** button - closes settings and activates drag/resize mode         |
| Transmission       | Radio buttons: Automatic / Manual / Manual w/ Clutch                            |
| Controller buttons | Re-capture buttons for Shift Up / Down / Clutch / Hide overlay                  |
| Calibration        | Reset all learned RPM redlines                                                  |
| Restore defaults   | Resets all colours, visibility, styles, and layout to factory defaults           |
| Advanced           | Shift ratio slider (80%–98%); UDP port field; Restart Now button                |

**`ElementsPanel`** - opened automatically when Edit Layout mode is active:

| Section    | Controls                                                                             |
|------------|--------------------------------------------------------------------------------------|
| Visibility | Toggle switches for each of the 6 elements; Reverse toggles for brake/throttle      |
| Styles     | Six `QComboBox` dropdowns - one per element type; changes apply live                |
| Colours    | Colour swatches opening a custom HSV colour picker; changes apply live              |

**Custom colour picker** (`_ColourPicker`) - frameless dark-themed dialog with:
- HSV saturation/value square
- Vertical hue bar
- Hex input field
- 12 preset swatches
- Cancel / Apply buttons

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
shift_ratio = 0.93
show_rev_lights = true
show_gear = true
show_shift_indicators = true
show_brake_bar = true
show_throttle_bar = true
show_brake_label = false
show_throttle_label = false
brake_bar_reversed = false
throttle_bar_reversed = false

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

[styles]
rpm = dot_row
brake = horiz_bar
throttle = horiz_bar
gear = box
shift_up = triangle
shift_dn = triangle

[layout]
rpm_x = 660
rpm_y = 20
rpm_w = 500
rpm_h = 56
brake_x = 540
brake_y = 24
brake_w = 110
brake_h = 40
throttle_x = 1170
throttle_y = 24
throttle_w = 110
throttle_h = 40
gear_x = 890
gear_y = 68
gear_w = 60
gear_h = 60
shift_up_x = 890
shift_up_y = -4
shift_up_w = 60
shift_up_h = 32
shift_dn_x = 890
shift_dn_y = 136
shift_dn_w = 60
shift_dn_h = 32
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

Output: `dist/FH6RPMOverlay2.0.0.exe` - single-file, no Python installation required. The spec uses `console=False` and bundles all PyQt6 dependencies.

---

## Dependencies

| Package | Version | Purpose                      |
|---------|---------|------------------------------|
| PyQt6   | 6.x     | GUI framework, Qt Quick      |
| Python  | 3.13    | Runtime (not needed for exe) |

No third-party packages beyond PyQt6. All other modules (`socket`, `struct`, `ctypes`, `threading`, `configparser`, `json`) are Python stdlib.

---

## Tests

```
pytest tests/
```

| File                       | What it covers                                       |
|----------------------------|------------------------------------------------------|
| `test_config_styles.py`    | Style defaults, round-trip save/load, invalid-style fallback, layout fields, label coverage |
