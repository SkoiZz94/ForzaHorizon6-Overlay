import json
import socket
import struct
import sys
import threading
import time
from pathlib import Path

NUM_LIGHTS   = 9      # 3 green + 3 yellow + 3 red
SHIFT_RATIO  = 0.93   # fraction of effective RPM range that triggers the shift flash

# Adaptive max calibration
_PEAK_ACTIVATE_FRAC = 0.65   # only calibrate once peak > this fraction of reported max
_STABILITY_SECS     = 0.25   # RPM must be stable for this many seconds (plateau fallback)
_STABILITY_TOL      = 0.02   # "stable" = within 2% of peak
_MAX_HEADROOM       = 1.03   # effective_max = observed_peak × this (small buffer above peak)

COLOR_GREEN  = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED    = "#ef4444"
COLOR_FLASH  = "#ff1a1a"  # bright red for shift flash (distinct from static red)
COLOR_UNLIT  = "#1f2937"

_OFFSET_MAX_RPM     = 8
_OFFSET_IDLE_RPM    = 12
_OFFSET_CURRENT_RPM = 16
_OFFSET_GEAR        = 319    # uint8 gear byte (FH6 extended format)
_MIN_PACKET_LEN     = 20     # need bytes 0-19 for RPM
_MIN_EXT_LEN        = 320    # need 320 bytes for gear

# Resolve next to the executable when frozen by PyInstaller, otherwise next to the script
_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
_CAL_FILE = _BASE_DIR / "calibration.json"


