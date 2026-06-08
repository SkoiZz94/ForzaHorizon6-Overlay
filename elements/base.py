import traceback
from pathlib import Path
from PyQt6.QtQuick import QQuickPaintedItem
from PyQt6.QtCore  import Qt, QPointF, QSizeF, QRectF, QTimer
from PyQt6.QtGui   import QPainter, QColor, QFont, QPen, QPolygon
from PyQt6.QtCore  import QPoint

_LOG_PATH = Path(__file__).parent.parent / "fh6overlay.log"

def _log_paint_error(key: str, exc: Exception) -> None:
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            import datetime
            f.write(f"\n{'='*60}\n{datetime.datetime.now()} [paint:{key}]\n")
            traceback.print_exc(file=f)
    except Exception:
        pass

_STYLE_ATTR: dict[str, str] = {
    "rpm":      "RPM_STYLES",
    "brake":    "BRAKE_STYLES",
    "throttle": "THROTTLE_STYLES",
    "gear":     "GEAR_STYLES",
    "shift_up": "SHIFT_STYLES",
    "shift_dn": "SHIFT_STYLES",
}

_MENU_SS = """
QMenu {
    background: #0f172a; color: #e2e8f0; border: 1px solid #1e3a5f;
    font-family: Consolas; font-size: 12px; padding: 4px 0;
}
QMenu::item            { padding: 6px 20px 6px 28px; }
QMenu::item:selected   { background: #1e40af; color: white; }
QMenu::item:checked    { color: #60a5fa; }
QMenu::indicator       { width: 12px; height: 12px; left: 8px; }
"""

_EDIT_COLORS: dict[str, str] = {
    "rpm":      "#3b82f6",
    "brake":    "#ef4444",
    "throttle": "#22c55e",
    "gear":     "#8b5cf6",
    "shift_up": "#facc15",
    "shift_dn": "#f97316",
}
_RESIZE_GRIP = 16  # px square in bottom-right corner
_MIN_W = 30
_MIN_H = 14
_GRID  = 8         # snap grid size in edit mode


def _snap(v: float) -> float:
    return round(v / _GRID) * _GRID


