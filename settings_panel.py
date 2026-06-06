# settings_panel.py
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QFont, QColor, QDesktopServices, QPixmap,
                         QPainter, QPen, QLinearGradient, QBrush)
from PyQt6.QtWidgets import (
    QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame, QWidget, QLineEdit, QButtonGroup, QRadioButton,
    QScrollArea,
)

from config import Config, save_config


def _res(relative: str) -> str:
    """Resolve a bundled resource path (works both frozen and from source)."""
    import sys, os
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


_PRESETS = [
    "#ef4444", "#f97316", "#facc15", "#22c55e",
    "#06b6d4", "#3b82f6", "#a855f7", "#ec4899",
    "#ffffff", "#94a3b8", "#dc2626", "#0f172a",
]


class _SVPicker(QWidget):
    """Saturation/Value square for HSV picking."""
    colour_changed = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0
        self.setFixedSize(180, 180)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._dragging = False

    def set_hue(self, hue: float):
        self._hue = hue
        self.update()

    def set_color(self, color: QColor):
        h, s, v, _ = color.getHsvF()
        self._hue = max(0.0, h)
        self._sat = s
        self._val = v
        self.update()

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue, self._sat, self._val)

    def paintEvent(self, event):
        p = QPainter(self)
        r = self.rect()
        w, h = self.width(), self.height()
        p.fillRect(r, QColor.fromHsvF(self._hue, 1.0, 1.0))
        wg = QLinearGradient(0, 0, w, 0)
        wg.setColorAt(0.0, QColor(255, 255, 255, 255))
        wg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(r, QBrush(wg))
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(0, 0, 0, 0))
        bg.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(r, QBrush(bg))
        cx = int(self._sat * w)
        cy = int((1.0 - self._val) * h)
        p.setPen(QPen(QColor(0, 0, 0), 2))
        p.drawEllipse(cx - 6, cy - 6, 12, 12)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.drawEllipse(cx - 5, cy - 5, 10, 10)

    def _update_from(self, pos):
        self._sat = max(0.0, min(1.0, pos.x() / self.width()))
        self._val = max(0.0, min(1.0, 1.0 - pos.y() / self.height()))
        self.update()
        self.colour_changed.emit(self.color())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from(event.position())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from(event.position())

    def mouseReleaseEvent(self, event):
        self._dragging = False


class _HueBar(QWidget):
    """Vertical hue slider."""
    hue_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self.setFixedSize(18, 180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dragging = False

    def set_hue(self, hue: float):
        self._hue = hue
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, 0, h)
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsvF(i / 6, 1.0, 1.0))
        p.fillRect(self.rect(), QBrush(grad))
        cy = int(self._hue * h)
        p.setPen(QPen(QColor(0, 0, 0), 2))
        p.drawLine(0, cy, w, cy)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawLine(1, cy, w - 1, cy)

    def _update_from(self, pos):
        self._hue = max(0.0, min(1.0, pos.y() / self.height()))
        self.update()
        self.hue_changed.emit(self._hue)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from(event.position())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from(event.position())

    def mouseReleaseEvent(self, event):
        self._dragging = False


_CP_SS = """
QWidget   { background:#1a1a1a; color:#e5e5e5; font-family:Consolas; }
QFrame#cp_header { background:#dc2626; }
QLineEdit {
    background:#111; border:1px solid #333; border-radius:4px;
    color:#22c55e; font-family:Consolas; font-size:13px; padding:4px 10px;
}
QLineEdit:focus { border-color:#dc2626; }
QPushButton {
    background:#111; border:1px solid #333; border-radius:4px;
    color:#888; font-family:Consolas; font-size:12px; padding:5px 14px;
}
QPushButton:hover { border-color:#dc2626; color:#fff; }
"""