def _load_cal_db() -> dict[str, float]:
    try:
        return json.loads(_CAL_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_cal_db(db: dict[str, float]) -> None:
    try:
        _CAL_FILE.write_text(json.dumps(db, indent=2))
    except OSError:
        pass


def _cal_key(max_rpm: float, idle_rpm: float) -> str:
    """Stable string key combining max_rpm and idle_rpm to identify a car."""
    return f"{round(max_rpm)},{round(idle_rpm / 10) * 10}"


def parse_packet(data: bytes) -> tuple[float, float, float, int]:
    """Parse FH6 Car Dash UDP packet. Returns (current_rpm, idle_rpm, max_rpm, gear).

    Gear encoding: 0=reverse, 1-10=forward gears (no neutral in FH6).
    255 (int8 -1) is normalised to 11; both 0 and 11 are treated as reverse by the overlay.
    Packets shorter than 320 bytes return gear=0.
    """
    if len(data) < _MIN_PACKET_LEN:
        raise struct.error(f"Packet too short: {len(data)} bytes, need {_MIN_PACKET_LEN}")
    max_rpm     = struct.unpack_from("<f", data, _OFFSET_MAX_RPM)[0]
    idle_rpm    = struct.unpack_from("<f", data, _OFFSET_IDLE_RPM)[0]
    current_rpm = struct.unpack_from("<f", data, _OFFSET_CURRENT_RPM)[0]
    gear_raw    = struct.unpack_from("<B", data, _OFFSET_GEAR)[0] if len(data) >= _MIN_EXT_LEN else 0
    gear        = 11 if gear_raw == 255 else gear_raw   # normalise int8 −1 encoding to 11
    return current_rpm, idle_rpm, max_rpm, gear


def compute_ratio(current_rpm: float, idle_rpm: float, max_rpm: float) -> float:
    """Return RPM position as a value in [0.0, 1.0] where 0 = idle and 1 = max."""
    rpm_range = max_rpm - idle_rpm
    if rpm_range <= 0:
        return 0.0
    return max(0.0, min(1.0, (current_rpm - idle_rpm) / rpm_range))


class TelemetryState:
    """Shared container written by the UDP thread, read by the GUI thread."""

    def __init__(self, *, cal_db: dict[str, float] | None = None):
        self.ratio: float = 0.0
        self.connected: bool = False
        self.is_electric: bool = False      # True when idle_rpm < 100 (no idle = electric)
        self.packet_has_gear: bool = False  # True when packet was long enough for gear byte
        self.gear: int = 0
        self._last_packet_time: float = 0.0
        self._peak_rpm: float = 0.0
        self._peak_stable_since: float = 0.0
        self._effective_max: float = 0.0   # 0 = not yet calibrated, use reported max
        self._last_max_rpm: float = -1.0   # sentinel: no car seen yet
        self._last_idle_rpm: float = -1.0
        self._cal_db: dict[str, float] = _load_cal_db() if cal_db is None else dict(cal_db)

    def _try_save_calibration(self, key: str, value: float) -> None:
        if value > self._effective_max:
            self._effective_max = value
            self._cal_db[key] = value
            _save_cal_db(self._cal_db)

    def update(self, current_rpm: float, idle_rpm: float, max_rpm: float,
               gear: int = 0, packet_len: int = _MIN_EXT_LEN) -> None:
        now = time.monotonic()

        # Detect electric cars: ICE engines idle at 600-1200 RPM; electric motors don't idle
        self.is_electric = idle_rpm < 100.0
        self.packet_has_gear = packet_len >= _MIN_EXT_LEN

        # Detect car change (max_rpm + idle_rpm are constant per car model)
        if max_rpm != self._last_max_rpm or idle_rpm != self._last_idle_rpm:
            self._last_max_rpm = max_rpm
            self._last_idle_rpm = idle_rpm
            self._peak_rpm = 0.0
            self._peak_stable_since = now
            self.gear = 0   # reset so first gear reading doesn't trigger false upshift
            self._effective_max = (
                0.0 if self.is_electric
                else self._cal_db.get(_cal_key(max_rpm, idle_rpm), 0.0)
            )

        # Detect upshift before updating gear (self.gear is still the previous value)
        upshift = gear > self.gear and self.gear > 0
        self.gear = gear

        if self.is_electric:
            self.ratio = 0.0
        else:
            key = _cal_key(max_rpm, idle_rpm)

            # Track the highest RPM seen
            if current_rpm > self._peak_rpm:
                self._peak_rpm = current_rpm
                self._peak_stable_since = now

            if self._peak_rpm > max_rpm * _PEAK_ACTIVATE_FRAC:
                # Primary: calibrate on every upshift — RPM just before the shift IS the
                # effective redline; no cap at max_rpm so underreported limits are corrected
                if upshift:
                    self._try_save_calibration(key, self._peak_rpm * _MAX_HEADROOM)
                    self._peak_rpm = current_rpm  # reset peak tracking for the new gear

                # Fallback: plateau at high RPM = driver is bouncing off the limiter
                elif (not self._effective_max
                        and now - self._peak_stable_since > _STABILITY_SECS
                        and current_rpm >= self._peak_rpm * (1.0 - _STABILITY_TOL)):
                    self._try_save_calibration(key, self._peak_rpm * _MAX_HEADROOM)

            effective_max = self._effective_max or max_rpm
            self.ratio = compute_ratio(current_rpm, idle_rpm, effective_max)

        self.connected = True
        self._last_packet_time = now

    def check_timeout(self, timeout_seconds: float = 2.0) -> None:
        """Mark as disconnected if no packet received within timeout."""
        if self.connected and time.monotonic() - self._last_packet_time > timeout_seconds:
            self.connected = False
            self._peak_rpm = 0.0
            self._effective_max = 0.0
            self._last_max_rpm = -1.0   # force calibration re-lookup on reconnect
            self._last_idle_rpm = -1.0


def start_udp_listener(state: TelemetryState, port: int) -> None:
    """Bind a UDP socket and start a daemon thread that populates `state`.

    Raises OSError immediately (in the calling thread) if the port is in use.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", port))
    sock.settimeout(1.0)

    def _listen():
        while True:
            try:
                data, _ = sock.recvfrom(1024)
                try:
                    current, idle, max_rpm, gear = parse_packet(data)
                    state.update(current, idle, max_rpm, gear, len(data))
                except struct.error:
                    pass
            except socket.timeout:
                continue

    threading.Thread(target=_listen, daemon=True).start()


def lights_state(ratio: float, connected: bool) -> list[str]:
    """Return NUM_LIGHTS colour hex strings for the current RPM ratio.

    connected=False → all unlit.
    ratio >= SHIFT_RATIO → all flash-red.
    Otherwise → proportional fill: lights 0-2 green, 3-5 yellow, 6-8 red.
    """
    if not connected:
        return [COLOR_UNLIT] * NUM_LIGHTS

    if ratio >= SHIFT_RATIO:
        return [COLOR_FLASH] * NUM_LIGHTS

    result = []
    for i in range(NUM_LIGHTS):
        threshold = (i + 1) * (SHIFT_RATIO / NUM_LIGHTS)
        if ratio >= threshold:
            if i < 3:
                result.append(COLOR_GREEN)
            elif i < 6:
                result.append(COLOR_YELLOW)
            else:
                result.append(COLOR_RED)
        else:
            result.append(COLOR_UNLIT)
    return result
