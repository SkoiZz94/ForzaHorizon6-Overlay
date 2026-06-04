import signal
import sys
from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import (QPainter, QColor, QFont, QLinearGradient, QBrush,
                          QKeySequence, QShortcut, QIcon, QPixmap)

from telemetry import TelemetryState, start_udp_listener, lights_state, COLOR_UNLIT
from telemetry import NUM_LIGHTS, SHIFT_RATIO
from controller import ControllerState, start_controller_listener

UDP_PORT     = 20777
TOP_MARGIN   = 10      # px from top of screen
UPDATE_MS    = 50      # repaint interval (20 fps)

# Rev lights
LIGHT_SIZE   = 44      # px diameter
LIGHT_GAP    = 7       # px between dots
GLOW_PAD     = 16      # extra padding for glow halos

# Controller widget
BAR_W        = 90      # px width of each trigger bar
BAR_H        = 18      # px height of trigger bar
BAR_GAP      = 6       # px between bar and centre column
CENTER_W     = 28      # px width of gear + shift column
SHIFT_H      = 12      # px height of shift button
GEAR_H       = 22      # px height of gear number box
CTR_HEIGHT   = SHIFT_H + 2 + GEAR_H + 2 + SHIFT_H   # = 50 px

# Layout
SECTION_GAP  = 14      # px between rev lights and controller section
DIVIDER_W    = 1       # px width of separator line

SHIFT_FADE_MS = 300    # ms for shift indicators to fade off after release


