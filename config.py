import configparser
import sys
from dataclasses import dataclass
from pathlib import Path

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = _BASE_DIR / "config.ini"

_DEFAULTS = None   # set after class definition


@dataclass
class Config:
    udp_port:          int = 20777
    shift_up_button:   int = 0x2000   # 8192  — B button on Xbox
    shift_down_button: int = 0x4000   # 16384 — X button on Xbox
    clutch_button:     int = 0        # 0 = disabled


_DEFAULTS = Config()


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read config.ini, falling back to defaults for missing or invalid keys."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")

    def _int(section: str, key: str, default: int) -> int:
        try:
            return int(parser.get(section, key))
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    return Config(
        udp_port          = _int("network", "udp_port",   _DEFAULTS.udp_port),
        shift_up_button   = _int("buttons", "shift_up",   _DEFAULTS.shift_up_button),
        shift_down_button = _int("buttons", "shift_down", _DEFAULTS.shift_down_button),
        clutch_button     = _int("buttons", "clutch",     _DEFAULTS.clutch_button),
    )


def save_config(path: Path, config: Config) -> None:
    """Write config.ini with human-readable button cheat-sheet comments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# FH6 Overlay configuration\n"
        "# Delete this file to re-run the button setup wizard\n"
        "#\n"
        "# Common XInput button values:\n"
        "#   A=4096   B=8192   X=16384  Y=32768\n"
        "#   LB=256   RB=512   Back=32  Start=16\n"
        "\n"
        "[network]\n"
        f"udp_port = {config.udp_port}\n"
        "\n"
        "[buttons]\n"
        f"shift_up = {config.shift_up_button}\n"
        f"shift_down = {config.shift_down_button}\n"
        f"clutch = {config.clutch_button}\n",
        encoding="utf-8",
    )
