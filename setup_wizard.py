import ctypes
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout,
                              QHBoxLayout, QFrame, QRadioButton, QButtonGroup,
                              QWidget, QMessageBox)

from config import Config, save_config
from controller import XINPUT_GAMEPAD, XINPUT_STATE

_STYLESHEET = """
QDialog { background-color: #0a0a0a; color: #f1f1f1; font-family: Consolas; }
QLabel  { color: #f1f1f1; font-family: Consolas; }
QFrame#header { background-color: #dc2626; }
QPushButton {
    background-color: #111; color: #aaa; border: 1px solid #333;
    border-radius: 4px; padding: 6px 16px; font-family: Consolas; font-size: 12px;
}
QPushButton:hover { border-color: #dc2626; color: #fff; }
QPushButton[primary="true"] { background-color: #dc2626; border: none; color: white; }
QRadioButton { color: #e5e5e5; font-family: Consolas; font-size: 12px; spacing: 8px; }
QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px;
    border: 2px solid #444; background: #111; }
QRadioButton::indicator:checked { background: #dc2626; border-color: #dc2626; }
"""

_STEP_LABELS = {
    1: "Press your  SHIFT UP  button",
    2: "Press your  SHIFT DOWN  button",
    3: "Press your  CLUTCH  button",
    4: "Press your  HIDE  button or combo",
}
_STEP_SKIPPABLE = {1: False, 2: False, 3: True, 4: True}


