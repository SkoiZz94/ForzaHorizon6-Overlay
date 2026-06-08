import ctypes
import threading
import time

_POLL_S  = 0.016    # ~60 Hz
_RETRY_S = 1.0      # seconds between reconnect attempts


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
        self.lt_pct:     int  = 0
        self.rt_pct:     int  = 0
        self.shift_up:   bool = False
        self.shift_down: bool = False
        self.clutch:     bool = False
        self.connected:  bool = False
        self.toggle_hide: bool = False  # True for exactly one tick on hide rising edge


def _trigger_pct(raw: int) -> int:
    """Convert XInput trigger byte (0-255) to percentage (0-100)."""
    return round(raw / 255 * 100)


def start_controller_listener(
    state: ControllerState,
    shift_up_button: int,
    shift_down_button: int,
    clutch_button: int,
    hide_button: int = 0,
    controller_index: int = 0,
) -> None:
    """Start XInput polling in a daemon thread. Non-fatal if XInput is unavailable."""
    try:
        xinput = ctypes.windll.xinput1_4
    except OSError:
        print("Warning: xinput1_4.dll not found — controller overlay disabled.")
        return

    def _poll():
        xi_state = XINPUT_STATE()
        prev_hide_active = False
        while True:
            result = xinput.XInputGetState(controller_index, ctypes.byref(xi_state))
            if result == 0:   # ERROR_SUCCESS
                gp = xi_state.Gamepad
                buttons = gp.wButtons
                state.lt_pct     = _trigger_pct(gp.bLeftTrigger)
                state.rt_pct     = _trigger_pct(gp.bRightTrigger)
                state.shift_up   = bool(buttons & shift_up_button)
                state.shift_down = bool(buttons & shift_down_button)
                state.clutch     = bool(buttons & clutch_button) if clutch_button else False
                state.connected  = True

                hide_active = hide_button != 0 and (buttons & hide_button) == hide_button
                if hide_active and not prev_hide_active:
                    state.toggle_hide = True
                # toggle_hide is NOT cleared here; _tick in overlay.py consumes and clears it
                prev_hide_active = hide_active

                time.sleep(_POLL_S)
            else:
                state.connected   = False
                prev_hide_active  = False
                time.sleep(_RETRY_S)

    t = threading.Thread(target=_poll, daemon=True, name="XInputPoller")
    t.start()
