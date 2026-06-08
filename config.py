import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = "2.0.0"

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = _BASE_DIR / "config.ini"

SCALE_MIN = 0.5
SCALE_MAX = 3.0
_VALID_TRANSMISSIONS = {"automatic", "manual", "manual_clutch"}

# ── Style catalogues ────────────────────────────────────────────────────────
RPM_STYLES      = ("dot_row", "cont_bar", "seg_tiles", "arc_gauge",
                   "f1_split", "shift_light", "spectrum_bars")
BRAKE_STYLES    = ("horiz_bar", "vert_bar", "quarter_arc",
                   "numeric", "radial_fill", "stacked_blocks")
THROTTLE_STYLES = BRAKE_STYLES
GEAR_STYLES     = ("box", "minimal", "mode_tag", "hexagon", "pill", "rpm_color_fill")
SHIFT_STYLES    = ("triangle", "chevrons", "flash_bar",
                   "text_label", "glow_pulse", "pulse_ring")

STYLE_LABELS: dict[str, str] = {
    "dot_row": "Dot Row", "cont_bar": "Continuous Bar",
    "seg_tiles": "Segmented Tiles", "arc_gauge": "Arc Gauge",
    "f1_split": "F1 Split", "shift_light": "Shift Light Only",
    "spectrum_bars": "Spectrum Bars",
    "horiz_bar": "Horizontal Bar", "vert_bar": "Vertical Bar",
    "quarter_arc": "Quarter Arc", "numeric": "Numeric Only",
    "radial_fill": "Radial Fill", "stacked_blocks": "Stacked Blocks",
    "box": "Box", "minimal": "Minimal", "mode_tag": "Gear + Mode Tag",
    "hexagon": "Hexagon", "pill": "Pill Badge",
    "rpm_color_fill": "RPM Color Fill",
    "triangle": "Triangle", "chevrons": "Chevrons",
    "flash_bar": "Flash Bar", "text_label": "Text Label",
    "glow_pulse": "Glow Pulse", "pulse_ring": "Pulse Ring",
}


@dataclass
class Config:
    udp_port:          int   = 20777
    shift_up_button:   int   = 0x2000
    shift_down_button: int   = 0x4000
    clutch_button:     int   = 0
    transmission:      str   = "manual"
    hide_button:       int   = 0
    overlay_x:         int   = -1
    overlay_y:         int   = 10
    overlay_scale:     float = 1.0
    shift_ratio:       float = 0.93

    show_rev_lights:       bool = True
    show_gear:             bool = True
    show_shift_indicators: bool = True
    show_brake_bar:        bool = True
    show_throttle_bar:     bool = True
    show_brake_label:      bool = False
    show_throttle_label:   bool = False
    brake_bar_reversed:    bool = False
    throttle_bar_reversed: bool = False

    colour_rev_zone1:      str = "#22c55e"
    colour_rev_zone2:      str = "#eab308"
    colour_rev_zone3:      str = "#ef4444"
    colour_brake_start:    str = "#991b1b"
    colour_brake_end:      str = "#ef4444"
    colour_throttle_start: str = "#15803d"
    colour_throttle_end:   str = "#22c55e"
    colour_shift_active:   str = "#facc15"
    colour_gear_bg:        str = "#0f172a"
    colour_gear_text:      str = "#e2e8f0"

    # ── Per-element styles ───────────────────────────────────────────────────
    rpm_style:      str = "dot_row"
    brake_style:    str = "horiz_bar"
    throttle_style: str = "horiz_bar"
    gear_style:     str = "box"
    shift_up_style: str = "triangle"
    shift_dn_style: str = "triangle"

    # ── Per-element layout (x/y = -1 means "use screen-relative default") ───
    rpm_x:      int = -1;  rpm_y:      int = -1;  rpm_w:      int = 500; rpm_h:      int = 56
    brake_x:    int = -1;  brake_y:    int = -1;  brake_w:    int = 110; brake_h:    int = 40
    throttle_x: int = -1;  throttle_y: int = -1;  throttle_w: int = 110; throttle_h: int = 40
    gear_x:     int = -1;  gear_y:     int = -1;  gear_w:     int = 60;  gear_h:     int = 60
    shift_up_x: int = -1;  shift_up_y: int = -1;  shift_up_w: int = 60;  shift_up_h: int = 32
    shift_dn_x: int = -1;  shift_dn_y: int = -1;  shift_dn_w: int = 60;  shift_dn_h: int = 32


_DEFAULTS = Config()


def _valid_colour(val: str, default: str) -> str:
    from PyQt6.QtGui import QColor
    return val if QColor(val).isValid() else default