class SetupWizard(QDialog):
    """First-run wizard shown when config.ini does not exist."""

    def __init__(self, config_path: Path):
        super().__init__()
        self._config_path = config_path
        self._captured: dict[str, int | str] = {}
        self._step = 0
        self._step_history: list[int] = []
        self._prev_buttons = 0
        self._xinput = self._load_xinput()
        self._capturing = False

        self.setWindowTitle("Forza Horizon 6 RPM Overlay — Setup")
        self.setFixedSize(420, 230)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self._drag_offset = None
        self.setStyleSheet(_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(objectName="header")
        header.setFixedHeight(36)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("Forza Horizon 6 RPM Overlay")
        title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: white; letter-spacing: 2px;")
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setStyleSheet(
            "QPushButton { background:transparent; color:rgba(255,255,255,0.85);"
            " border:none; font-size:18px; padding:0; }"
        )
        close_btn.clicked.connect(self._on_close)
        hl.addWidget(close_btn)
        root.addWidget(header)
        header.mousePressEvent = self._hdr_press
        header.mouseMoveEvent  = self._hdr_move

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(20, 16, 20, 16)
        root.addWidget(content)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._label.setWordWrap(True)
        self._content_layout.addWidget(self._label)

        self._radio_widget = QWidget()
        radio_layout = QHBoxLayout(self._radio_widget)
        radio_layout.setSpacing(16)
        self._radio_group = QButtonGroup(self)
        for i, label in enumerate(("Automatic", "Manual", "Manual w/ Clutch")):
            rb = QRadioButton(label)
            if i == 1:
                rb.setChecked(True)
            self._radio_group.addButton(rb, i)
            radio_layout.addWidget(rb)
        self._content_layout.addWidget(self._radio_widget)

        self._summary = QLabel()
        self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary.setStyleSheet("color: #aaa; font-size: 11px;")
        self._summary.setWordWrap(True)
        self._content_layout.addWidget(self._summary)
        self._summary.hide()

        btn_row = QHBoxLayout()
        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self._go_back)
        btn_row.addWidget(self._back_btn)
        btn_row.addStretch()
        self._skip_btn = QPushButton("Skip")
        self._skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(self._skip_btn)
        self._next_btn = QPushButton("Next →")
        self._next_btn.setProperty("primary", True)
        self._next_btn.setStyleSheet("background-color: #dc2626; color: white; border: none;")
        self._next_btn.clicked.connect(self._next_transmission)
        btn_row.addWidget(self._next_btn)
        self._content_layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        self._show_transmission_step()

    def _on_close(self):
        # F5: write defaults on rejection so main() has a valid config
        if not self._config_path.exists():
            save_config(self._config_path, Config())
        self.reject()

    def _hdr_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def _hdr_move(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def _load_xinput(self):
        try:
            return ctypes.windll.xinput1_4
        except OSError:
            return None

    def _current_buttons(self) -> int:
        if not self._xinput:
            return 0
        xi = XINPUT_STATE()
        return xi.Gamepad.wButtons if self._xinput.XInputGetState(0, ctypes.byref(xi)) == 0 else 0

    def _total_steps(self) -> int:
        transmission = self._captured.get("transmission", "manual")
        if transmission == "automatic":
            return 2   # transmission + hide
        elif transmission == "manual":
            return 4   # transmission + shift_up + shift_down + hide
        else:
            return 5   # transmission + shift_up + shift_down + clutch + hide

    def _step_number(self) -> int:
        return len(self._step_history) + 1

    def _show_transmission_step(self):
        self._label.setText("Choose your transmission type")
        self._radio_widget.setVisible(True)
        self._summary.setVisible(False)
        self._skip_btn.setVisible(False)
        self._back_btn.setVisible(False)
        self._next_btn.setVisible(True)
        self._next_btn.setText("Next →")
        self._capturing = False

    def _next_transmission(self):
        btn_id = self._radio_group.checkedId()
        self._captured["transmission"] = ("automatic", "manual", "manual_clutch")[btn_id]
        self._step_history.append(0)
        self._step = 1
        self._advance()

    def _advance(self):
        if not self._xinput:
            self._finish()
            return
        self._radio_widget.setVisible(False)
        self._summary.setVisible(False)
        self._next_btn.setVisible(False)
        transmission = self._captured.get("transmission", "manual")

        if self._step == 1 and transmission == "automatic":
            self._captured["shift_up_button"] = 0
            self._captured["shift_down_button"] = 0
            self._step = 3

        if self._step == 3 and transmission != "manual_clutch":
            self._captured["clutch_button"] = 0
            self._step = 4

        if self._step == 5:
            self._finish()
            return

        total = self._total_steps()
        displayed_n = self._step_number()
        text = f"({displayed_n}/{total})  {_STEP_LABELS[self._step]}"
        self._label.setText(text)
        self._skip_btn.setVisible(_STEP_SKIPPABLE[self._step])
        self._back_btn.setVisible(True)
        self._prev_buttons = self._current_buttons()
        self._capturing = True
        self._timer.start(16)

    def _go_back(self):
        self._capturing = False
        self._timer.stop()
        if not self._step_history:
            return
        self._step = self._step_history.pop()
        if self._step == 0:
            self._show_transmission_step()
        else:
            self._advance()

    def _poll(self):
        if not self._capturing:
            return
        current = self._current_buttons()
        new_pressed = current & ~self._prev_buttons
        self._prev_buttons = current
        if not new_pressed:
            return

        field_map = {1: "shift_up_button", 2: "shift_down_button",
                     3: "clutch_button", 4: "hide_button"}
        field = field_map[self._step]

        if self._step == 4:
            self._captured[field] = current
        else:
            captured_mask = new_pressed & (-new_pressed)
            # F4: warn if shift down same as shift up
            if self._step == 2:
                if captured_mask == self._captured.get("shift_up_button", 0):
                    self._label.setText(
                        "⚠  Same as Shift Up!\n\nPress a different button."
                    )
                    return
            self._captured[field] = captured_mask

        self._capturing = False
        self._timer.stop()
        self._step_history.append(self._step)
        self._step += 1
        self._advance()

    def _skip(self):
        field_map = {3: "clutch_button", 4: "hide_button"}
        self._captured[field_map[self._step]] = 0
        self._capturing = False
        self._timer.stop()
        self._step_history.append(self._step)
        self._step += 1
        self._advance()

    def _finish(self):
        self._timer.stop()
        d = Config()
        transmission = self._captured.get("transmission", "manual")
        cfg = Config(
            transmission      = transmission,
            shift_up_button   = self._captured.get("shift_up_button",   d.shift_up_button),
            shift_down_button = self._captured.get("shift_down_button", d.shift_down_button),
            clutch_button     = self._captured.get("clutch_button",     0),
            hide_button       = self._captured.get("hide_button",       0),
            show_gear             = transmission != "automatic",
            show_shift_indicators = transmission != "automatic",
        )
        save_config(self._config_path, cfg)

        # U13: completion screen
        self._radio_widget.setVisible(False)
        self._skip_btn.setVisible(False)
        self._back_btn.setVisible(False)
        self._label.setText("Setup complete!")

        su = f"0x{cfg.shift_up_button:04X}" if cfg.shift_up_button else "—"
        sd = f"0x{cfg.shift_down_button:04X}" if cfg.shift_down_button else "—"
        cl = f"0x{cfg.clutch_button:04X}" if cfg.clutch_button else "—"
        hb = f"0x{cfg.hide_button:04X}" if cfg.hide_button else "—"
        summary_lines = [
            f"Transmission: {transmission.replace('_', ' ').title()}",
            f"Shift Up: {su}   Shift Down: {sd}",
        ]
        if transmission == "manual_clutch":
            summary_lines.append(f"Clutch: {cl}")
        summary_lines.append(f"Hide: {hb}")
        self._summary.setText("\n".join(summary_lines))
        self._summary.setVisible(True)

        self._next_btn.setText("Launch Overlay")
        self._next_btn.setVisible(True)
        self._next_btn.clicked.disconnect()
        self._next_btn.clicked.connect(self.accept)
