import ctypes
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from config import Config, save_config


class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons",      ctypes.c_ushort),
        ("bLeftTrigger",  ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX",      ctypes.c_short),
        ("sThumbLY",      ctypes.c_short),
        ("sThumbRX",      ctypes.c_short),
        ("sThumbRY",      ctypes.c_short),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad",        _XINPUT_GAMEPAD),
    ]


# (label shown to user, Config field name, skippable)
_STEPS = [
    ("SHIFT UP",   "shift_up_button",   False),
    ("SHIFT DOWN", "shift_down_button", False),
    ("CLUTCH",     "clutch_button",     True),
]


class SetupWizard(QDialog):
    """One-time button assignment dialog shown when config.ini does not exist."""

    def __init__(self, config_path: Path):
        super().__init__()
        self._config_path = config_path
        self._captured: dict[str, int] = {}
        self._step = 0
        self._prev_buttons = 0
        self._xinput = self._load_xinput()

        self.setWindowTitle("FH6 Overlay — Button Setup")
        self.setFixedSize(380, 140)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        layout.addWidget(self._label)

        self._skip_btn = QPushButton("Skip (no clutch)")
        self._skip_btn.clicked.connect(self._skip)
        layout.addWidget(self._skip_btn)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(16)   # ~60 Hz

        self._advance()

    def _load_xinput(self):
        try:
            return ctypes.windll.xinput1_4
        except OSError:
            print("Warning: xinput1_4.dll not found — saving default button config.")
            return None

    def _current_buttons(self) -> int:
        if not self._xinput:
            return 0
        xi = _XINPUT_STATE()
        return xi.Gamepad.wButtons if self._xinput.XInputGetState(0, ctypes.byref(xi)) == 0 else 0

    def _advance(self):
        if not self._xinput or self._step >= len(_STEPS):
            self._finish()
            return
        label, _, skippable = _STEPS[self._step]
        step_n = self._step + 1
        total  = len(_STEPS)
        self._label.setText(f"({step_n}/{total})  Press your  {label}  button")
        self._skip_btn.setVisible(skippable)
        self._prev_buttons = self._current_buttons()

    def _poll(self):
        current = self._current_buttons()
        new_pressed = current & ~self._prev_buttons
        self._prev_buttons = current
        if new_pressed:
            lowest_bit = new_pressed & (-new_pressed)   # isolate one button
            _, field, _ = _STEPS[self._step]
            self._captured[field] = lowest_bit
            self._step += 1
            self._advance()

    def _skip(self):
        _, field, _ = _STEPS[self._step]
        self._captured[field] = 0
        self._step += 1
        self._advance()

    def _finish(self):
        self._timer.stop()
        defaults = Config()
        cfg = Config(
            shift_up_button   = self._captured.get("shift_up_button",   defaults.shift_up_button),
            shift_down_button = self._captured.get("shift_down_button", defaults.shift_down_button),
            clutch_button     = self._captured.get("clutch_button",     0),
        )
        save_config(self._config_path, cfg)
        print(f"Config saved to {self._config_path}")
        self.accept()