class _ColourPicker(QDialog):
    """Custom dark-themed HSV colour picker."""

    def __init__(self, initial: QColor, title: str, parent=None):
        super().__init__(parent)
        self._colour = QColor(initial)
        self._drag_offset = None

        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(_CP_SS)
        self.setFixedWidth(300)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header (draggable) ────────────────────────────────────────────────
        self._header = QFrame(objectName="cp_header")
        self._header.setFixedHeight(36)
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel(title)
        lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        lbl.setStyleSheet("color:white; background:transparent;")
        hl.addWidget(lbl)
        hl.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(24, 24)
        x_btn.setStyleSheet(
            "background:transparent; border:none; color:rgba(255,255,255,0.7); font-size:13px;"
        )
        x_btn.clicked.connect(self.reject)
        hl.addWidget(x_btn)
        root.addWidget(self._header)
        self._header.mousePressEvent = self._hdr_press
        self._header.mouseMoveEvent  = self._hdr_move

        # ── Body ──────────────────────────────────────────────────────────────
        body = QVBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(10)
        root.addLayout(body)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        self._sv = _SVPicker()
        pick_row.addWidget(self._sv)
        self._hue_bar = _HueBar()
        pick_row.addWidget(self._hue_bar)
        body.addLayout(pick_row)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(8)
        hex_lbl = QLabel("HEX")
        hex_lbl.setFixedWidth(32)
        hex_lbl.setStyleSheet("color:#555; font-size:11px;")
        hex_row.addWidget(hex_lbl)
        self._hex = QLineEdit()
        self._hex.setFixedWidth(90)
        hex_row.addWidget(self._hex)
        self._preview = QFrame()
        self._preview.setFixedSize(32, 26)
        hex_row.addWidget(self._preview)
        hex_row.addStretch()
        body.addLayout(hex_row)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background:#2a2a2a;")
        body.addWidget(div)

        pre_lbl = QLabel("PRESETS")
        pre_lbl.setStyleSheet("color:#444; font-size:10px; letter-spacing:1px;")
        body.addWidget(pre_lbl)

        pre_row = QHBoxLayout()
        pre_row.setSpacing(5)
        for hex_c in _PRESETS:
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setStyleSheet(
                f"background:{hex_c}; border-radius:3px;"
                "border:1px solid rgba(255,255,255,0.1); padding:0;"
            )
            b.clicked.connect(lambda _, c=hex_c: self._set_colour(QColor(c)))
            pre_row.addWidget(b)
        pre_row.addStretch()
        body.addLayout(pre_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("OK — Apply")
        ok.setStyleSheet(
            "background:#dc2626; border:none; color:white;"
            "font-family:Consolas; font-size:12px; padding:5px 14px; border-radius:4px;"
        )
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        body.addLayout(btn_row)

        self._sv.colour_changed.connect(self._on_sv_changed)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        self._hex.editingFinished.connect(self._on_hex_edited)

        self._set_colour(initial)

    # ── drag support ──────────────────────────────────────────────────────────

    def _hdr_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            from PyQt6.QtCore import QPointF
            self._drag_offset = event.globalPosition() - QPointF(self.pos())

    def _hdr_move(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move((event.globalPosition() - self._drag_offset).toPoint())

    # ── colour sync ───────────────────────────────────────────────────────────

    def _set_colour(self, colour: QColor):
        self._colour = QColor(colour)
        h, s, v, _ = colour.getHsvF()
        if h < 0:
            h = 0.0
        self._hue_bar.set_hue(h)
        self._sv.set_hue(h)
        self._sv.set_color(colour)
        self._hex.setText(colour.name())
        self._preview.setStyleSheet(
            f"background:{colour.name()}; border-radius:4px; border:1px solid #333;"
        )

    def _on_sv_changed(self, colour: QColor):
        self._colour = colour
        self._hex.setText(colour.name())
        self._preview.setStyleSheet(
            f"background:{colour.name()}; border-radius:4px; border:1px solid #333;"
        )

    def _on_hue_changed(self, hue: float):
        self._sv.set_hue(hue)
        colour = self._sv.color()
        self._colour = colour
        self._hex.setText(colour.name())
        self._preview.setStyleSheet(
            f"background:{colour.name()}; border-radius:4px; border:1px solid #333;"
        )

    def _on_hex_edited(self):
        text = self._hex.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        c = QColor(text)
        if c.isValid():
            self._set_colour(c)

    def selected_color(self) -> QColor:
        return self._colour


class _ScrollArea(QScrollArea):
    """QScrollArea that pins its widget width exactly to the viewport width."""
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.widget() is not None:
            self.widget().setFixedWidth(self.viewport().width())

_SS = """
QDialog   { background-color: #0a0a0a; color: #f1f1f1; font-family: Consolas; }
QWidget   { background-color: #0a0a0a; color: #f1f1f1; }
QScrollArea { border: none; }
QLabel    { color: #f1f1f1; font-family: Consolas; font-size: 12px; }
QFrame#header { background-color: #dc2626; }
QFrame#divider { background-color: #1a1a1a; }
QPushButton {
    background-color: #111; color: #aaa; border: 1px solid #2a2a2a;
    border-radius: 4px; padding: 4px 12px;
    font-family: Consolas; font-size: 12px;
}
QPushButton:hover { border-color: #dc2626; color: #fff; }
QPushButton[primary="true"] { background-color: #dc2626; border: none; color: white; }
QLineEdit {
    background: #111; color: #aaa; border: 1px solid #2a2a2a;
    border-radius: 4px; padding: 3px 8px; font-family: Consolas; font-size: 12px;
}
QLineEdit:focus { border-color: #dc2626; color: #fff; }
QRadioButton { color: #e5e5e5; font-family: Consolas; font-size: 12px; spacing: 8px; }
QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px;
    border: 2px solid #444; background: #111; }
QRadioButton::indicator:checked { background: #dc2626; border-color: #dc2626; }
"""

_TOGGLE_ON  = "background:#dc2626; border-radius:8px; min-width:32px; max-width:32px; min-height:16px; max-height:16px; color:white; font-size:10px;"
_TOGGLE_OFF = "background:#222; border:1px solid #333; border-radius:8px; min-width:32px; max-width:32px; min-height:16px; max-height:16px; color:#555; font-size:10px;"


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
    lbl.setStyleSheet("color: #dc2626; letter-spacing: 2px; padding-bottom: 4px;")
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background-color: #1a1a1a;")
    return f


class _Toggle(QPushButton):
    """Toggle button that flips a boolean on Config and saves."""

    def __init__(self, config: Config, attr: str, on_change):
        super().__init__()
        self._config = config
        self._attr = attr
        self._on_change = on_change
        self._refresh()
        self.clicked.connect(self._toggle)

    def _refresh(self):
        on = getattr(self._config, self._attr)
        self.setStyleSheet(_TOGGLE_ON if on else _TOGGLE_OFF)
        self.setText("●" if on else "○")

    def _toggle(self):
        setattr(self._config, self._attr, not getattr(self._config, self._attr))
        self._refresh()
        self._on_change()


class _SwatchButton(QPushButton):
    """Colour swatch that opens QColorDialog and writes to config."""

    def __init__(self, config: Config, attr: str, on_change):
        super().__init__()
        self._config = config
        self._attr = attr
        self._on_change = on_change
        self.setFixedSize(28, 20)
        self.setToolTip(attr.replace("colour_", "").replace("_", " "))
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self):
        colour = getattr(self._config, self._attr)
        self.setStyleSheet(
            f"background:{colour}; border:1px solid rgba(255,255,255,0.15); border-radius:4px;"
        )

    def _pick(self):
        initial = QColor(getattr(self._config, self._attr))
        label = self._attr.replace("colour_", "").replace("_", " ").title()
        dlg = _ColourPicker(initial, label, self.window())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            colour = dlg.selected_color()
            if colour.isValid():
                setattr(self._config, self._attr, colour.name())
                self._refresh()
                self._on_change()


class _BindRow(QWidget):
    """One button-binding row with a re-capture button."""

    def __init__(self, label: str, config: Config, attr: str, on_change):
        super().__init__()
        self._config = config
        self._attr = attr
        self._on_change = on_change
        self._capturing = False
        self._prev_buttons = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        lbl = QLabel(label)
        layout.addWidget(lbl)
        layout.addStretch()
        self._btn = QPushButton(self._mask_label())
        self._btn.clicked.connect(self._start_capture)
        layout.addWidget(self._btn)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        try:
            import ctypes
            self._xinput = ctypes.windll.xinput1_4
        except OSError:
            self._xinput = None

    def _mask_label(self) -> str:
        val = getattr(self._config, self._attr)
        return "— disabled —" if val == 0 else f"0x{val:04X}"

    def _current_buttons(self) -> int:
        if not self._xinput:
            return 0
        import ctypes
        from controller import XINPUT_STATE
        xi = XINPUT_STATE()
        return xi.Gamepad.wButtons if self._xinput.XInputGetState(0, ctypes.byref(xi)) == 0 else 0

    def _start_capture(self):
        self._btn.setText("Press button...")
        self._btn.setStyleSheet("border-color: #dc2626; color: #dc2626;")
        self._capturing = True
        self._prev_buttons = self._current_buttons()
        self._timer.start(16)

    def _poll(self):
        if not self._capturing:
            return
        current = self._current_buttons()
        new_pressed = current & ~self._prev_buttons
        if new_pressed:
            setattr(self._config, self._attr, new_pressed & (-new_pressed))
            self._capturing = False
            self._timer.stop()
            self._btn.setStyleSheet("")
            self._btn.setText(self._mask_label())
            self._on_change()


class SettingsPanel(QDialog):

    def __init__(self, config: Config, config_path: Path, tel, overlay):
        super().__init__(overlay)
        self._config = config
        self._config_path = config_path
        self._tel = tel
        self._overlay = overlay

        self.setWindowTitle("Forza Horizon 6 RPM Overlay — Settings")
        self.setFixedWidth(540)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self._drag_offset = None
        self.setStyleSheet(_SS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
        header = QFrame(objectName="header")
        header.setFixedHeight(40)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("Forza Horizon 6 RPM Overlay")
        title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: white; letter-spacing: 2px; background: transparent;")
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setStyleSheet(
            "QPushButton { background:transparent; color:rgba(255,255,255,0.85);"
            " border:none; font-size:18px; padding:0; }"
        )
        close_btn.clicked.connect(self.close)
        hl.addWidget(close_btn)
        root.addWidget(header)
        header.mousePressEvent = self._hdr_press
        header.mouseMoveEvent  = self._hdr_move

        # ── Scrollable body ───────────────────────────────────────────────────
        scroll = _ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body_widget = QWidget()
        self._body = QVBoxLayout(body_widget)
        self._body.setContentsMargins(16, 16, 16, 16)
        self._body.setSpacing(14)
        scroll.setWidget(body_widget)
        root.addWidget(scroll)

        self._build_sections()
        self.resize(540, 640)

    def _apply(self):
        save_config(self._config_path, self._config)
        self._overlay.apply_config()

    def _hdr_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def _hdr_move(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def _build_sections(self):
        self._add_transmission()
        self._body.addWidget(_divider())
        self._add_overlay_elements()
        self._body.addWidget(_divider())
        self._add_colours()
        self._body.addWidget(_divider())
        self._add_controller_buttons()
        self._body.addWidget(_divider())
        self._add_calibration()
        self._body.addWidget(_divider())
        self._add_restore_defaults()
        self._body.addWidget(_divider())
        self._add_network()
        self._body.addWidget(_divider())
        self._add_developer()
        self._body.addStretch()

    def _add_transmission(self):
        self._body.addWidget(_section_label("Transmission"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self._transmission_group = QButtonGroup(self)
        self._transmission_radios: dict[str, QRadioButton] = {}
        options = [("Automatic", "automatic"), ("Manual", "manual"),
                   ("Manual w/ Clutch", "manual_clutch")]
        for label, value in options:
            rb = QRadioButton(label)
            rb.setChecked(self._config.transmission == value)
            rb.toggled.connect(lambda checked, v=value: self._set_transmission(v) if checked else None)
            self._transmission_group.addButton(rb)
            self._transmission_radios[value] = rb
            row.addWidget(rb)
        row.addStretch()
        self._body.addLayout(row)

    def _set_transmission(self, value: str):
        self._config.transmission = value
        auto = value == "automatic"
        self._config.show_gear = not auto
        self._config.show_shift_indicators = not auto
        self._apply()

    def _add_overlay_elements(self):
        self._body.addWidget(_section_label("Overlay elements"))
        self._toggles: list[_Toggle] = []
        toggles = [
            ("Rev lights",         "show_rev_lights"),
            ("Gear indicator",     "show_gear"),
            ("Shift up / down",    "show_shift_indicators"),
            ("Brake bar",          "show_brake_bar"),
            ("Throttle bar",       "show_throttle_bar"),
            ("Brake % label",      "show_brake_label"),
            ("Throttle % label",   "show_throttle_label"),
        ]
        for label, attr in toggles:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            t = _Toggle(self._config, attr, self._apply)
            self._toggles.append(t)
            row.addWidget(t)
            self._body.addLayout(row)

    def _add_colours(self):
        self._body.addWidget(_section_label("Colours"))
        self._swatches: list[_SwatchButton] = []
        colour_rows = [
            ("Rev lights — zones",  ["colour_rev_zone1", "colour_rev_zone2", "colour_rev_zone3"]),
            ("Brake bar",           ["colour_brake_start", "colour_brake_end"]),
            ("Throttle bar",        ["colour_throttle_start", "colour_throttle_end"]),
            ("Shift indicator",     ["colour_shift_active"]),
            ("Gear box",            ["colour_gear_bg", "colour_gear_text"]),
            ("Overlay background",  ["colour_overlay_bg"]),
        ]
        for label, attrs in colour_rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch()
            swatches = QHBoxLayout()
            swatches.setSpacing(4)
            for attr in attrs:
                sw = _SwatchButton(self._config, attr, self._apply)
                self._swatches.append(sw)
                swatches.addWidget(sw)
            row.addLayout(swatches)
            self._body.addLayout(row)

    def _add_controller_buttons(self):
        self._body.addWidget(_section_label("Controller buttons"))
        bindings = [
            ("Shift Up",     "shift_up_button"),
            ("Shift Down",   "shift_down_button"),
            ("Clutch",       "clutch_button"),
            ("Hide overlay", "hide_button"),
        ]
        for label, attr in bindings:
            self._body.addWidget(_BindRow(label, self._config, attr, self._apply))

    def _add_calibration(self):
        self._body.addWidget(_section_label("Calibration"))
        row = QHBoxLayout()
        lbl = QLabel("Clear all learned RPM redlines")
        lbl.setStyleSheet("color: #666;")
        row.addWidget(lbl)
        row.addStretch()
        self._cal_status = QLabel("")
        self._cal_status.setStyleSheet("color: #22c55e; font-size: 11px;")
        row.addWidget(self._cal_status)
        btn = QPushButton("Reset calibration")
        btn.setStyleSheet("border-color: #dc2626; color: #dc2626;")
        btn.clicked.connect(self._reset_calibration)
        row.addWidget(btn)
        self._body.addLayout(row)

    def _reset_calibration(self):
        self._tel.reset_calibration()
        self._cal_status.setText("Reset ✓")
        QTimer.singleShot(3000, lambda: self._cal_status.setText(""))

    def _add_restore_defaults(self):
        self._body.addWidget(_section_label("Restore defaults"))
        row = QHBoxLayout()
        lbl = QLabel("Reset all appearance and position to factory defaults")
        lbl.setStyleSheet("color: #666;")
        row.addWidget(lbl)
        row.addStretch()
        self._restore_status = QLabel("")
        self._restore_status.setStyleSheet("color: #22c55e; font-size: 11px;")
        row.addWidget(self._restore_status)
        btn = QPushButton("Restore defaults")
        btn.setStyleSheet("border-color: #dc2626; color: #dc2626;")
        btn.clicked.connect(self._do_restore_defaults)
        row.addWidget(btn)
        self._body.addLayout(row)

    def _do_restore_defaults(self):
        d = Config()
        c = self._config
        # Reset all colour fields
        for attr in (
            "colour_rev_zone1", "colour_rev_zone2", "colour_rev_zone3",
            "colour_brake_start", "colour_brake_end",
            "colour_throttle_start", "colour_throttle_end",
            "colour_shift_active", "colour_gear_bg", "colour_gear_text",
            "colour_overlay_bg",
        ):
            setattr(c, attr, getattr(d, attr))
        # Reset all visibility toggles
        for attr in (
            "show_rev_lights", "show_gear", "show_shift_indicators",
            "show_brake_bar", "show_throttle_bar",
            "show_brake_label", "show_throttle_label",
        ):
            setattr(c, attr, getattr(d, attr))
        # Reset position, scale, and transmission
        c.overlay_x = d.overlay_x
        c.overlay_y = d.overlay_y
        c.overlay_scale = d.overlay_scale
        c.transmission = d.transmission
        # Sync overlay live scale before apply_config reads _apply_layout
        self._overlay._scale = d.overlay_scale
        self._apply()
        # Refresh dynamic UI widgets to reflect new values
        for t in self._toggles:
            t._refresh()
        for sw in self._swatches:
            sw._refresh()
        for value, rb in self._transmission_radios.items():
            rb.blockSignals(True)
            rb.setChecked(c.transmission == value)
            rb.blockSignals(False)
        self._restore_status.setText("Restored ✓")
        QTimer.singleShot(3000, lambda: self._restore_status.setText(""))

    def _add_network(self):
        self._body.addWidget(_section_label("Network"))
        row = QHBoxLayout()
        row.addWidget(QLabel("UDP Port"))
        row.addStretch()
        self._port_edit = QLineEdit(str(self._config.udp_port))
        self._port_edit.setFixedWidth(80)
        self._port_edit.editingFinished.connect(self._save_port)
        row.addWidget(self._port_edit)
        note = QLabel("(restart required)")
        note.setStyleSheet("color: #555; font-size: 11px;")
        row.addWidget(note)
        self._body.addLayout(row)

    def _save_port(self):
        try:
            self._config.udp_port = int(self._port_edit.text())
            save_config(self._config_path, self._config)
        except ValueError:
            self._port_edit.setText(str(self._config.udp_port))

    def _add_developer(self):
        row = QHBoxLayout()
        row.setSpacing(12)

        logo_lbl = QLabel()
        px = QPixmap(_res("logo/SkoiZzLogo.png"))
        if not px.isNull():
            logo_lbl.setPixmap(px.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        logo_lbl.setFixedSize(44, 44)
        row.addWidget(logo_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("Forza Horizon 6 RPM Overlay")
        title.setStyleSheet("color: #e5e5e5; font-size: 13px;")
        text_col.addWidget(title)

        link_row = QHBoxLayout()
        link_row.setContentsMargins(0, 0, 0, 0)
        dev_label = QLabel("Developed by: ")
        dev_label.setStyleSheet("color: #666; font-size: 12px;")
        link_row.addWidget(dev_label)
        link_btn = QPushButton("SkoiZz")
        link_btn.setStyleSheet(
            "background: transparent; border: none; color: #dc2626;"
            " font-family: Consolas; font-size: 12px; padding: 0; text-decoration: underline;"
        )
        link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/SkoiZz94/ForzaHorizon6-Overlay")))
        link_row.addWidget(link_btn)
        link_row.addStretch()
        text_col.addLayout(link_row)

        row.addLayout(text_col)
        row.addStretch()
        self._body.addLayout(row)
