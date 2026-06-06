import signal
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu
from PyQt6.QtCore import Qt, QTimer, QRect, QPointF
from PyQt6.QtGui import (QPainter, QColor, QFont, QLinearGradient, QBrush,
                          QKeySequence, QShortcut, QIcon, QPixmap)

from telemetry import TelemetryState, start_udp_listener, lights_state, COLOR_UNLIT
from telemetry import NUM_LIGHTS, SHIFT_RATIO, COLOR_GREEN, COLOR_YELLOW, COLOR_RED
from controller import ControllerState, start_controller_listener
from config import Config, save_config, CONFIG_PATH

TOP_MARGIN   = 10
UPDATE_MS    = 50

# Rev lights
LIGHT_SIZE   = 44
LIGHT_GAP    = 7
GLOW_PAD     = 16

# Controller widget
BAR_W        = 90
BAR_H        = 18
BAR_GAP      = 6
CENTER_W     = 28
SHIFT_H      = 12
GEAR_H       = 22
CTR_HEIGHT   = SHIFT_H + 2 + GEAR_H + 2 + SHIFT_H   # = 50

# Layout
SECTION_GAP  = 14
DIVIDER_W    = 1

SHIFT_FADE_MS = 300

# Ghost handles
HANDLE_W       = 22
HANDLE_H       = 22
HANDLE_GAP     = 3
HANDLE_R       = 4
HANDLE_MARGIN  = 6
HANDLE_STRIP_W = HANDLE_MARGIN + HANDLE_W + 4   # 32 logical px added to widget width

SCALE_MIN = 0.5
SCALE_MAX = 3.0


