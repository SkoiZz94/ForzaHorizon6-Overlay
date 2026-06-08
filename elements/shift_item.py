from PyQt6.QtCore  import Qt, QRectF, QPointF
from PyQt6.QtGui   import (QPainter, QColor, QFont, QPainterPath,
                            QBrush, QPen, QPolygonF)
from .base import BaseElement

_UNLIT  = QColor("#1f2937")
_BAR_BG = QColor("#1a2332")


class ShiftItem(BaseElement):
    """
    A single-direction shift indicator.
    `direction` is "up" or "dn".
    """

    def __init__(self, win, direction: str, parent=None):
        if direction not in ("up", "dn"):
            raise ValueError(f"direction must be 'up' or 'dn', got {direction!r}")
        super().__init__(win, f"shift_{direction}", parent)
        self._direction = direction

    @property
    def _fade(self) -> float:
        return self._win._up_fade if self._direction == "up" else self._win._dn_fade

    @property
    def _point_up(self) -> bool:
        return self._direction == "up"

    @property
    def _color(self) -> QColor:
        return QColor(self._win._config.colour_shift_active)

    def _paint_element(self, painter: QPainter) -> None:
        w, h  = int(self.width()), int(self.height())
        fade  = self._fade
        color = self._color
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 0))
        s = self._style
        if   s == "triangle":   self._triangle(painter, w, h, fade, color)
        elif s == "chevrons":   self._chevrons(painter, w, h, fade, color)
        elif s == "flash_bar":  self._flash_bar(painter, w, h, fade, color)
        elif s == "text_label": self._text_label(painter, w, h, fade, color)
        elif s == "glow_pulse": self._glow_pulse(painter, w, h, fade, color)
        elif s == "pulse_ring": self._pulse_ring(painter, w, h, fade, color)

    # ── triangle ─────────────────────────────────────────────────────────────

    def _triangle(self, p, w, h, fade, color):
        cx, cy = w / 2, h / 2
        aw, ah = min(w * 0.55, 22.0), min(h * 0.55, 20.0)
        if fade > 0:
            self._glow(p, cx, cy, aw * 1.0, color, fade * 0.5)
        poly = QPolygonF()
        if self._point_up:
            poly.append(QPointF(cx,        cy - ah / 2))
            poly.append(QPointF(cx + aw/2, cy + ah / 2))
            poly.append(QPointF(cx - aw/2, cy + ah / 2))
        else:
            poly.append(QPointF(cx,        cy + ah / 2))
            poly.append(QPointF(cx + aw/2, cy - ah / 2))
            poly.append(QPointF(cx - aw/2, cy - ah / 2))
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor(color)
        c.setAlphaF(max(0.35, fade) if fade > 0 else 0.55)
        p.setBrush(c if fade > 0 else _UNLIT)
        p.drawPolygon(poly)

    # ── chevrons ──────────────────────────────────────────────────────────────

    def _chevrons(self, p, w, h, fade, color):
        cx, cy = w / 2, h / 2
        cw, ch = min(w * 0.45, 16.0), min(h * 0.30, 10.0)
        if fade > 0:
            self._glow(p, cx, cy, 30.0, color, fade * 0.3)
        pen_c = QColor(color) if fade > 0 else QColor(_UNLIT)
        pen_c.setAlphaF(max(0.3, fade) if fade > 0 else 0.4)
        p.setPen(QPen(pen_c, 2.5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        offsets = [-12, 2] if self._point_up else [-2, 12]
        for oy in offsets:
            if self._point_up:
                pts = [QPointF(cx - cw, cy + oy + ch),
                       QPointF(cx,      cy + oy),
                       QPointF(cx + cw, cy + oy + ch)]
            else:
                pts = [QPointF(cx - cw, cy + oy),
                       QPointF(cx,      cy + oy + ch),
                       QPointF(cx + cw, cy + oy)]
            p.drawPolyline(QPolygonF(pts))

    # ── flash_bar ─────────────────────────────────────────────────────────────

    def _flash_bar(self, p, w, h, fade, color):
        px = 6; bh = h - 10; by = 5; bw = w - px * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(px, by, bw, bh, 5, 5)
        if fade > 0:
            overlay = QColor(color)
            overlay.setAlphaF(fade * 0.85)
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(px, by, bw, bh), 5, 5)
            p.setClipPath(clip)
            p.setBrush(overlay)
            p.drawRect(px, by, bw, bh)
            p.restore()
        arrow = "▲" if self._point_up else "▼"
        label = f"{arrow} {'UP' if self._point_up else 'DN'}"
        c = QColor(color if fade > 0 else "#475569")
        c.setAlphaF(max(0.4, fade) if fade > 0 else 0.45)
        p.setPen(c)
        fs = max(7, min(int(bh * 0.55), int(bw / (len(label) * 0.65))))
        p.setFont(QFont("Consolas", fs, QFont.Weight.Bold))
        p.drawText(QRectF(px, by, bw, bh), Qt.AlignmentFlag.AlignCenter, label)

    # ── text_label ────────────────────────────────────────────────────────────

    def _text_label(self, p, w, h, fade, color):
        px = 6; bh = h - 10; by = 5; bw = w - px * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(px, by, bw, bh, 4, 4)
        if fade > 0.05:
            border_c = QColor(color)
            border_c.setAlphaF(fade * 0.7)
            p.setPen(QPen(border_c, 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(px, by, bw, bh, 4, 4)
        arrow = "↑" if self._point_up else "↓"
        label = f"SHIFT {arrow}"
        c = QColor(color if fade > 0 else "#475569")
        c.setAlphaF(max(0.4, fade) if fade > 0 else 0.45)
        p.setPen(c)
        fs = max(7, min(int(bh * 0.55), int(bw / (len(label) * 0.65))))
        p.setFont(QFont("Consolas", fs, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, label)

    # ── glow_pulse ────────────────────────────────────────────────────────────

    def _glow_pulse(self, p, w, h, fade, color):
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.28
        if fade > 0:
            self._glow(p, cx, cy, r * 1.6, color, fade * 0.8)
        c = QColor(color) if fade > 0 else QColor(_UNLIT)
        if fade > 0:
            c.setAlphaF(0.25 + fade * 0.75)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    # ── pulse_ring ────────────────────────────────────────────────────────────

    def _pulse_ring(self, p, w, h, fade, color):
        cx, cy  = w / 2, h / 2
        dot_r   = min(w, h) * 0.18
        max_r   = min(w, h) * 0.46
        if fade > 0:
            self._glow(p, cx, cy, dot_r * 2.4, color, fade * 0.5)
        c = QColor(color) if fade > 0 else QColor(_UNLIT)
        if fade > 0:
            c.setAlphaF(max(0.3, fade))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2))
        # Static dim triangle — always drawn, independent of fade
        aw = dot_r * 0.65
        ah = dot_r * 0.60
        tri = QPolygonF()
        if self._point_up:
            tri.append(QPointF(cx,        cy - ah / 2))
            tri.append(QPointF(cx + aw/2, cy + ah / 2))
            tri.append(QPointF(cx - aw/2, cy + ah / 2))
        else:
            tri.append(QPointF(cx,        cy + ah / 2))
            tri.append(QPointF(cx + aw/2, cy - ah / 2))
            tri.append(QPointF(cx - aw/2, cy - ah / 2))
        p.setPen(Qt.PenStyle.NoPen)
        dim = QColor(0, 0, 0, 120)
        p.setBrush(dim)
        p.drawPolygon(tri)
        if fade > 0.05:
            ring_r = dot_r + 2 + (max_r - dot_r - 2) * (1 - fade)
            pen_c  = QColor(color)
            pen_c.setAlphaF(fade * 0.85)
            p.setPen(QPen(pen_c, max(1.0, 2.5 * fade)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2))


class ShiftUpItem(ShiftItem):
    def __init__(self, win, parent=None):
        super().__init__(win, "up", parent)


class ShiftDnItem(ShiftItem):
    def __init__(self, win, parent=None):
        super().__init__(win, "dn", parent)
