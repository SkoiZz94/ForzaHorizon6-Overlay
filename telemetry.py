import json
import socket
import struct
import threading
import time

from config import _BASE_DIR

NUM_LIGHTS   = 9
SHIFT_RATIO  = 0.93   # kept as fallback; overlay uses config.shift_ratio at runtime

_PEAK_ACTIVATE_FRAC = 0.65
_MAX_HEADROOM       = 1.03
_CAL_MAX_HEADROOM   = 1.08   # hard ceiling: prevents stray packets inflating calibration permanently
_DEFAULT_MAX_FRAC   = 0.90

COLOR_GREEN  = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED    = "#ef4444"
COLOR_FLASH  = "#ff1a1a"
COLOR_UNLIT  = "#1f2937"

_OFFSET_MAX_RPM     = 8
_OFFSET_IDLE_RPM    = 12
_OFFSET_CURRENT_RPM = 16
_OFFSET_GEAR        = 319
_MIN_PACKET_LEN     = 20
_MIN_EXT_LEN        = 320

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
    return f"{round(max_rpm)},{round(idle_rpm / 10) * 10}"


def parse_packet(data: bytes) -> tuple[float, float, float, int]:
    """Parse FH6 Car Dash UDP packet. Returns (current_rpm, idle_rpm, max_rpm, gear)."""
    if len(data) < _MIN_PACKET_LEN:
        raise struct.error(f"Packet too short: {len(data)} bytes")
    max_rpm     = struct.unpack_from("<f", data, _OFFSET_MAX_RPM)[0]
    idle_rpm    = struct.unpack_from("<f", data, _OFFSET_IDLE_RPM)[0]
    current_rpm = struct.unpack_from("<f", data, _OFFSET_CURRENT_RPM)[0]
    gear_raw    = struct.unpack_from("<B", data, _OFFSET_GEAR)[0] if len(data) >= _MIN_EXT_LEN else 0
    gear        = 11 if gear_raw == 255 else gear_raw

    # F3: reject stray UDP packets with garbage RPM values
    if not (0 < max_rpm < 30000):
        raise struct.error(f"Invalid max_rpm: {max_rpm}")
    if not (0 <= idle_rpm < max_rpm):
        raise struct.error(f"Invalid idle_rpm: {idle_rpm}")
    if not (0 <= current_rpm <= max_rpm * 1.1):
        raise struct.error(f"Invalid current_rpm: {current_rpm}")

    return current_rpm, idle_rpm, max_rpm, gear


def compute_ratio(current_rpm: float, idle_rpm: float, max_rpm: float) -> float:
    rpm_range = max_rpm - idle_rpm
    if rpm_range <= 0:
        return 0.0
    return max(0.0, min(1.0, (current_rpm - idle_rpm) / rpm_range))


class TelemetryState:
    """Shared container written by the UDP thread, read by the GUI thread."""

    def __init__(self, *, cal_db: dict[str, float] | None = None):
        self.ratio: float = 0.0
        self.current_rpm: float = 0.0
        self.connected: bool = False
        self.is_electric: bool = False
        self.packet_has_gear: bool = False
        self.gear: int = 0
        self.display_gear: int = 0
        self.calibration_updated: bool = False   # U5: set True when effective_max changes
        self._last_packet_time: float = 0.0
        self._peak_by_gear: dict[int, float] = {}
        self._effective_max: float = 0.0
        self._last_max_rpm: float = -1.0
        self._last_idle_rpm: float = -1.0
        self._cal_db: dict[str, float] = _load_cal_db() if cal_db is None else dict(cal_db)
        self._pending_flush: bool = False
        self._prev_gear: int = 0        # downshift guard
        self._downshift_frames: int = 0 # frames remaining to suppress peak update

    def _update_effective_max(self, key: str, value: float) -> None:
        """Update in-memory calibration. Disk write deferred to flush."""
        if value > self._effective_max:
            self._effective_max = value
            self._cal_db[key] = value
            self._pending_flush = True
            self.calibration_updated = True

    def _flush_calibration(self) -> None:
        if self._pending_flush:
            _save_cal_db(self._cal_db)
            self._pending_flush = False

    def update(self, current_rpm: float, idle_rpm: float, max_rpm: float,
               gear: int = 0, packet_len: int = _MIN_EXT_LEN) -> None:
        now = time.monotonic()

        self.is_electric = idle_rpm < 100.0
        self.packet_has_gear = packet_len >= _MIN_EXT_LEN

        if max_rpm != self._last_max_rpm or idle_rpm != self._last_idle_rpm:
            self._flush_calibration()   # flush on car change
            self._last_max_rpm = max_rpm
            self._last_idle_rpm = idle_rpm
            self._peak_by_gear = {}
            self._prev_gear = 0
            self._downshift_frames = 0
            self.gear = 0
            self.display_gear = 0
            self._effective_max = (
                0.0 if self.is_electric
                else self._cal_db.get(_cal_key(max_rpm, idle_rpm), 0.0)
            )

        self.current_rpm = current_rpm
        self.gear = gear
        if gear != 11:
            self.display_gear = gear

        if self.is_electric:
            self.ratio = 0.0
        else:
            key = _cal_key(max_rpm, idle_rpm)
            _valid_gear = gear not in (0, 11)
            if _valid_gear:
                # Downshift RPM spike: suppress peak tracking to avoid inflating effective_max
                if self._prev_gear > 0 and gear < self._prev_gear:
                    self._downshift_frames = 15   # ~750 ms at 50 Hz
                elif self._downshift_frames > 0:
                    self._downshift_frames -= 1
                self._prev_gear = gear
            if _valid_gear and self._downshift_frames == 0:
                if current_rpm > self._peak_by_gear.get(gear, 0.0):
                    self._peak_by_gear[gear] = current_rpm
                    if current_rpm > max_rpm * _PEAK_ACTIVATE_FRAC:
                        self._update_effective_max(
                            key, min(current_rpm * _MAX_HEADROOM, max_rpm * _CAL_MAX_HEADROOM)
                        )

            effective_max = self._effective_max or (max_rpm * _DEFAULT_MAX_FRAC)
            self.ratio = compute_ratio(current_rpm, idle_rpm, effective_max)

        self.connected = True
        self._last_packet_time = now

    def check_timeout(self, timeout_seconds: float = 2.0) -> None:
        if self.connected and time.monotonic() - self._last_packet_time > timeout_seconds:
            self._flush_calibration()   # flush on timeout
            self.connected = False
            self._peak_by_gear = {}
            self._effective_max = 0.0
            self._last_max_rpm = -1.0
            self._last_idle_rpm = -1.0

    def reset_calibration(self) -> None:
        self._cal_db.clear()
        self._effective_max = 0.0
        self._peak_by_gear = {}
        self._pending_flush = False
        _CAL_FILE.unlink(missing_ok=True)


def start_udp_listener(state: TelemetryState, port: int) -> None:
    """Bind UDP socket and start a daemon thread. Raises OSError if port is in use."""
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

    t = threading.Thread(target=_listen, daemon=True, name="UDPListener")
    t.start()


def lights_state(ratio: float, connected: bool, shift_ratio: float = SHIFT_RATIO) -> list[str]:
    """Return NUM_LIGHTS colour hex strings for the current RPM ratio."""
    if not connected:
        return [COLOR_UNLIT] * NUM_LIGHTS

    if ratio >= shift_ratio:
        return [COLOR_FLASH] * NUM_LIGHTS

    result = []
    for i in range(NUM_LIGHTS):
        threshold = (i + 1) * (shift_ratio / NUM_LIGHTS)
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