class BaseElement(QQuickPaintedItem):
    """
    Abstract base for all overlay elements.

    Subclasses implement `_paint_element(painter)`.
    In Edit Layout mode the base class draws a colour-coded border,
    element name label, and a triangular resize grip, and handles
    mouse drag (move) and resize interactions.
    """

    def __init__(self, win, key: str, parent=None):
        super().__init__(parent)
        self._win = win
        self._key = key
        self._drag_offset: QPointF | None = None
        self._resizing: bool = False
        self._dirty:   bool  = False
        self.setAcceptedMouseButtons(Qt.MouseButton.AllButtons)

    # ── Public interface ────────────────────────────────────────────────────

    @property
    def _style(self) -> str:
        return getattr(self._win._config, f"{self._key}_style")

    # ── Painting ────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter) -> None:
        try:
            if int(self.width()) < 4 or int(self.height()) < 4:
                return
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_element(painter)
            if self._win._edit_mode:
                self._paint_edit_overlay(painter)
        except Exception as exc:
            _log_paint_error(self._key, exc)

    def _paint_element(self, painter: QPainter) -> None:
        raise NotImplementedError

    def _paint_edit_overlay(self, painter: QPainter) -> None:
        w, h = int(self.width()), int(self.height())
        ec   = QColor(_EDIT_COLORS.get(self._key, "#ffffff"))

        # Tinted background
        tint = QColor(ec.red(), ec.green(), ec.blue(), 28)
        painter.fillRect(0, 0, w, h, tint)

        # Border
        pen = QPen(ec, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(1, 1, w - 2, h - 2)

        # Label
        painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawText(4, 0, w - 8, 14,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self._key.replace("_", " ").upper())

        # Resize grip — filled triangle in bottom-right corner
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ec)
        g = _RESIZE_GRIP
        painter.drawPolygon(QPolygon([
            QPoint(w - g, h),
            QPoint(w,     h - g),
            QPoint(w,     h),
        ]))

    # ── Hit testing ─────────────────────────────────────────────────────────

    def _in_resize_grip(self, pos: QPointF) -> bool:
        w, h = self.width(), self.height()
        return (w - _RESIZE_GRIP <= pos.x() <= w and
                h - _RESIZE_GRIP <= pos.y() <= h)

    # ── Mouse events (only active when edit mode is on) ─────────────────────

    def mousePressEvent(self, event) -> None:
        if not self._win._edit_mode:
            event.ignore()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._show_style_menu(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self._in_resize_grip(event.position()):
            self._resizing = True
        else:
            self._drag_offset = event.globalPosition() - QPointF(self.x(), self.y())
        self.grabMouse()
        event.accept()
        # Re-raise the elements panel after the overlay window steals Z-order focus
        ep = getattr(self._win, '_elements_panel', None)
        if ep is not None:
            QTimer.singleShot(0, ep.raise_)

    def mouseMoveEvent(self, event) -> None:
        if not self._win._edit_mode:
            event.ignore()
            return
        if self._drag_offset is not None and not self._resizing:
            p = event.globalPosition() - self._drag_offset
            self.setX(max(0.0, _snap(p.x())))
            self.setY(max(0.0, _snap(p.y())))
            self._dirty = True
        elif self._resizing:
            lp = event.position()
            self.setSize(QSizeF(max(_MIN_W, _snap(lp.x())), max(_MIN_H, _snap(lp.y()))))
            self._dirty = True
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._win._edit_mode:
            event.ignore()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            if self._drag_offset is not None or self._resizing:
                self.ungrabMouse()
                self._drag_offset = None
                self._resizing = False
            event.ignore()
            return
        if self._drag_offset is not None or self._resizing:
            self.ungrabMouse()
        # Persist new geometry to config only when something actually moved/resized
        if self._dirty:
            cfg = self._win._config
            key = self._key
            setattr(cfg, f"{key}_x", int(self.x()))
            setattr(cfg, f"{key}_y", int(self.y()))
            setattr(cfg, f"{key}_w", int(self.width()))
            setattr(cfg, f"{key}_h", int(self.height()))
            self._dirty = False
        self._drag_offset = None
        self._resizing = False
        event.accept()

    # ── Style context menu ───────────────────────────────────────────────────

    def _show_style_menu(self, global_pos) -> None:
        import config as cfg_mod
        from config import STYLE_LABELS, save_config
        from PyQt6.QtWidgets import QMenu

        styles_attr = _STYLE_ATTR.get(self._key)
        if styles_attr is None:
            return
        styles  = getattr(cfg_mod, styles_attr)
        current = self._style

        menu = QMenu()
        menu.setStyleSheet(_MENU_SS)
        for style_key in styles:
            action = menu.addAction(STYLE_LABELS.get(style_key, style_key))
            action.setCheckable(True)
            action.setChecked(style_key == current)
            action.setData(style_key)

        chosen = menu.exec(global_pos)
        if chosen is not None:
            new_style = chosen.data()
            setattr(self._win._config, f"{self._key}_style", new_style)
            save_config(self._win._config_path, self._win._config)
            self.update()

    # ── Shared QPainter helpers used by subclasses ──────────────────────────

    @staticmethod
    def _glow(painter: QPainter, cx: float, cy: float,
              radius: float, color: QColor, alpha: float) -> None:
        """Radial gradient glow centred at (cx, cy)."""
        from PyQt6.QtGui import QRadialGradient, QBrush
        if alpha <= 0:
            return
        g = QRadialGradient(cx, cy, radius)
        c0 = QColor(color)
        c0.setAlphaF(alpha)
        c1 = QColor(color)
        c1.setAlphaF(0.0)
        g.setColorAt(0.0, c0)
        g.setColorAt(1.0, c1)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(g))
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        painter.restore()

    @staticmethod
    def _annular_arc(cx: float, cy: float,
                     r_out: float, r_in: float,
                     start_deg: float, sweep_deg: float):
        """Return a QPainterPath for an annular (donut) arc segment.

        Angles follow QPainter convention: 0° = 3 o'clock, positive = CCW.
        sweep_deg negative = clockwise arc.
        """
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.arcMoveTo(cx - r_out, cy - r_out, r_out * 2, r_out * 2, start_deg)
        path.arcTo(    cx - r_out, cy - r_out, r_out * 2, r_out * 2, start_deg,  sweep_deg)
        path.arcTo(    cx - r_in,  cy - r_in,  r_in  * 2, r_in  * 2,
                   start_deg + sweep_deg, -sweep_deg)
        path.closeSubpath()
        return path
