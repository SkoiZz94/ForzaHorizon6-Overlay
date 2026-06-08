import signal
import sys
import time
import traceback
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QMessageBox,
                             QWidget, QPushButton)
from PyQt6.QtQuick   import QQuickWindow, QQuickPaintedItem
from PyQt6.QtCore    import Qt, QSizeF, QPoint, QRectF, QTimer
from PyQt6.QtGui     import (QPainter, QColor, QFont, QIcon, QPixmap, QGuiApplication)

from telemetry  import TelemetryState, start_udp_listener
from controller import ControllerState, start_controller_listener
from config     import Config, save_config, CONFIG_PATH

SHIFT_FADE_MS  = 300
_FLASH_HALF_MS = 80


def _acquire_single_instance() -> bool:
    """Return False if another instance is already running (Windows named mutex)."""
    if sys.platform != "win32":
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Global\\FH6OverlaySingleInstance")
    return kernel32.GetLastError() != 183   # 183 = ERROR_ALREADY_EXISTS


def _install_qt_message_handler() -> None:
    """Intercept Qt warnings.

    Suppresses the QFont::setPointSize <= 0 console spam and instead writes
    a Python traceback to fh6overlay.log so the exact call site can be found.
    All other Qt messages are forwarded to stderr unchanged.
    """
    from PyQt6.QtCore import qInstallMessageHandler, QtMsgType

    log_path = (
        Path(sys.executable).parent / "fh6overlay.log"
        if getattr(sys, "frozen", False)
        else Path(__file__).parent / "fh6overlay.log"
    )

    def _handler(msg_type, context, message):
        if "QFont::setPointSize: Point size <= 0" in message:
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n{'='*60}\n{datetime.datetime.now()} [QFont size warning]\n"
                            f"{message}\n")
                    traceback.print_stack(file=f)
            except Exception:
                pass
            return  # suppress console output
        if "QDxgiVSyncService not destroyed in time" in message:
            return  # cosmetic cleanup-timing warning; render thread races static dtor
        if msg_type in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg,
                        QtMsgType.QtFatalMsg):
            print(message, file=sys.stderr)

    qInstallMessageHandler(_handler)


def _install_exception_handler() -> None:
    log_path = (
        Path(sys.executable).parent / "fh6overlay.log"
        if getattr(sys, "frozen", False)
        else Path(__file__).parent / "fh6overlay.log"
    )

    def _handler(exc_type, exc_value, exc_tb):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n{datetime.datetime.now()}\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass
        msg = QMessageBox()
        msg.setWindowTitle("FH6 Overlay — unexpected error")
        msg.setText(
            f"An unexpected error occurred. The overlay must close.\n\n"
            f"Log saved to:\n{log_path}"
        )
        msg.setDetailedText(
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        )
        msg.exec()
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _handler


def _log_error(location: str) -> None:
    log_path = (
        Path(sys.executable).parent / "fh6overlay.log"
        if getattr(sys, "frozen", False)
        else Path(__file__).parent / "fh6overlay.log"
    )
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n{datetime.datetime.now()} [{location}]\n")
            traceback.print_exc(file=f)
    except Exception:
        pass


class _GridOverlay(QQuickPaintedItem):
    """Semi-transparent grid overlay rendered behind elements during edit mode."""

    _GRID = 8

    def paint(self, p: QPainter) -> None:
        w, h = int(self.width()), int(self.height())
        g = self._GRID
        # Minor grid lines (very subtle)
        p.setPen(QColor(255, 255, 255, 18))
        for x in range(0, w + g, g):
            p.drawLine(x, 0, x, h)
        for y in range(0, h + g, g):
            p.drawLine(0, y, w, y)
        # Major grid lines every 5 cells (slightly brighter)
        p.setPen(QColor(255, 255, 255, 42))
        step = g * 5
        for x in range(0, w + step, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h + step, step):
            p.drawLine(0, y, w, y)


