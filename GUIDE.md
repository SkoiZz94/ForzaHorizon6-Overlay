# Forza Horizon 6 RPM Overlay - Getting Started

A real-time rev lights and controller display for Forza Horizon 6, shown as a transparent overlay on top of your game.

---

> **This overlay is safe to use and is not bannable.**
>
> FH6 Overlay does not modify, patch, or interact with any game files, game memory, or game processes. It is a completely separate application that reads telemetry data that **Forza itself broadcasts** over your local network via the official built-in Data Out feature. Every major racing game that supports Data Out (Forza, F1, Gran Turismo, iRacing) is designed for exactly this kind of external tool. Nothing here gives you an in-game advantage - it only shows information the game is already sending to you.

> **The exe is clean - no viruses, no malware, no telemetry.**
>
> `FH6Overlay.exe` is a Python script compiled into a standalone executable using [PyInstaller](https://pyinstaller.org). Because PyInstaller bundles a Python runtime inside the exe, some antivirus software (including Windows Defender) may flag it as suspicious - this is a well-documented false positive that affects virtually all PyInstaller-built apps. **Every single line of source code is publicly available in this repository.** You can read it, audit it, and verify exactly what the program does before running it. If you still prefer not to trust the pre-built exe, you can build it yourself: install Python 3.13 and PyInstaller, clone this repo, and run `python -m PyInstaller FH6Overlay.spec`.

---

## What You'll See

The overlay displays up to six independent elements, each fully repositionable and available in multiple visual styles:

- **RPM indicator** - fills green → yellow → red as you approach the redline, then flashes when it's time to shift. Seven styles: Dot Row, Continuous Bar, Segmented Tiles, Arc Gauge, F1 Split, Shift Light Only, Spectrum Bars.
- **Brake bar** - shows how hard you're pressing the left trigger. Six styles: Horizontal Bar, Vertical Bar, Quarter Arc, Numeric Only, Radial Fill, Stacked Blocks.
- **Throttle bar** - shows how hard you're pressing the right trigger. Same six styles as Brake.
- **Gear indicator** - your current gear, `R` for reverse, `D` for electric cars, `C` (yellow) while the clutch button is held. Six styles: Box, Minimal, Gear + Mode Tag, Hexagon, Pill Badge, RPM Color Fill.
- **Shift Up / Shift Down indicators** - light up when you press the corresponding button, with a brief fade-out after release. Six styles: Triangle, Chevrons, Flash Bar, Text Label, Glow Pulse, Pulse Ring.

---

## Requirements

- Windows 10 or 11
- Forza Horizon 6
- An Xbox controller (or any XInput-compatible gamepad)

---

## Step 1 - Download

Download `FH6RPMOverlay2.0.0.exe` from the [Releases page](../../releases) and put it anywhere on your PC - your Desktop is fine.

> No installation needed. It's a single file.

---

## Step 2 - Configure Forza Horizon 6

The overlay receives data directly from the game over your local network. You need to turn this on in Forza's settings.

1. In FH6, open **Settings**
2. Go to **HUD and Gameplay**
3. Scroll down to **Data Out**
4. Set **Data Out** to **On**
5. Set **Data Out IP Address** to `127.0.0.1`
6. Set **Data Out IP Port** to `20777`

> These settings are saved and will stay on next time you launch the game.

---

## Step 3 - Run the Overlay

Double-click `FH6RPMOverlay2.0.0.exe`.

The first time you run it, a setup wizard will appear:

**Step 1 of 5 - Transmission type**
Choose how you drive: Automatic, Manual, or Manual w/ Clutch. This controls which elements the overlay shows by default.

**Steps 2–3 - Shift buttons**
Press your Shift Up button, then your Shift Down button when prompted. The wizard detects them automatically.

**Step 4 - Clutch button** *(Manual w/ Clutch only)*
Press your clutch button, or click **Skip** if you don't use one.

**Step 5 - Hide button** *(optional)*
Press a button or button combo to use for toggling the overlay on/off during a race. Click **Skip** to disable this.

> Your settings are saved to `config.ini` next to the exe. You only need to do this once. To redo it, delete `config.ini` and restart.

---

## Step 4 - Drive

The overlay will appear on your screen. Launch a race or free-roam session in FH6.

- The RPM element fills up as you rev the engine
- All lights flash when it's time to shift
- The overlay learns your car's real redline over a few upshifts and becomes more accurate the more you drive

> **The overlay sits on top of all windows** - including FH6 in borderless or windowed mode. If you're running FH6 fullscreen exclusive, use borderless windowed mode in the game's display settings.

---

## Moving and Repositioning Elements

Each overlay element can be freely repositioned and resized independently.

### Opening Edit Layout

Click the **⚙** button that appears when you hover over the overlay (right edge of the element band), then click **Edit Layout** in the Settings panel. Or right-click the system tray icon and choose **Edit Layout**.

### In Edit Layout mode

Every element gets a coloured border and a label showing what it is.

| Action | What it does |
|--------|--------------|
| **Left-drag** any element | Move it anywhere on screen |
| **Drag the triangle grip** (bottom-right corner) | Resize the element |
| **Right-click** any element | Open a menu to change its visual style |
| **Apply** button (floating Overlay Appearance panel) | Save all positions and sizes to disk and exit edit mode |
| **Cancel** button (floating Overlay Appearance panel) | Discard all moves/resizes and restore the previous layout |

A floating **Overlay Appearance** panel opens automatically when you enter Edit Layout mode. It contains visibility toggles, style dropdowns, and colour swatches - use these to configure how each element looks while you position it.

> Style changes (right-click menu or Overlay Appearance panel) are saved immediately and independently of Apply/Cancel.

---

## Hover Controls

When you move your mouse over the overlay, a small strip appears to the right of the elements:

| Button | Action |
|--------|--------|
| **⚙** | Opens the Settings panel |
| **✕** | Closes the overlay |

The strip hides itself automatically while Edit Layout mode is active.

---

## Settings Panel

Click the **⚙** hover button to open the settings panel.

### Layout
Click **Edit Layout** to close the settings panel and enter drag/resize mode. The settings panel reopens automatically when you click Apply or Cancel.

### Transmission
Switch between Automatic, Manual, and Manual w/ Clutch. Changing this also updates which overlay elements are shown by default.

### Controller Buttons
Re-capture any button assignment without re-running the full wizard.

### Calibration
Click **Reset calibration** to clear all learned RPM redlines. Useful when the rev lights feel off after a game update or car change.

### Restore Defaults
Resets all colours, visibility, styles, and layout back to factory settings. Controller button assignments and UDP port are preserved.

### Advanced
- **Shift point** - slider to set the RPM fraction that triggers the shift flash (default 93%, range 80%–98%)
- **UDP Port** - change if you moved Forza's Data Out port; requires a restart to take effect
- **Restart Now** - restart the overlay immediately after a port change

---

## Overlay Appearance Panel

This panel opens automatically when you enter Edit Layout mode. It floats in the centre of your screen and can be dragged by its header. All changes here apply live and persist instantly.

### Visibility
Toggle any element on or off individually:
- Rev lights, Gear indicator, Shift Up, Shift Down, Brake bar, Throttle bar
- **Brake % label** / **Throttle % label** - show a percentage readout inside the bar (most styles)
- **Reverse brake bar** / **Reverse throttle bar** - flip the fill direction

### Visual Styles
Six dropdowns - one per element type. Changes apply immediately. You can also change styles in Edit Layout by right-clicking any element.

| Element   | Available styles |
|-----------|-----------------|
| RPM       | Dot Row, Continuous Bar, Segmented Tiles, Arc Gauge, F1 Split, Shift Light Only, Spectrum Bars |
| Brake     | Horizontal Bar, Vertical Bar, Quarter Arc, Numeric Only, Radial Fill, Stacked Blocks |
| Throttle  | (same as Brake) |
| Gear      | Box, Minimal, Gear + Mode Tag, Hexagon, Pill Badge, RPM Color Fill |
| Shift Up  | Triangle, Chevrons, Flash Bar, Text Label, Glow Pulse, Pulse Ring |
| Shift Down| (same as Shift Up) |

### Colours
Click any colour swatch to open the colour picker. Pick a colour using the HSV square, the hue bar, or by typing a hex code directly. 12 preset swatches are available for quick picks.

---

## Hiding the Overlay Mid-Race

If you set a hide button (or combo) during setup, pressing it while in-game will toggle the overlay on and off instantly. You can change or set this button any time in the Settings panel under **Controller Buttons → Hide overlay**.

---

## Quitting

- Click the **✕** hover button on the overlay, or
- Right-click the icon in the **system tray** (bottom-right of your taskbar) and click **Quit**

---

## Troubleshooting

### The overlay appears but the RPM element doesn't respond

- Make sure Forza's **Data Out** settings are saved and you're in an active session with a car (not at the main menu)
- Check the IP address is exactly `127.0.0.1` and the port is `20777`
- Make sure no other app is using UDP port 20777

### The controller bars and gear don't appear / show dashes

- Make sure your controller is connected before launching the overlay
- The gear indicator shows `–` until the game sends data - this is normal at the main menu

### I want to redo the setup wizard

Delete `config.ini` (it's next to `FH6RPMOverlay2.0.0.exe`) and restart the overlay.

### The rev lights flash too early or too late

The overlay starts with a conservative 90% estimate of your redline and learns the real value from driving. After a few upshifts in the same car it will be accurate. To reset all learned values, open Settings and click **Reset calibration**. You can also adjust the shift point slider in Settings → Advanced.

### I want to change button assignments without redoing the wizard

Open Settings (hover ⚙ button) and go to **Controller Buttons**. Click any binding to re-capture it.

### Elements are in the wrong position or wrong size

Open Settings → **Edit Layout**, then drag elements to where you want them. Click **Apply** when done. Or click **Restore Defaults** in Settings to snap everything back to the default layout.

### I accidentally moved an element off-screen

Open Settings → **Restore Defaults** to reset the layout, or open Settings → **Edit Layout** and drag the element back into view.
