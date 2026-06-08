import math
from PyQt6.QtCore  import Qt, QRectF, QPointF
from PyQt6.QtGui   import (QPainter, QColor, QFont, QPainterPath,
                            QBrush, QPen)
from .base import BaseElement

_GEAR_BG = QColor("#0f172a")
_TEXT    = QColor("#e2e8f0")
_MUTED   = QColor("#64748b")
_BORDER  = QColor("#1e3a5f")


def _gear_label(win) -> str:
    tel = win._tel
    if not tel.connected:
        return "–"
    if tel.display_gear == 0:
        return "R"
    if tel.is_electric:
        return "D"
    return str(tel.display_gear)


def _font_size(label: str, base_px: int) -> int:
    size = int(base_px * 0.72) if len(label) > 1 else base_px
    return max(6, size)


class GearItem(BaseElement):
    def __init__(self, win, parent=None):
        super().__init__(win, "gear", parent)

    def _paint_element(self, painter: QPainter) -> None:
        w, h  = int(self.width()), int(self.height())
        label = _gear_label(self._win)
        if self._win._ctrl.clutch:
            label = "C"
        painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 0))
        s = self._style
        if   s == "box":           self._box(painter, w, h, label)
        elif s == "minimal":       self._minimal(painter, w, h, label)
        elif s == "mode_tag":      self._mode_tag(painter, w, h, label)
        elif s == "hexagon":       self._hexagon(painter, w, h, label)
        elif s == "pill":          self._pill(painter, w, h, label)
        elif s == "rpm_color_fill": self._rpm_color_fill(painter, w, h, label)

    # ── box ──────────────────────────────────────────────────────────────────

    def _box(self, p, w, h, label):
        bw = min(w - 4, max(40, int(w * 0.80)))
        bh = min(h - 4, max(28, int(h * 0.76)))
        bx = (w - bw) // 2; by = (h - bh) // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_GEAR_BG)
        p.drawRoundedRect(bx, by, bw, bh, 7, 7)
        p.setPen(_BORDER)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(bx, by, bw, bh, 7, 7)
        cfg = self._win._config
        p.setPen(QColor(cfg.colour_gear_text))
        p.setFont(QFont("Consolas", _font_size(label, int(h * 0.5)), QFont.Weight.Bold))
        p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, label)

    # ── minimal ───────────────────────────────────────────────────────────────

    def _minimal(self, p, w, h, label):
        self._glow(p, w / 2, h / 2, min(w, h) * 0.45, QColor("#94a3b8"), 0.18)
        p.setPen(_TEXT)
        p.setFont(QFont("Consolas", _font_size(label, int(h * 0.65)), QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, label)

    # ── mode_tag ──────────────────────────────────────────────────────────────

    def _mode_tag(self, p, w, h, label):
        p.setPen(_TEXT)
        p.setFont(QFont("Consolas", _font_size(label, int(h * 0.48)), QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h * 0.60), Qt.AlignmentFlag.AlignCenter, label)
        mode = self._win._config.transmission.replace("_", " ").upper()
        p.setPen(_MUTED)
        p.setFont(QFont("Consolas", max(6, int(h * 0.11))))
        p.drawText(QRectF(0, h * 0.65, w, h * 0.35), Qt.AlignmentFlag.AlignCenter, mode)

    # ── hexagon ───────────────────────────────────────────────────────────────

    def _hexagon(self, p, w, h, label):
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.45
        path = QPainterPath()
        for i in range(6):
            angle = math.pi / 6 + i * math.pi / 3
            pt    = QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_GEAR_BG)
        p.drawPath(path)
        p.setPen(QColor("#334155"))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(_TEXT)
        p.setFont(QFont("Consolas", _font_size(label, int(r * 0.80)), QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, label)

    # ── pill ──────────────────────────────────────────────────────────────────

    def _pill(self, p, w, h, label):
        ph = min(h - 8, max(26, int(h * 0.65)))
        py = (h - ph) // 2
        px = 6; pw = w - px * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_GEAR_BG)
        p.drawRoundedRect(px, py, pw, ph, ph / 2, ph / 2)
        p.setPen(_BORDER)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(px, py, pw, ph, ph / 2, ph / 2)
        p.setPen(_TEXT)
        p.setFont(QFont("Consolas", _font_size(label, int(ph * 0.60)), QFont.Weight.Bold))
        p.drawText(QRectF(px, py, pw, ph), Qt.AlignmentFlag.AlignCenter, label)

    # ── rpm_color_fill ────────────────────────────────────────────────────────

    def _rpm_color_fill(self, p, w, h, label):
        ratio  = self._win._tel.ratio
        sr     = self._win._config.shift_ratio
        if sr <= 0:
            return
        is_f   = ratio >= sr
        hiding = is_f and not self._win._flash_on

        # Determine fill colour + alpha based on RPM zone
        fill_c: QColor | None = None
        fill_a = 0.0
        if is_f and not hiding:
            fill_c = QColor("#ff2020")
            fill_a = 0.88
        elif not is_f:
            thresh = [sr / 9, sr * 4 / 9, sr * 7 / 9]
            colors = [QColor("#22c55e"), QColor("#eab308"), QColor("#ef4444")]
            spans  = [sr * 3 / 9,        sr * 3 / 9,       sr * 2 / 9]
            for i in range(2, -1, -1):
                if ratio >= thresh[i]:
                    fill_c = colors[i]
                    fill_a = min(1.0, (ratio - thresh[i]) / spans[i]) * (0.68, 0.76, 0.86)[i]
                    break

        bx, by, bw, bh = 4, 4, w - 8, h - 8
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_GEAR_BG)
        p.drawRoundedRect(bx, by, bw, bh, 8, 8)

        if fill_c and fill_a > 0.02:
            overlay = QColor(fill_c)
            overlay.setAlphaF(fill_a)
            p.setBrush(overlay)
            p.drawRoundedRect(bx, by, bw, bh, 8, 8)
            self._glow(p, w / 2, h / 2, min(w, h) * 0.55, fill_c, fill_a * 0.55)

        border_c = QColor(fill_c.red(), fill_c.green(), fill_c.blue(), 100) \
                   if fill_c else _BORDER
        p.setPen(border_c)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(bx, by, bw, bh, 8, 8)

        if not hiding:
            p.setPen(_TEXT)
            p.setFont(QFont("Consolas", _font_size(label, int(h * 0.50)), QFont.Weight.Bold))
            p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, label)