class TopBarOverlay(QWidget):
    def __init__(self, tel: TelemetryState, ctrl: ControllerState):
        super().__init__()
        self._tel = tel
        self._ctrl = ctrl
        self._flash_on = True
        self._flash_tick = 0
        self._up_fade: float = 0.0
        self._dn_fade: float = 0.0
        self._setup_window()
        self._start_timer()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        rev_w  = NUM_LIGHTS * LIGHT_SIZE + (NUM_LIGHTS - 1) * LIGHT_GAP
        ctrl_w = BAR_W + BAR_GAP + CENTER_W + BAR_GAP + BAR_W
        width  = GLOW_PAD + rev_w + SECTION_GAP + DIVIDER_W + SECTION_GAP + ctrl_w + GLOW_PAD
        height = max(LIGHT_SIZE, CTR_HEIGHT) + 2 * GLOW_PAD
        self.setFixedSize(width, height)

        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        self.move(x, TOP_MARGIN)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        ratio = self._tel.ratio
        cy = self.height() // 2

        # Rev lights — hidden during flash-off phase so the gap is visible
        if not (ratio >= SHIFT_RATIO and not self._flash_on):
            self._draw_rev_lights(painter, GLOW_PAD, cy)

        # Divider and controller section always visible
        rev_w = NUM_LIGHTS * LIGHT_SIZE + (NUM_LIGHTS - 1) * LIGHT_GAP
        div_x = GLOW_PAD + rev_w + SECTION_GAP
        painter.setPen(QColor(51, 65, 85, 100))
        painter.drawLine(div_x, cy - LIGHT_SIZE // 2, div_x, cy + LIGHT_SIZE // 2)
        painter.setPen(Qt.PenStyle.NoPen)

        ctrl_x = div_x + DIVIDER_W + SECTION_GAP
        self._draw_controller(painter, ctrl_x, cy)

        painter.end()

    def _draw_rev_lights(self, painter: QPainter, x: int, cy: int) -> None:
        colors = lights_state(self._tel.ratio, self._tel.connected)
        y = cy - LIGHT_SIZE // 2
        for color_hex in colors:
            self._draw_light(painter, x, y, color_hex)
            x += LIGHT_SIZE + LIGHT_GAP

    def _draw_controller(self, painter: QPainter, x: int, cy: int) -> None:
        c = self._ctrl

        # ── Brake bar (red, fills left → right) ──────────────────────────────
        bk_y = cy - BAR_H // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1e293b"))
        painter.drawRoundedRect(x, bk_y, BAR_W, BAR_H, 4, 4)

        fill_w = max(0, int(BAR_W * c.lt_pct / 100))
        if fill_w:
            grad = QLinearGradient(x, 0, x + BAR_W, 0)
            grad.setColorAt(0.0, QColor("#991b1b"))
            grad.setColorAt(1.0, QColor("#ef4444"))
            painter.save()
            painter.setClipRect(x, bk_y, fill_w, BAR_H)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(x, bk_y, BAR_W, BAR_H, 4, 4)
            painter.restore()

        if c.lt_pct > 0:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
            painter.drawText(QRect(x, bk_y, BAR_W - 3, BAR_H),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{c.lt_pct}%")

        # ── Centre column (shift ▲ / gear / shift ▼) ─────────────────────────
        col_x = x + BAR_W + BAR_GAP
        top_y = cy - CTR_HEIGHT // 2

        # Shift UP button
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._shift_color(self._up_fade))
        painter.drawRoundedRect(col_x, top_y, CENTER_W, SHIFT_H, 2, 2)
        painter.setPen(QColor("#1a1200") if self._up_fade > 0.5 else QColor("#4b5563"))
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.drawText(QRect(col_x, top_y, CENTER_W, SHIFT_H),
                         Qt.AlignmentFlag.AlignCenter, "▲")

        # Gear box
        gear_y = top_y + SHIFT_H + 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0f172a"))
        painter.drawRoundedRect(col_x, gear_y, CENTER_W, GEAR_H, 3, 3)

        if not self._tel.connected:
            gear_label = "–"
        elif self._tel.gear in (0, 11):
            gear_label = "R"
        elif self._tel.is_electric:
            gear_label = "D"
        else:
            gear_label = str(self._tel.gear)

        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        painter.drawText(QRect(col_x, gear_y, CENTER_W, GEAR_H),
                         Qt.AlignmentFlag.AlignCenter, gear_label)

        # Shift DOWN button
        dn_y   = gear_y + GEAR_H + 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._shift_color(self._dn_fade))
        painter.drawRoundedRect(col_x, dn_y, CENTER_W, SHIFT_H, 2, 2)
        painter.setPen(QColor("#1a1200") if self._dn_fade > 0.5 else QColor("#4b5563"))
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.drawText(QRect(col_x, dn_y, CENTER_W, SHIFT_H),
                         Qt.AlignmentFlag.AlignCenter, "▼")

        # ── Throttle bar (green, fills right → left) ─────────────────────────
        th_x = col_x + CENTER_W + BAR_GAP
        th_y = cy - BAR_H // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1e293b"))
        painter.drawRoundedRect(th_x, th_y, BAR_W, BAR_H, 4, 4)

        fill_w = max(0, int(BAR_W * c.rt_pct / 100))
        if fill_w:
            fill_x = th_x + BAR_W - fill_w
            grad = QLinearGradient(fill_x + fill_w, 0, fill_x, 0)
            grad.setColorAt(0.0, QColor("#15803d"))
            grad.setColorAt(1.0, QColor("#22c55e"))
            painter.save()
            painter.setClipRect(fill_x, th_y, fill_w, BAR_H)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(th_x, th_y, BAR_W, BAR_H, 4, 4)
            painter.restore()

        if c.rt_pct > 0:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
            painter.drawText(QRect(th_x + 3, th_y, BAR_W - 3, BAR_H),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{c.rt_pct}%")

    def _draw_light(self, painter: QPainter, x: int, y: int, color_hex: str) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        if color_hex == COLOR_UNLIT:
            painter.setBrush(QColor(color_hex))
            painter.drawEllipse(x, y, LIGHT_SIZE, LIGHT_SIZE)
            return
        c = QColor(color_hex)
        r, g, b = c.red(), c.green(), c.blue()
        # glow halos — outer (faint) to inner (stronger)
        for extra, alpha in ((14, 18), (9, 38), (5, 65)):
            half = extra // 2
            painter.setBrush(QColor(r, g, b, alpha))
            painter.drawEllipse(x - half, y - half, LIGHT_SIZE + extra, LIGHT_SIZE + extra)
        # main light
        painter.setBrush(QColor(color_hex))
        painter.drawEllipse(x, y, LIGHT_SIZE, LIGHT_SIZE)

    def _shift_color(self, fade: float) -> QColor:
        """Interpolate between dark background and shift-yellow based on fade (0–1)."""
        r = int(0x1e + (0xfa - 0x1e) * fade)
        g = int(0x29 + (0xcc - 0x29) * fade)
        b = int(0x3b + (0x15 - 0x3b) * fade)
        return QColor(r, g, b)

    def _start_timer(self):
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(UPDATE_MS)

    def _tick(self):
        self._tel.check_timeout()
        if self._tel.ratio >= SHIFT_RATIO:
            self._flash_tick += 1
            if self._flash_tick >= 3:
                self._flash_on = not self._flash_on
                self._flash_tick = 0
        else:
            self._flash_on = True
            self._flash_tick = 0

        decay = UPDATE_MS / SHIFT_FADE_MS
        self._up_fade = 1.0 if self._ctrl.shift_up else max(0.0, self._up_fade - decay)
        self._dn_fade = 1.0 if self._ctrl.shift_down else max(0.0, self._dn_fade - decay)

        self.update()


def _tray_icon() -> QIcon:
    px = QPixmap(16, 16)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ef4444"))
    p.drawEllipse(1, 1, 14, 14)
    p.end()
    return QIcon(px)


def main():
    tel  = TelemetryState()
    ctrl = ControllerState()

    try:
        start_udp_listener(tel, UDP_PORT)
    except OSError as e:
        print(f"Error: could not bind to port {UDP_PORT}.")
        print(f"Make sure no other instance of the overlay is already running.")
        print(f"Details: {e}")
        sys.exit(1)

    start_controller_listener(ctrl)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep alive when overlay is the only window
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C exits cleanly without traceback

    tray = QSystemTrayIcon(_tray_icon(), parent=app)
    tray.setToolTip("FH6 Overlay")
    menu = QMenu()
    menu.addAction("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.show()

    overlay = TopBarOverlay(tel, ctrl)

    # Quit shortcuts for when running from terminal
    for seq in ("Escape", "Ctrl+Q"):
        QShortcut(QKeySequence(seq), overlay, activated=app.quit)

    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