class _HoverControls(QWidget):
    """Ghost-handle strip: always-on-top thin strip that reveals Settings/Close on hover."""

    _FULL_W  = 36
    _BTN_W   = 28
    _BTN_H   = 28
    _BTN_GAP = 4
    _PAD     = 6
    _HEIGHT  = _PAD + _BTN_H + _BTN_GAP + _BTN_H + _PAD   # 72

    def __init__(self, on_settings, on_close):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFixedSize(self._FULL_W, self._HEIGHT)

        _ss_base = (
            "QPushButton { background: rgba(51,65,85,160); color: rgba(255,255,255,210);"
            " border: none; border-radius: 5px; font-size: 14px; }"
            " QPushButton:hover { background: rgba(99,102,241,220); }"
        )
        _ss_close = (
            "QPushButton { background: rgba(51,65,85,160); color: rgba(255,255,255,210);"
            " border: none; border-radius: 5px; font-size: 12px; }"
            " QPushButton:hover { background: rgba(220,38,38,220); }"
        )

        self._settings_btn = QPushButton("⚙", self)
        self._settings_btn.setFixedSize(self._BTN_W, self._BTN_H)
        self._settings_btn.move(4, self._PAD)
        self._settings_btn.setStyleSheet(_ss_base)
        self._settings_btn.clicked.connect(on_settings)
        self._settings_btn.hide()

        self._close_btn = QPushButton("✕", self)
        self._close_btn.setFixedSize(self._BTN_W, self._BTN_H)
        self._close_btn.move(4, self._PAD + self._BTN_H + self._BTN_GAP)
        self._close_btn.setStyleSheet(_ss_close)
        self._close_btn.clicked.connect(on_close)
        self._close_btn.hide()

    def enterEvent(self, event):
        self._settings_btn.show()
        self._close_btn.show()
        self.update()

    def leaveEvent(self, event):
        self._settings_btn.hide()
        self._close_btn.hide()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        # Alpha=1 fill so Windows delivers mouse events on otherwise-transparent pixels
        painter.setBrush(QColor(0, 0, 0, 1))
        painter.drawRect(self.rect())
        w, h = self.width(), self.height()
        if not self._settings_btn.isVisible():
            # Collapsed: subtle right-edge strip indicator
            painter.setBrush(QColor(100, 116, 139, 90))
            painter.drawRoundedRect(w - 5, 0, 5, h, 2, 2)
        else:
            # Expanded: dark background panel
            painter.setBrush(QColor(10, 15, 30, 192))
            painter.drawRoundedRect(0, 0, w, h, 6, 6)
        painter.end()


