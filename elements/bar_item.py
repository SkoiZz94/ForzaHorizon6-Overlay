from PyQt6.QtCore  import Qt, QRectF
from PyQt6.QtGui   import (QPainter, QColor, QFont, QLinearGradient,
                            QBrush, QPainterPath)
from .base import BaseElement

_BAR_BG = QColor("#1a2332")
_MUTED  = QColor("#64748b")
_TEXT   = QColor("#e2e8f0")

# Quarter arc: 3 o'clock (0°) → 12 o'clock (90°) counter-clockwise
_QA_START =  0.0
_QA_SWEEP =  90.0

# Radial fill: SA = π×0.85 rads → QPainter degrees = -180*0.85
# sweep = π×1.30 rads → QPainter degrees = -180*1.30 (negative = CW)
_RF_START = -180 * 0.85
_RF_SWEEP = -180 * 1.30


class BarItem(BaseElement):
    """Shared base for BrakeItem and ThrottleItem."""

    def __init__(self, win, key: str, fill_from_left: bool, parent=None):
        super().__init__(win, key, parent)
        self._fill_left_base = fill_from_left

    @property
    def _fill_left(self) -> bool:
        rev = getattr(self._win._config, f"{self._key}_bar_reversed", False)
        return (not self._fill_left_base) if rev else self._fill_left_base

    @property
    def _value(self) -> float:
        raw = (self._win._ctrl.lt_pct if self._key == "brake"
               else self._win._ctrl.rt_pct)
        return min(1.0, raw / 100)

    @property
    def _c0(self) -> QColor:
        attr = "colour_brake_start" if self._key == "brake" else "colour_throttle_start"
        return QColor(getattr(self._win._config, attr))

    @property
    def _c1(self) -> QColor:
        attr = "colour_brake_end" if self._key == "brake" else "colour_throttle_end"
        return QColor(getattr(self._win._config, attr))

    def _paint_element(self, painter: QPainter) -> None:
        w, h = int(self.width()), int(self.height())
        v    = self._value
        c0, c1 = self._c0, self._c1
        cfg = self._win._config
        show_pct = (cfg.show_brake_label if self._key == "brake"
                    else cfg.show_throttle_label)
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 0))
        s = self._style
        if   s == "horiz_bar":      self._horiz_bar(painter, w, h, v, c0, c1, show_pct)
        elif s == "vert_bar":       self._vert_bar(painter, w, h, v, c0, c1, show_pct)
        elif s == "quarter_arc":    self._quarter_arc(painter, w, h, v, c0, c1, show_pct)
        elif s == "numeric":        self._numeric(painter, w, h, v, c1)
        elif s == "radial_fill":    self._radial_fill(painter, w, h, v, c0, c1, show_pct)
        elif s == "stacked_blocks": self._stacked_blocks(painter, w, h, v, c0, c1, show_pct)

    # ── horiz_bar ────────────────────────────────────────────────────────────

    def _horiz_bar(self, p, w, h, v, c0, c1, show_pct):
        px = 10
        bh = max(10, int(h * 0.55))
        by = (h - bh) // 2
        bw = w - px * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(px, by, bw, bh, 4, 4)
        fw = int(bw * v)
        if fw > 1:
            fx = px if self._fill_left else px + bw - fw
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(fx, by, fw, bh), 4, 4)
            p.setClipPath(clip)
            gr = QLinearGradient(px, 0, px + bw, 0)
            if self._fill_left:
                gr.setColorAt(0.0, c0); gr.setColorAt(1.0, c1)
            else:
                gr.setColorAt(0.0, c1); gr.setColorAt(1.0, c0)
            p.setBrush(QBrush(gr))
            p.drawRect(px, by, bw, bh)
            p.restore()
        if show_pct:
            p.setPen(_TEXT)
            p.setFont(QFont("Consolas", max(6, int(bh * 0.60)), QFont.Weight.Bold))
            p.drawText(QRectF(px + 3, by, bw - 6, bh),
                       Qt.AlignmentFlag.AlignCenter, f"{int(v * 100)}%")

    # ── vert_bar ─────────────────────────────────────────────────────────────

    def _vert_bar(self, p, w, h, v, c0, c1, show_pct):
        px, py = 8, 8
        bw = w - px * 2
        bh = h - py * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(px, py, bw, bh, 4, 4)
        fh = int(bh * v)
        if fh > 1:
            fy = py if not self._fill_left else py + bh - fh
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(px, fy, bw, fh), 4, 4)
            p.setClipPath(clip)
            gr = QLinearGradient(0, py, 0, py + bh)
            if self._fill_left:
                gr.setColorAt(0.0, c1); gr.setColorAt(1.0, c0)
            else:
                gr.setColorAt(0.0, c0); gr.setColorAt(1.0, c1)
            p.setBrush(QBrush(gr))
            p.drawRect(px, py, bw, bh)
            p.restore()
        if show_pct:
            p.setPen(_TEXT)
            p.setFont(QFont("Consolas", max(6, int(bh * 0.30)), QFont.Weight.Bold))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       f"{int(v * 100)}%")

    # ── quarter_arc ───────────────────────────────────────────────────────────

    def _quarter_arc(self, p, w, h, v, c0, c1, show_pct):
        p.save()
        if not self._fill_left:
            p.translate(w, 0)
            p.scale(-1, 1)
        ox = 8
        oy = h - 8
        R  = min((w - ox) * 0.92, oy * 0.92)
        ri = R * 0.60
        track = self._annular_arc(ox, oy, R, ri, _QA_START, _QA_SWEEP)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawPath(track)
        if v > 0.005:
            fill_sweep = _QA_SWEEP * v
            fill_path  = self._annular_arc(ox, oy, R - 1, ri + 1, _QA_START, fill_sweep)
            gr = QLinearGradient(ox + R, oy, ox, oy - R)
            gr.setColorAt(0.0, c0); gr.setColorAt(1.0, c1)
            p.setBrush(QBrush(gr))
            p.drawPath(fill_path)
        p.restore()

    # ── numeric ───────────────────────────────────────────────────────────────

    def _numeric(self, p, w, h, v, accent):
        p.setPen(accent)
        p.setFont(QFont("Consolas", max(10, int(h * 0.45)), QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                   f"{int(v * 100)}%")

    # ── radial_fill ───────────────────────────────────────────────────────────

    def _radial_fill(self, p, w, h, v, c0, c1, show_pct):
        cx    = w / 2
        cy    = h * 0.52
        R     = min(w, h) * 0.44
        ri    = R * 0.58
        if self._fill_left:
            start, total = _RF_START, _RF_SWEEP
        else:
            start, total = _RF_START + _RF_SWEEP, -_RF_SWEEP
        track = self._annular_arc(cx, cy, R, ri, start, total)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawPath(track)
        if v > 0.005:
            fill_path = self._annular_arc(cx, cy, R - 1, ri + 1, start, total * v)
            gr = QLinearGradient(cx - R, cy, cx + R, cy)
            if self._fill_left:
                gr.setColorAt(0.0, c0); gr.setColorAt(1.0, c1)
            else:
                gr.setColorAt(0.0, c1); gr.setColorAt(1.0, c0)
            p.setBrush(QBrush(gr))
            p.drawPath(fill_path)
        if show_pct:
            p.setPen(c1)
            p.setFont(QFont("Consolas", max(7, int(R * 0.30)), QFont.Weight.Bold))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       f"{int(v * 100)}%")

    # ── stacked_blocks ────────────────────────────────────────────────────────

    def _stacked_blocks(self, p, w, h, v, c0, c1, show_pct):
        n       = 8
        px, py  = 8, 8
        gap     = 4
        bw      = w - px * 2
        bh_each = max(4, (h - py * 2 - gap * (n - 1)) // n)
        lit     = round(v * n)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            ty     = py + (n - 1 - i) * (bh_each + gap)
            is_lit = (i < lit) if self._fill_left else (i >= n - lit)
            t      = i / (n - 1) if n > 1 else 0.0
            if is_lit:
                r0, g0, b0 = c0.red(), c0.green(), c0.blue()
                r1, g1, b1 = c1.red(), c1.green(), c1.blue()
                if t < 0.4:
                    c = c0
                elif t < 0.75:
                    tf = (t - 0.4) / 0.35
                    c = QColor(int(r0+(r1-r0)*tf), int(g0+(g1-g0)*tf), int(b0+(b1-b0)*tf))
                else:
                    c = c1
                p.setBrush(c)
            else:
                p.setBrush(_BAR_BG)
            p.drawRoundedRect(px, ty, bw, bh_each, 3, 3)
        if show_pct:
            p.setPen(_TEXT)
            p.setFont(QFont("Consolas", max(8, int(h * 0.22)), QFont.Weight.Bold))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       f"{int(v * 100)}%")


class BrakeItem(BarItem):
    def __init__(self, win, parent=None):
        super().__init__(win, "brake", fill_from_left=True, parent=parent)


class ThrottleItem(BarItem):
    def __init__(self, win, parent=None):
        super().__init__(win, "throttle", fill_from_left=False, parent=parent)
