import ctypes
import threading
import time

SHIFT_UP_BTN   = 0x2000   # B button (swap with SHIFT_DOWN_BTN if inverted)
SHIFT_DOWN_BTN = 0x4000   # X button
_POLL_S        = 0.016     # ~60 Hz
_RETRY_S       = 1.0       # seconds between reconnect attempts


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons",      ctypes.c_ushort),
        ("bLeftTrigger",  ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX",      ctypes.c_short),
        ("sThumbLY",      ctypes.c_short),
        ("sThumbRX",      ctypes.c_short),
        ("sThumbRY",      ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad",        XINPUT_GAMEPAD),
    ]


class ControllerState:
    """Shared container written by the XInput thread, read by the GUI thread."""

    def __init__(self):
        self.lt_pct: int = 0          # left trigger (brake) 0-100
        self.rt_pct: int = 0          # right trigger (throttle) 0-100
        self.shift_up: bool = False
        self.shift_down: bool = False
        self.connected: bool = False


def _trigger_pct(raw: int) -> int:
    """Convert XInput trigger byte (0-255) to percentage (0-100)."""
    return round(raw / 255 * 100)


def start_controller_listener(state: ControllerState, controller_index: int = 0) -> None:
    """Start XInput polling in a daemon thread. Non-fatal if XInput is unavailable."""
    try:
        xinput = ctypes.windll.xinput1_4
    except OSError:
        print("Warning: xinput1_4.dll not found — controller overlay disabled.")
        return

    def _poll():
        xi_state = XINPUT_STATE()
        while True:
            result = xinput.XInputGetState(controller_index, ctypes.byref(xi_state))
            if result == 0:   # ERROR_SUCCESS
                gp = xi_state.Gamepad
                state.lt_pct     = _trigger_pct(gp.bLeftTrigger)
                state.rt_pct     = _trigger_pct(gp.bRightTrigger)
                state.shift_up   = bool(gp.wButtons & SHIFT_UP_BTN)
                state.shift_down = bool(gp.wButtons & SHIFT_DOWN_BTN)
                state.connected  = True
                time.sleep(_POLL_S)
            else:
                state.connected = False
                time.sleep(_RETRY_S)

    threading.Thread(target=_poll, daemon=True).start()