def load_config(path: Path = CONFIG_PATH) -> Config:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")

    def _int(section, key, default):
        try:
            return int(parser.get(section, key))
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def _float(section, key, default):
        try:
            return float(parser.get(section, key))
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def _bool(section, key, default):
        try:
            return parser.get(section, key).strip().lower() in ("true", "1", "yes")
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def _str(section, key, default):
        try:
            return parser.get(section, key).strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    d = _DEFAULTS
    port = _int("network", "udp_port", d.udp_port)
    scale = _float("overlay", "scale", d.overlay_scale)
    sr = _float("overlay", "shift_ratio", d.shift_ratio)
    transmission = _str("general", "transmission", d.transmission)

    return Config(
        udp_port          = port if 1024 <= port <= 65535 else d.udp_port,
        shift_up_button   = _int("buttons", "shift_up",   d.shift_up_button),
        shift_down_button = _int("buttons", "shift_down", d.shift_down_button),
        clutch_button     = _int("buttons", "clutch",     d.clutch_button),
        transmission      = transmission if transmission in _VALID_TRANSMISSIONS else d.transmission,
        hide_button       = _int("buttons", "hide",        d.hide_button),
        overlay_x         = _int("overlay", "x",           d.overlay_x),
        overlay_y         = _int("overlay", "y",           d.overlay_y),
        overlay_scale     = max(SCALE_MIN, min(SCALE_MAX, scale)),
        shift_ratio       = max(0.80, min(0.98, sr)),
        show_rev_lights       = _bool("overlay", "show_rev_lights",       d.show_rev_lights),
        show_gear             = _bool("overlay", "show_gear",             d.show_gear),
        show_shift_indicators = _bool("overlay", "show_shift_indicators", d.show_shift_indicators),
        show_brake_bar        = _bool("overlay", "show_brake_bar",        d.show_brake_bar),
        show_throttle_bar     = _bool("overlay", "show_throttle_bar",     d.show_throttle_bar),
        show_brake_label      = _bool("overlay", "show_brake_label",      d.show_brake_label),
        show_throttle_label   = _bool("overlay", "show_throttle_label",   d.show_throttle_label),
        brake_bar_reversed    = _bool("overlay", "brake_bar_reversed",    d.brake_bar_reversed),
        throttle_bar_reversed = _bool("overlay", "throttle_bar_reversed", d.throttle_bar_reversed),
        colour_rev_zone1      = _valid_colour(_str("colours", "rev_zone1",      d.colour_rev_zone1),      d.colour_rev_zone1),
        colour_rev_zone2      = _valid_colour(_str("colours", "rev_zone2",      d.colour_rev_zone2),      d.colour_rev_zone2),
        colour_rev_zone3      = _valid_colour(_str("colours", "rev_zone3",      d.colour_rev_zone3),      d.colour_rev_zone3),
        colour_brake_start    = _valid_colour(_str("colours", "brake_start",    d.colour_brake_start),    d.colour_brake_start),
        colour_brake_end      = _valid_colour(_str("colours", "brake_end",      d.colour_brake_end),      d.colour_brake_end),
        colour_throttle_start = _valid_colour(_str("colours", "throttle_start", d.colour_throttle_start), d.colour_throttle_start),
        colour_throttle_end   = _valid_colour(_str("colours", "throttle_end",   d.colour_throttle_end),   d.colour_throttle_end),
        colour_shift_active   = _valid_colour(_str("colours", "shift_active",   d.colour_shift_active),   d.colour_shift_active),
        colour_gear_bg        = _valid_colour(_str("colours", "gear_bg",        d.colour_gear_bg),        d.colour_gear_bg),
        colour_gear_text      = _valid_colour(_str("colours", "gear_text",      d.colour_gear_text),      d.colour_gear_text),
        rpm_style      = (lambda v: v if v in RPM_STYLES      else d.rpm_style     )(_str("styles", "rpm",      d.rpm_style)),
        brake_style    = (lambda v: v if v in BRAKE_STYLES    else d.brake_style   )(_str("styles", "brake",    d.brake_style)),
        throttle_style = (lambda v: v if v in THROTTLE_STYLES else d.throttle_style)(_str("styles", "throttle", d.throttle_style)),
        gear_style     = (lambda v: v if v in GEAR_STYLES     else d.gear_style    )(_str("styles", "gear",     d.gear_style)),
        shift_up_style = (lambda v: v if v in SHIFT_STYLES    else d.shift_up_style)(_str("styles", "shift_up", d.shift_up_style)),
        shift_dn_style = (lambda v: v if v in SHIFT_STYLES    else d.shift_dn_style)(_str("styles", "shift_dn", d.shift_dn_style)),
        rpm_x      = _int("layout", "rpm_x",      d.rpm_x),
        rpm_y      = _int("layout", "rpm_y",      d.rpm_y),
        rpm_w      = max(40, _int("layout", "rpm_w",  d.rpm_w)),
        rpm_h      = max(20, _int("layout", "rpm_h",  d.rpm_h)),
        brake_x    = _int("layout", "brake_x",    d.brake_x),
        brake_y    = _int("layout", "brake_y",    d.brake_y),
        brake_w    = max(40, _int("layout", "brake_w",  d.brake_w)),
        brake_h    = max(20, _int("layout", "brake_h",  d.brake_h)),
        throttle_x = _int("layout", "throttle_x", d.throttle_x),
        throttle_y = _int("layout", "throttle_y", d.throttle_y),
        throttle_w = max(40, _int("layout", "throttle_w", d.throttle_w)),
        throttle_h = max(20, _int("layout", "throttle_h", d.throttle_h)),
        gear_x     = _int("layout", "gear_x",     d.gear_x),
        gear_y     = _int("layout", "gear_y",     d.gear_y),
        gear_w     = max(30, _int("layout", "gear_w",  d.gear_w)),
        gear_h     = max(20, _int("layout", "gear_h",  d.gear_h)),
        shift_up_x = _int("layout", "shift_up_x", d.shift_up_x),
        shift_up_y = _int("layout", "shift_up_y", d.shift_up_y),
        shift_up_w = max(30, _int("layout", "shift_up_w", d.shift_up_w)),
        shift_up_h = max(14, _int("layout", "shift_up_h", d.shift_up_h)),
        shift_dn_x = _int("layout", "shift_dn_x", d.shift_dn_x),
        shift_dn_y = _int("layout", "shift_dn_y", d.shift_dn_y),
        shift_dn_w = max(30, _int("layout", "shift_dn_w", d.shift_dn_w)),
        shift_dn_h = max(14, _int("layout", "shift_dn_h", d.shift_dn_h)),
    )