class TopBarOverlay(QWidget):
    def __init__(self, tel: TelemetryState, ctrl: ControllerState,
                 config: Config, config_path: Path):
        super().__init__()
        self._tel = tel
        self._ctrl = ctrl
        self._config = config
        self._config_path = config_path
        self._flash_on = True
        self._flash_tick = 0
        self._up_fade: float = 0.0
        self._dn_fade: float = 0.0
        self._scale: float = config.overlay_scale
        self._handles_visible: bool = False
        self._hovered_handle: str | None = None
        self._drag_mode: str | None = None
        self._drag_offset = None
        self._resize_start_x: float = 0.0
        self._resize_start_scale: float = 1.0
        self._content_w: int = 0
        self._content_h: int = 0
        self._settings_panel = None
        self._setup_window()
        self._start_timer()

    def _ctrl_width(self) -> int:
        cfg = self._config
        has = (cfg.show_brake_bar or cfg.show_gear
               or cfg.show_shift_indicators or cfg.show_throttle_bar)
        if not has:
            return 0
        w = 0
        if cfg.show_brake_bar:
            w += BAR_W + BAR_GAP
        if cfg.show_gear or cfg.show_shift_indicators:
            w += CENTER_W + BAR_GAP
        if cfg.show_throttle_bar:
            w += BAR_W + BAR_GAP
        return max(w - BAR_GAP, 0)

    def _compute_content_size(self) -> tuple[int, int]:
        cfg = self._config
        sections = []
        if cfg.show_rev_lights:
            rev_w = NUM_LIGHTS * LIGHT_SIZE + (NUM_LIGHTS - 1) * LIGHT_GAP
            sections.append(rev_w)
        cw = self._ctrl_width()
        if cw > 0:
            sections.append(cw)
        if len(sections) == 2:
            w = (GLOW_PAD + sections[0] + SECTION_GAP
                 + DIVIDER_W + SECTION_GAP + sections[1] + GLOW_PAD)
        elif len(sections) == 1:
            w = GLOW_PAD + sections[0] + GLOW_PAD
        else:
            w = 2 * GLOW_PAD
        h_candidates = []
        if cfg.show_rev_lights:
            h_candidates.append(LIGHT_SIZE)
        if cw > 0:
            h_candidates.append(CTR_HEIGHT)
        h = (max(h_candidates) if h_candidates else 0) + 2 * GLOW_PAD
        min_handle_h = 4 * HANDLE_H + 3 * HANDLE_GAP + 4
        return w, max(h, 2 * GLOW_PAD, min_handle_h)

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._apply_layout()

    def _apply_layout(self):
        cw, ch = self._compute_content_size()
        self._content_w = cw
        self._content_h = ch
        lw = cw + HANDLE_STRIP_W
        self.setFixedSize(int(lw * self._scale), int(ch * self._scale))
        cfg = self._config
        if cfg.overlay_x == -1:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - int(lw * self._scale)) // 2
            self.move(x, cfg.overlay_y)
        else:
            self.move(cfg.overlay_x, cfg.overlay_y)

    # ── Task 5: ghost handle hit-testing ────────────────────────────────────

    def _handle_at(self, pos) -> str | None:
        s = self._scale
        lx = pos.x() / s
        ly = pos.y() / s
        hx = self._content_w + HANDLE_MARGIN
        if not (hx <= lx <= hx + HANDLE_W):
            return None
        total_h = 4 * HANDLE_H + 3 * HANDLE_GAP
        y0 = (self._content_h - total_h) // 2
        for i, name in enumerate(("move", "resize", "settings", "close")):
            hy = y0 + i * (HANDLE_H + HANDLE_GAP)
            if hy <= ly < hy + HANDLE_H:
                return name
        return None

    def enterEvent(self, event):
        self._handles_visible = True
        self.update()

    def leaveEvent(self, event):
        if self._drag_mode is None:
            self._handles_visible = False
            self._hovered_handle = None
            self.update()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            prev = self._hovered_handle
            self._hovered_handle = self._handle_at(event.position())
            if self._hovered_handle != prev:
                self.update()
        elif self._drag_mode == "move":
            self.move((event.globalPosition() - self._drag_offset).toPoint())
        elif self._drag_mode == "resize":
            delta = event.globalPosition().x() - self._resize_start_x
            new_scale = self._resize_start_scale + delta / 300.0
            new_scale = max(SCALE_MIN, min(SCALE_MAX, new_scale))
            if abs(new_scale - self._scale) > 0.001:
                self._scale = new_scale
                self._apply_layout()

    # ── Task 6: mouse press/release + scale-aware paintEvent ────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        handle = self._handle_at(event.position())
        if handle == "move":
            self._drag_mode = "move"
            self._drag_offset = event.globalPosition() - QPointF(self.pos())
        elif handle == "resize":
            self._drag_mode = "resize"
            self._resize_start_x = event.globalPosition().x()
            self._resize_start_scale = self._scale
        elif handle == "settings":
            self._open_settings()
        elif handle == "close":
            QApplication.instance().quit()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._drag_mode == "move":
            self._config.overlay_x = self.x()
            self._config.overlay_y = self.y()
            save_config(self._config_path, self._config)
        elif self._drag_mode == "resize":
            self._config.overlay_scale = round(self._scale, 3)
            save_config(self._config_path, self._config)
        self._drag_mode = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        s = self._scale
        painter.save()
        painter.scale(s, s)

        cfg = self._config
        cy = self._content_h // 2

        # Rev lights — hidden during flash-off phase
        if not (self._tel.ratio >= SHIFT_RATIO and not self._flash_on):
            if cfg.show_rev_lights:
                self._draw_rev_lights(painter, GLOW_PAD, cy)

        # Divider (only when both sections are visible)
        if cfg.show_rev_lights and self._ctrl_width() > 0:
            rev_w = NUM_LIGHTS * LIGHT_SIZE + (NUM_LIGHTS - 1) * LIGHT_GAP
            div_x = GLOW_PAD + rev_w + SECTION_GAP
            painter.setPen(QColor(51, 65, 85, 100))
            painter.drawLine(div_x, cy - LIGHT_SIZE // 2, div_x, cy + LIGHT_SIZE // 2)
            painter.setPen(Qt.PenStyle.NoPen)
            ctrl_x = div_x + DIVIDER_W + SECTION_GAP
        elif self._ctrl_width() > 0:
            ctrl_x = GLOW_PAD
        else:
            ctrl_x = None

        if ctrl_x is not None:
            self._draw_controller(painter, ctrl_x, cy)

        # Keep handle strip hit-testable: 1-alpha fill so Windows delivers mouse
        # events even when handles aren't drawn (transparent pixels get no events)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 1))
        painter.drawRect(self._content_w, 0, HANDLE_STRIP_W, self._content_h)

        # Handles drawn in logical coords (inside scale transform)
        if self._handles_visible:
            self._draw_handles(painter)

        painter.restore()
        painter.end()

    def _draw_handles(self, painter: QPainter) -> None:
        total_h = 4 * HANDLE_H + 3 * HANDLE_GAP
        y0 = (self._content_h - total_h) // 2
        hx = self._content_w + HANDLE_MARGIN
        icons = ("⣿", "⟺", "⚙", "✕")
        names = ("move", "resize", "settings", "close")
        for i, (icon, name) in enumerate(zip(icons, names)):
            hy = y0 + i * (HANDLE_H + HANDLE_GAP)
            is_hovered = self._hovered_handle == name
            bg = QColor(220, 38, 38, 160) if is_hovered else QColor(51, 65, 85, 140)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(hx, hy, HANDLE_W, HANDLE_H, HANDLE_R, HANDLE_R)
            painter.setPen(QColor(255, 255, 255, 210))
            painter.setFont(QFont("Segoe UI Symbol", 9))
            painter.drawText(
                QRect(hx, hy, HANDLE_W, HANDLE_H),
                Qt.AlignmentFlag.AlignCenter,
                icon,
            )

    def _draw_rev_lights(self, painter: QPainter, x: int, cy: int) -> None:
        cfg = self._config
        colour_map = {
            COLOR_GREEN:  cfg.colour_rev_zone1,
            COLOR_YELLOW: cfg.colour_rev_zone2,
            COLOR_RED:    cfg.colour_rev_zone3,
        }
        colours = lights_state(self._tel.ratio, self._tel.connected)
        y = cy - LIGHT_SIZE // 2
        for c in colours:
            self._draw_light(painter, x, y, colour_map.get(c, c))
            x += LIGHT_SIZE + LIGHT_GAP

    def _draw_controller(self, painter: QPainter, x: int, cy: int) -> None:
        c = self._ctrl
        cfg = self._config

        # ── Brake bar ────────────────────────────────────────────────────────
        if cfg.show_brake_bar:
            bk_y = cy - BAR_H // 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1e293b"))
            painter.drawRoundedRect(x, bk_y, BAR_W, BAR_H, 4, 4)
            fill_w = max(0, int(BAR_W * c.lt_pct / 100))
            if fill_w:
                grad = QLinearGradient(x, 0, x + BAR_W, 0)
                grad.setColorAt(0.0, QColor(cfg.colour_brake_start))
                grad.setColorAt(1.0, QColor(cfg.colour_brake_end))
                painter.save()
                painter.setClipRect(x, bk_y, fill_w, BAR_H)
                painter.setBrush(QBrush(grad))
                painter.drawRoundedRect(x, bk_y, BAR_W, BAR_H, 4, 4)
                painter.restore()
            if cfg.show_brake_label and c.lt_pct > 0:
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                painter.drawText(QRect(x, bk_y, BAR_W - 3, BAR_H),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 f"{c.lt_pct}%")
            x += BAR_W + BAR_GAP

        # ── Centre column ────────────────────────────────────────────────────
        if cfg.show_gear or cfg.show_shift_indicators:
            col_x = x
            top_y = cy - CTR_HEIGHT // 2

            if cfg.show_shift_indicators:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._shift_color(self._up_fade))
                painter.drawRoundedRect(col_x, top_y, CENTER_W, SHIFT_H, 2, 2)
                painter.setPen(QColor("#1a1200") if self._up_fade > 0.5 else QColor("#4b5563"))
                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                painter.drawText(QRect(col_x, top_y, CENTER_W, SHIFT_H),
                                 Qt.AlignmentFlag.AlignCenter, "▲")

            gear_y = top_y + SHIFT_H + 2
            if cfg.show_gear:
                painter.setPen(Qt.PenStyle.NoPen)
                if self._ctrl.clutch:
                    painter.setBrush(self._shift_color(1.0))
                    painter.drawRoundedRect(col_x, gear_y, CENTER_W, GEAR_H, 3, 3)
                    painter.setPen(QColor("#1a1200"))
                    painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
                    painter.drawText(QRect(col_x, gear_y, CENTER_W, GEAR_H),
                                     Qt.AlignmentFlag.AlignCenter, "C")
                else:
                    painter.setBrush(QColor(cfg.colour_gear_bg))
                    painter.drawRoundedRect(col_x, gear_y, CENTER_W, GEAR_H, 3, 3)
                    if not self._tel.connected:
                        gear_label = "–"
                    elif self._tel.display_gear == 0:
                        gear_label = "R"
                    elif self._tel.is_electric:
                        gear_label = "D"
                    else:
                        gear_label = str(self._tel.display_gear)
                    painter.setPen(QColor(cfg.colour_gear_text))
                    painter.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
                    painter.drawText(QRect(col_x, gear_y, CENTER_W, GEAR_H),
                                     Qt.AlignmentFlag.AlignCenter, gear_label)

            if cfg.show_shift_indicators:
                dn_y = gear_y + GEAR_H + 2
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._shift_color(self._dn_fade))
                painter.drawRoundedRect(col_x, dn_y, CENTER_W, SHIFT_H, 2, 2)
                painter.setPen(QColor("#1a1200") if self._dn_fade > 0.5 else QColor("#4b5563"))
                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                painter.drawText(QRect(col_x, dn_y, CENTER_W, SHIFT_H),
                                 Qt.AlignmentFlag.AlignCenter, "▼")

            x += CENTER_W + BAR_GAP

        # ── Throttle bar ─────────────────────────────────────────────────────
        if cfg.show_throttle_bar:
            th_y = cy - BAR_H // 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1e293b"))
            painter.drawRoundedRect(x, th_y, BAR_W, BAR_H, 4, 4)
            fill_w = max(0, int(BAR_W * c.rt_pct / 100))
            if fill_w:
                fill_x = x + BAR_W - fill_w
                grad = QLinearGradient(fill_x + fill_w, 0, fill_x, 0)
                grad.setColorAt(0.0, QColor(cfg.colour_throttle_start))
                grad.setColorAt(1.0, QColor(cfg.colour_throttle_end))
                painter.save()
                painter.setClipRect(fill_x, th_y, fill_w, BAR_H)
                painter.setBrush(QBrush(grad))
                painter.drawRoundedRect(x, th_y, BAR_W, BAR_H, 4, 4)
                painter.restore()
            if cfg.show_throttle_label and c.rt_pct > 0:
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                painter.drawText(QRect(x + 3, th_y, BAR_W - 3, BAR_H),
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
        """Interpolate between dark background and config shift-active colour based on fade (0–1)."""
        active = QColor(self._config.colour_shift_active)
        bg = QColor("#1e293b")
        r = int(bg.red()   + (active.red()   - bg.red())   * fade)
        g = int(bg.green() + (active.green() - bg.green()) * fade)
        b = int(bg.blue()  + (active.blue()  - bg.blue())  * fade)
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

        if self._ctrl.toggle_hide:
            if self.isVisible():
                self.hide()
            else:
                self.show()

        self.update()

    def apply_config(self) -> None:
        self._scale = self._config.overlay_scale
        self._apply_layout()
        self.update()

    def _open_settings(self):
        from settings_panel import SettingsPanel
        if self._settings_panel is None or not self._settings_panel.isVisible():
            self._settings_panel = SettingsPanel(
                self._config, self._config_path, self._tel, self
            )
        self._settings_panel.show()
        self._settings_panel.raise_()


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
    import argparse
    from config import load_config, CONFIG_PATH
    from setup_wizard import SetupWizard

    parser = argparse.ArgumentParser(description='FH6 rev light overlay')
    parser.add_argument('--port', type=int, default=None,
                        help='UDP port override (default: from config.ini)')
    args = parser.parse_args()

    # QApplication must exist before the wizard (both are PyQt6 windows)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if not CONFIG_PATH.exists():
        wizard = SetupWizard(CONFIG_PATH)
        wizard.exec()

    config = load_config(CONFIG_PATH)
    port   = args.port if args.port is not None else config.udp_port

    tel  = TelemetryState()
    ctrl = ControllerState()

    try:
        start_udp_listener(tel, port)
    except OSError as e:
        print(f"Error: could not bind to port {port}.")
        print(f"Make sure no other instance of the overlay is already running.")
        print(f"Details: {e}")
        sys.exit(1)

    start_controller_listener(ctrl, config.shift_up_button,
                              config.shift_down_button, config.clutch_button,
                              config.hide_button)

    tray = QSystemTrayIcon(_tray_icon(), parent=app)
    tray.setToolTip("FH6 Overlay")
    menu = QMenu()
    menu.addAction("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.show()

    overlay = TopBarOverlay(tel, ctrl, config, CONFIG_PATH)

    for seq in ("Escape", "Ctrl+Q"):
        QShortcut(QKeySequence(seq), overlay, activated=app.quit)

    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