class OverlayWindow(QQuickWindow):
    def __init__(self, tel: TelemetryState, ctrl: ControllerState,
                 config: Config, config_path: Path):
        QQuickWindow.setDefaultAlphaBuffer(True)
        super().__init__()

        self._tel         = tel
        self._ctrl        = ctrl
        self._config      = config
        self._config_path = config_path

        # Animation state
        self._flash_on:     bool  = True
        self._flash_active: bool  = False
        self._up_fade:      float = 0.0
        self._dn_fade:      float = 0.0
        self._cal_flash_until: float = 0.0
        self._last_tick_time:  float = time.monotonic()

        # Edit Layout mode
        self._edit_mode: bool             = False
        self._layout_snapshot: dict       = {}
        self._elements_panel              = None
        self._grid_overlay                = None
        self._reopen_settings_on_exit: bool = False
        self._settings_panel              = None
        self._hover_controls              = None

        self.setFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setColor(QColor(0, 0, 0, 0))

        # Full-screen on primary display
        screen = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen.x(), screen.y(), screen.width(), screen.height())

        # Create all element items as children of the content item
        from elements import (RPMItem, BrakeItem, ThrottleItem,
                              GearItem, ShiftUpItem, ShiftDnItem)
        ci = self.contentItem()
        self._rpm      = RPMItem(self, ci)
        self._brake    = BrakeItem(self, ci)
        self._throttle = ThrottleItem(self, ci)
        self._gear     = GearItem(self, ci)
        self._shift_up = ShiftUpItem(self, ci)
        self._shift_dn = ShiftDnItem(self, ci)
        self._elements = [self._rpm, self._brake, self._throttle,
                          self._gear, self._shift_up, self._shift_dn]
        self._element_keys = ["rpm", "brake", "throttle", "gear", "shift_up", "shift_dn"]

        self._apply_default_layout()
        self._sync_element_geometry()
        self._sync_visibility()
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(16)   # ~60 fps
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        # Ghost-handle hover controls (Settings + Close)
        from PyQt6.QtWidgets import QApplication as _QApp
        hc = _HoverControls(self._open_settings, _QApp.instance().quit)
        sc = QGuiApplication.primaryScreen().geometry()
        hc.move(
            sc.x() + sc.width() // 2 + 420,
            sc.y() + 10,
        )
        hc.show()
        self._hover_controls = hc

    # ── Default layout ───────────────────────────────────────────────────────

    def _apply_default_layout(self) -> None:
        """Set default positions (and sizes) for elements that still have x == -1."""
        screen = QGuiApplication.primaryScreen().geometry()
        sw = screen.width()
        cx = sw // 2
        # Horizontal layout matches the old TopBarOverlay (overlay_y=10):
        #   RPM lights span the left-of-center region (old center x: cx-137)
        #   Brake | Gear column | Throttle span the right-of-center region
        # Vertical:  shift_up above gear, gear in middle, shift_dn below
        #   y=10 to y=142 compact top band (old band was y=35-85, new elements are larger)
        defaults = {
            # Sizes approximate old TopBarOverlay proportions; all center on cy=32 from top
            # (old overlay: overlay_y=10, cy=50 within 101px-high widget → screen cy=60)
            # key: (x, y, w, h)
            "rpm":      (max(0, cx - 387), 10,  500, 44),  # right: cx+113, center_y=32
            "brake":    (cx + 118,         22,  100, 20),  # right: cx+218, center_y=32
            "shift_up": (cx + 223,          0,   40, 14),  # above gear
            "gear":     (cx + 223,         16,   40, 32),  # right: cx+263, center_y=32
            "shift_dn": (cx + 223,         50,   40, 14),  # below gear
            "throttle": (cx + 268,         22,  100, 20),  # right: cx+368, center_y=32
        }
        cfg = self._config
        for key, (dx, dy, dw, dh) in defaults.items():
            if getattr(cfg, f"{key}_x") == -1:
                setattr(cfg, f"{key}_x", max(0, dx))
                setattr(cfg, f"{key}_y", max(0, dy))
                setattr(cfg, f"{key}_w", dw)
                setattr(cfg, f"{key}_h", dh)

    def _sync_element_geometry(self) -> None:
        """Push x/y/w/h from config onto each element item."""
        cfg = self._config
        for item, key in zip(self._elements, self._element_keys):
            item.setX(getattr(cfg, f"{key}_x"))
            item.setY(getattr(cfg, f"{key}_y"))
            item.setSize(QSizeF(getattr(cfg, f"{key}_w"), getattr(cfg, f"{key}_h")))

    def _sync_visibility(self) -> None:
        cfg = self._config
        self._rpm.setVisible(cfg.show_rev_lights)
        self._brake.setVisible(cfg.show_brake_bar)
        self._throttle.setVisible(cfg.show_throttle_bar)
        self._gear.setVisible(cfg.show_gear)
        self._shift_up.setVisible(cfg.show_shift_indicators)
        self._shift_dn.setVisible(cfg.show_shift_indicators)

    def apply_config(self) -> None:
        try:
            self._sync_element_geometry()
            self._sync_visibility()
            for el in self._elements:
                el.update()
        except Exception:
            _log_error("apply_config")

    # ── Edit mode ────────────────────────────────────────────────────────────

    def toggle_edit_mode(self, reopen_settings: bool = False) -> None:
        if self._edit_mode:
            self._apply_layout()
            return
        self._edit_mode = True
        self._reopen_settings_on_exit = reopen_settings
        cfg = self._config
        self._layout_snapshot = {
            f"{key}_{dim}": getattr(cfg, f"{key}_{dim}")
            for key in self._element_keys
            for dim in ("x", "y", "w", "h")
        }
        self.hide()
        self.setFlag(Qt.WindowType.WindowTransparentForInput, False)
        for el in self._elements:
            el.setVisible(True)
        self.show()
        for el in self._elements:
            el.update()

        # Grid overlay — rendered behind all elements (z = -1)
        screen = QGuiApplication.primaryScreen().geometry()
        grid = _GridOverlay(self.contentItem())
        grid.setX(0)
        grid.setY(0)
        grid.setSize(QSizeF(screen.width(), screen.height()))
        grid.setZ(-1)
        grid.setVisible(True)
        self._grid_overlay = grid

        # Appearance panel with Apply / Cancel
        from settings_panel import ElementsPanel
        ep = ElementsPanel(
            self._config, self._config_path, self,
            on_apply=self._apply_layout,
            on_cancel=self._cancel_layout,
        )
        ep.show()
        self._elements_panel = ep

        if self._hover_controls is not None:
            self._hover_controls.hide()

    def _apply_layout(self) -> None:
        cfg = self._config
        for el, key in zip(self._elements, self._element_keys):
            setattr(cfg, f"{key}_x", int(el.x()))
            setattr(cfg, f"{key}_y", int(el.y()))
            setattr(cfg, f"{key}_w", int(el.width()))
            setattr(cfg, f"{key}_h", int(el.height()))
        save_config(self._config_path, cfg)
        self._exit_edit_mode()

    def _cancel_layout(self) -> None:
        for key, val in self._layout_snapshot.items():
            setattr(self._config, key, val)
        self._sync_element_geometry()
        self._exit_edit_mode()

    def _exit_edit_mode(self) -> None:
        self._edit_mode = False
        if self._grid_overlay is not None:
            self._grid_overlay.setVisible(False)
            self._grid_overlay.setParentItem(None)
            self._grid_overlay.deleteLater()
            self._grid_overlay = None
        if self._elements_panel is not None:
            self._elements_panel.close()
            self._elements_panel = None
        self.hide()
        self.setFlag(Qt.WindowType.WindowTransparentForInput, True)
        self._sync_visibility()
        self.show()
        for el in self._elements:
            el.update()
        if self._hover_controls is not None:
            self._hover_controls.show()
        if self._reopen_settings_on_exit:
            self._reopen_settings_on_exit = False
            self._open_settings()

    # ── Settings ─────────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        from settings_panel import SettingsPanel
        if self._settings_panel is None:
            self._settings_panel = SettingsPanel(
                self._config, self._config_path, self._tel, self
            )
        self._settings_panel.show()
        self._settings_panel.raise_()

    # ── Tick loop ────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        try:
            self._tick_impl()
        except Exception:
            _log_error("_tick")

    def _tick_impl(self) -> None:
        now   = time.monotonic()
        dt_ms = (now - self._last_tick_time) * 1000
        self._last_tick_time = now

        self._tel.check_timeout()

        if self._tel.calibration_updated:
            self._tel.calibration_updated = False
            self._cal_flash_until = now + 1.0

        self._flash_on = int(now * 1000 / _FLASH_HALF_MS) % 2 == 0

        ratio = self._tel.ratio
        sr    = self._config.shift_ratio
        if ratio >= sr:
            self._flash_active = True
        elif ratio < sr * 0.94:
            self._flash_active = False

        decay = dt_ms / SHIFT_FADE_MS
        self._up_fade = 1.0 if self._ctrl.shift_up   else max(0.0, self._up_fade - decay)
        self._dn_fade = 1.0 if self._ctrl.shift_down else max(0.0, self._dn_fade - decay)

        if self._ctrl.toggle_hide and not self._edit_mode:
            vis = not self._rpm.isVisible()
            for el in self._elements:
                el.setVisible(vis)
            if self._hover_controls is not None:
                self._hover_controls.setVisible(vis)
            self._ctrl.toggle_hide = False

        for el in self._elements:
            el.update()


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
    from config import load_config, CONFIG_PATH, VERSION
    from setup_wizard import SetupWizard

    _install_exception_handler()
    _install_qt_message_handler()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # U16: single instance — after QApplication so we can show a message
    if not _acquire_single_instance():
        QMessageBox.warning(None, "FH6 Overlay", "FH6 Overlay is already running.")
        sys.exit(0)

    if not CONFIG_PATH.exists():
        wizard = SetupWizard(CONFIG_PATH)
        wizard.exec()

    config = load_config(CONFIG_PATH)

    parser = argparse.ArgumentParser(description="FH6 rev light overlay")
    parser.add_argument("--port", type=int, default=None,
                        help="UDP port override (default: from config.ini)")
    args = parser.parse_args()
    port = args.port if args.port is not None else config.udp_port

    tel  = TelemetryState()
    ctrl = ControllerState()

    try:
        start_udp_listener(tel, port)
    except OSError as e:
        QMessageBox.critical(
            None, "FH6 Overlay — port error",
            f"Could not bind to UDP port {port}.\n\n"
            f"Make sure no other instance is running.\n\nDetails: {e}"
        )
        sys.exit(1)

    start_controller_listener(ctrl, config.shift_up_button,
                              config.shift_down_button, config.clutch_button,
                              config.hide_button)

    overlay = OverlayWindow(tel, ctrl, config, CONFIG_PATH)
    overlay.show()

    tray = QSystemTrayIcon(parent=app)
    ico_path = Path(__file__).parent / "logo" / "SkoiZzLogo.ico"
    if getattr(sys, "frozen", False):
        ico_path = Path(sys._MEIPASS) / "logo" / "SkoiZzLogo.ico"
    if ico_path.exists():
        tray.setIcon(QIcon(str(ico_path)))
    else:
        tray.setIcon(_tray_icon())
    tray.setToolTip(f"FH6 Overlay v{VERSION}")
    menu = QMenu()
    menu.addAction("Settings",    overlay._open_settings)
    menu.addAction("Edit Layout", overlay.toggle_edit_mode)
    menu.addSeparator()
    menu.addAction("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.show()

    ret = app.exec()
    # Close the QQuickWindow before sys.exit so the DXGI VSync render
    # thread can finish cleanly before static destructors run.
    overlay.close()
    app.processEvents()
    sys.exit(ret)


if __name__ == "__main__":
    main()