def save_config(path: Path, config: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = config
    content = (
        "# FH6 Overlay configuration\n"
        "# Delete this file to re-run the button setup wizard\n"
        "\n"
        "[general]\n"
        f"transmission = {c.transmission}\n"
        "\n"
        "[network]\n"
        f"udp_port = {c.udp_port}\n"
        "\n"
        "[buttons]\n"
        f"shift_up = {c.shift_up_button}\n"
        f"shift_down = {c.shift_down_button}\n"
        f"clutch = {c.clutch_button}\n"
        f"hide = {c.hide_button}\n"
        "\n"
        "[overlay]\n"
        f"x = {c.overlay_x}\n"
        f"y = {c.overlay_y}\n"
        f"scale = {c.overlay_scale}\n"
        f"shift_ratio = {c.shift_ratio}\n"
        f"show_rev_lights = {str(c.show_rev_lights).lower()}\n"
        f"show_gear = {str(c.show_gear).lower()}\n"
        f"show_shift_indicators = {str(c.show_shift_indicators).lower()}\n"
        f"show_brake_bar = {str(c.show_brake_bar).lower()}\n"
        f"show_throttle_bar = {str(c.show_throttle_bar).lower()}\n"
        f"show_brake_label = {str(c.show_brake_label).lower()}\n"
        f"show_throttle_label = {str(c.show_throttle_label).lower()}\n"
        f"brake_bar_reversed = {str(c.brake_bar_reversed).lower()}\n"
        f"throttle_bar_reversed = {str(c.throttle_bar_reversed).lower()}\n"
        "\n"
        "[colours]\n"
        f"rev_zone1 = {c.colour_rev_zone1}\n"
        f"rev_zone2 = {c.colour_rev_zone2}\n"
        f"rev_zone3 = {c.colour_rev_zone3}\n"
        f"brake_start = {c.colour_brake_start}\n"
        f"brake_end = {c.colour_brake_end}\n"
        f"throttle_start = {c.colour_throttle_start}\n"
        f"throttle_end = {c.colour_throttle_end}\n"
        f"shift_active = {c.colour_shift_active}\n"
        f"gear_bg = {c.colour_gear_bg}\n"
        f"gear_text = {c.colour_gear_text}\n"
        "\n"
        "[styles]\n"
        f"rpm = {c.rpm_style}\n"
        f"brake = {c.brake_style}\n"
        f"throttle = {c.throttle_style}\n"
        f"gear = {c.gear_style}\n"
        f"shift_up = {c.shift_up_style}\n"
        f"shift_dn = {c.shift_dn_style}\n"
        "\n"
        "[layout]\n"
        f"rpm_x = {c.rpm_x}\nrpm_y = {c.rpm_y}\nrpm_w = {c.rpm_w}\nrpm_h = {c.rpm_h}\n"
        f"brake_x = {c.brake_x}\nbrake_y = {c.brake_y}\nbrake_w = {c.brake_w}\nbrake_h = {c.brake_h}\n"
        f"throttle_x = {c.throttle_x}\nthrottle_y = {c.throttle_y}\nthrottle_w = {c.throttle_w}\nthrottle_h = {c.throttle_h}\n"
        f"gear_x = {c.gear_x}\ngear_y = {c.gear_y}\ngear_w = {c.gear_w}\ngear_h = {c.gear_h}\n"
        f"shift_up_x = {c.shift_up_x}\nshift_up_y = {c.shift_up_y}\nshift_up_w = {c.shift_up_w}\nshift_up_h = {c.shift_up_h}\n"
        f"shift_dn_x = {c.shift_dn_x}\nshift_dn_y = {c.shift_dn_y}\nshift_dn_w = {c.shift_dn_w}\nshift_dn_h = {c.shift_dn_h}\n"
    )
    # Atomic write: write to .tmp then rename
    # path.with_suffix(".ini.tmp") raises ValueError on Python 3.12+ for compound suffixes
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
