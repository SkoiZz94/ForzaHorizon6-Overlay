# config.py  (full replacement)
import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = _BASE_DIR / "config.ini"

_DEFAULTS = None


@dataclass
class Config:
    # ── Existing ──────────────────────────────────────────────────────────────
    udp_port:          int   = 20777
    shift_up_button:   int   = 0x2000
    shift_down_button: int   = 0x4000
    clutch_button:     int   = 0

    # ── Transmission ──────────────────────────────────────────────────────────
    transmission: str = "manual"   # "automatic" | "manual" | "manual_clutch"

    # ── Controller ────────────────────────────────────────────────────────────
    hide_button: int = 0           # XInput bitmask; 0 = disabled

    # ── Overlay position / size ───────────────────────────────────────────────
    overlay_x:     int   = -1      # -1 = auto-centre on first launch
    overlay_y:     int   = 10
    overlay_scale: float = 1.0

    # ── Visibility toggles ────────────────────────────────────────────────────
    show_rev_lights:       bool = True
    show_gear:             bool = True
    show_shift_indicators: bool = True
    show_brake_bar:        bool = True
    show_throttle_bar:     bool = True
    show_brake_label:      bool = False
    show_throttle_label:   bool = False

    # ── Colours ───────────────────────────────────────────────────────────────
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
    colour_overlay_bg:     str = "#0f172a"


_DEFAULTS = Config()


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
    return Config(
        udp_port          = _int("network", "udp_port",   d.udp_port),
        shift_up_button   = _int("buttons", "shift_up",   d.shift_up_button),
        shift_down_button = _int("buttons", "shift_down", d.shift_down_button),
        clutch_button     = _int("buttons", "clutch",     d.clutch_button),
        transmission      = _str("general", "transmission", d.transmission),
        hide_button       = _int("buttons", "hide",        d.hide_button),
        overlay_x         = _int("overlay", "x",           d.overlay_x),
        overlay_y         = _int("overlay", "y",           d.overlay_y),
        overlay_scale     = _float("overlay", "scale",     d.overlay_scale),
        show_rev_lights       = _bool("overlay", "show_rev_lights",       d.show_rev_lights),
        show_gear             = _bool("overlay", "show_gear",             d.show_gear),
        show_shift_indicators = _bool("overlay", "show_shift_indicators", d.show_shift_indicators),
        show_brake_bar        = _bool("overlay", "show_brake_bar",        d.show_brake_bar),
        show_throttle_bar     = _bool("overlay", "show_throttle_bar",     d.show_throttle_bar),
        show_brake_label      = _bool("overlay", "show_brake_label",      d.show_brake_label),
        show_throttle_label   = _bool("overlay", "show_throttle_label",   d.show_throttle_label),
        colour_rev_zone1      = _str("colours", "rev_zone1",      d.colour_rev_zone1),
        colour_rev_zone2      = _str("colours", "rev_zone2",      d.colour_rev_zone2),
        colour_rev_zone3      = _str("colours", "rev_zone3",      d.colour_rev_zone3),
        colour_brake_start    = _str("colours", "brake_start",    d.colour_brake_start),
        colour_brake_end      = _str("colours", "brake_end",      d.colour_brake_end),
        colour_throttle_start = _str("colours", "throttle_start", d.colour_throttle_start),
        colour_throttle_end   = _str("colours", "throttle_end",   d.colour_throttle_end),
        colour_shift_active   = _str("colours", "shift_active",   d.colour_shift_active),
        colour_gear_bg        = _str("colours", "gear_bg",        d.colour_gear_bg),
        colour_gear_text      = _str("colours", "gear_text",      d.colour_gear_text),
        colour_overlay_bg     = _str("colours", "overlay_bg",     d.colour_overlay_bg),
    )


def save_config(path: Path, config: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = config
    path.write_text(
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
        f"show_rev_lights = {str(c.show_rev_lights).lower()}\n"
        f"show_gear = {str(c.show_gear).lower()}\n"
        f"show_shift_indicators = {str(c.show_shift_indicators).lower()}\n"
        f"show_brake_bar = {str(c.show_brake_bar).lower()}\n"
        f"show_throttle_bar = {str(c.show_throttle_bar).lower()}\n"
        f"show_brake_label = {str(c.show_brake_label).lower()}\n"
        f"show_throttle_label = {str(c.show_throttle_label).lower()}\n"
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
        f"overlay_bg = {c.colour_overlay_bg}\n",
        encoding="utf-8",
    )
