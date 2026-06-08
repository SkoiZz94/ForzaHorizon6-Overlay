from PyQt6.QtCore  import Qt, QRectF
from PyQt6.QtGui   import (QPainter, QColor, QFont, QLinearGradient,
                            QBrush, QPainterPath)
from .base import BaseElement

_NUM_LIGHTS = 9
_UNLIT      = QColor("#1f2937")
_BAR_BG     = QColor("#1a2332")
_TEXT       = QColor("#e2e8f0")
_MUTED      = QColor("#64748b")

# Arc Gauge: HTML SA=π*0.78, sweep=π*1.44 clockwise
# QPainter convention: 0°=3 o'clock, positive=CCW, so negate the HTML angles
_ARC_START  = -180 * 0.78    # ≈ -140.4°
_ARC_SWEEP  = -180 * 1.44    # ≈ -259.2°, negative = CW


def _zone_color(i: int) -> QColor:
    """Return zone colour for light index i (0-based). Exactly 3 green / 3 yellow / 3 red."""
    if i < 3: return QColor("#22c55e")
    if i < 6: return QColor("#eab308")
    return QColor("#ef4444")


def _get_lights(ratio: float, shift_ratio: float) -> list[QColor]:
    """Return list of _NUM_LIGHTS colours: lit = zone colour, unlit = _UNLIT."""
    if ratio >= shift_ratio:
        return [QColor("#ff2020")] * _NUM_LIGHTS
    return [
        _zone_color(i) if ratio >= (i + 1) * (shift_ratio / _NUM_LIGHTS) else _UNLIT
        for i in range(_NUM_LIGHTS)
    ]


class RPMItem(BaseElement):
    def __init__(self, win, parent=None):
        super().__init__(win, "rpm", parent)

    def _paint_element(self, painter: QPainter) -> None:
        cfg         = self._win._config
        tel         = self._win._tel
        w, h        = int(self.width()), int(self.height())
        ratio       = tel.ratio
        shift_ratio = cfg.shift_ratio
        is_flash    = self._win._flash_active
        hiding      = is_flash and not self._win._flash_on
        colours     = [QColor("#ff2020")] * _NUM_LIGHTS if is_flash else _get_lights(ratio, shift_ratio)
        colour_map  = {
            "#22c55e": cfg.colour_rev_zone1,
            "#eab308": cfg.colour_rev_zone2,
            "#ef4444": cfg.colour_rev_zone3,
        }
        mapped = [
            QColor(colour_map.get(c.name(), c.name()))
            if c != _UNLIT else _UNLIT
            for c in colours
        ]

        painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 0))

        s = self._style
        if   s == "dot_row":       self._dot_row(painter, w, h, mapped, hiding)
        elif s == "cont_bar":      self._cont_bar(painter, w, h, ratio, shift_ratio, is_flash, hiding, cfg)
        elif s == "seg_tiles":     self._seg_tiles(painter, w, h, mapped, hiding)
        elif s == "arc_gauge":     self._arc_gauge(painter, w, h, ratio, shift_ratio, is_flash, hiding, cfg)
        elif s == "f1_split":      self._f1_split(painter, w, h, ratio, shift_ratio, mapped, hiding, cfg, is_flash)
        elif s == "shift_light":   self._shift_light(painter, w, h, ratio, shift_ratio, is_flash, hiding)
        elif s == "spectrum_bars": self._spectrum_bars(painter, w, h, mapped, hiding)

    # ── dot_row ─────────────────────────────────────────────────────────────

    def _dot_row(self, p, w, h, cols, hiding):
        dr  = min(14, (h - 4) // 2)
        gap = max(4, (w - _NUM_LIGHTS * dr * 2) // (_NUM_LIGHTS + 1))
        tw  = _NUM_LIGHTS * dr * 2 + (_NUM_LIGHTS - 1) * gap
        x   = (w - tw) // 2 + dr
        cy  = h // 2
        p.setPen(Qt.PenStyle.NoPen)
        for c in cols:
            if c != _UNLIT and not hiding:
                self._glow(p, x, cy, dr * 2.4, c, 0.30)
            p.setBrush(_UNLIT if hiding else c)
            p.drawEllipse(int(x - dr), int(cy - dr), dr * 2, dr * 2)
            x += dr * 2 + gap

    # ── cont_bar ────────────────────────────────────────────────────────────

    def _cont_bar(self, p, w, h, ratio, sr, is_flash, hiding, cfg):
        if sr <= 0:
            return
        px, bh = 10, max(10, int(h * 0.5))
        by = (h - bh) // 2
        bw = w - px * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(px, by, bw, bh, 5, 5)
        fw = int(bw * min(ratio / sr, 1.0))
        if fw > 0 and not hiding:
            p.save()
            path = QPainterPath()
            path.addRoundedRect(QRectF(px, by, fw, bh), 5, 5)
            p.setClipPath(path)
            if is_flash:
                p.setBrush(QColor("#ff2020"))
            else:
                gr = QLinearGradient(px, 0, px + bw, 0)
                gr.setColorAt(0.0, QColor(cfg.colour_rev_zone1))
                gr.setColorAt(0.45, QColor(cfg.colour_rev_zone2))
                gr.setColorAt(1.0, QColor(cfg.colour_rev_zone3))
                p.setBrush(QBrush(gr))
            p.drawRect(px, by, bw, bh)
            p.restore()

    # ── seg_tiles ────────────────────────────────────────────────────────────

    def _seg_tiles(self, p, w, h, cols, hiding):
        sw  = max(12, (w - 20) // _NUM_LIGHTS - 4)
        sh  = max(10, int(h * 0.65))
        gap = max(3, (w - _NUM_LIGHTS * sw) // (_NUM_LIGHTS + 1))
        tw  = _NUM_LIGHTS * sw + (_NUM_LIGHTS - 1) * gap
        x   = (w - tw) // 2
        ty  = (h - sh) // 2
        p.setPen(Qt.PenStyle.NoPen)
        for c in cols:
            p.setBrush(_UNLIT if hiding else c)
            p.drawRoundedRect(x, ty, sw, sh, 3, 3)
            x += sw + gap

    # ── arc_gauge ────────────────────────────────────────────────────────────

    def _arc_gauge(self, p, w, h, ratio, sr, is_flash, hiding, cfg):
        if sr <= 0:
            return
        cx, cy    = w / 2, h * 0.68
        outer_r   = min(w, h) * 0.46
        inner_r   = outer_r * 0.62
        # Track
        track = self._annular_arc(cx, cy, outer_r, inner_r, _ARC_START, _ARC_SWEEP)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawPath(track)
        # Fill: 80 small arc slices coloured by RPM zone
        fill_frac = min(ratio / sr, 1.0)
        if not hiding:
            segs = 80
            seg_sweep = _ARC_SWEEP / segs
            for i in range(segs):
                t = i / segs
                if t > fill_frac and not is_flash:
                    break
                seg_start = _ARC_START + i * seg_sweep
                seg_path  = self._annular_arc(cx, cy, outer_r - 1, inner_r + 1,
                                              seg_start, seg_sweep)
                if is_flash:
                    c = QColor("#ff2020")
                elif t < 0.34:
                    c = QColor(cfg.colour_rev_zone1)
                elif t < 0.67:
                    c = QColor(cfg.colour_rev_zone2)
                else:
                    c = QColor(cfg.colour_rev_zone3)
                p.setBrush(c)
                p.drawPath(seg_path)
        # Labels
        p.setFont(QFont("Consolas", max(6, int(h * 0.09)), QFont.Weight.Bold))
        p.setPen(_MUTED)
        p.drawText(QRectF(0, cy - outer_r * 0.3, w, outer_r * 0.3),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "RPM")
        rpm_val = f"{int(self._win._tel.current_rpm):,}"
        p.setPen(QColor("#ff2020") if is_flash else _TEXT)
        p.setFont(QFont("Consolas", max(7, int(h * 0.11)), QFont.Weight.Bold))
        p.drawText(QRectF(0, cy, w, outer_r * 0.4),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, rpm_val)

    # ── f1_split ─────────────────────────────────────────────────────────────

    def _f1_split(self, p, w, h, ratio, sr, cols, hiding, cfg, is_flash):
        FILL_ORDER = [4, 3, 5, 2, 6, 1, 7, 0, 8]
        lit_count  = sum(1 for c in cols if c != _UNLIT)
        dr  = min(14, (h - 4) // 2)
        gap = max(4, (w - _NUM_LIGHTS * dr * 2) // (_NUM_LIGHTS + 1))
        tw  = _NUM_LIGHTS * dr * 2 + (_NUM_LIGHTS - 1) * gap
        cx  = (w - tw) // 2 + dr
        cy  = h // 2
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(_NUM_LIGHTS):
            x    = cx + i * (dr * 2 + gap)
            rank = FILL_ORDER.index(i)
            is_lit = rank < lit_count and not hiding
            if is_lit:
                if is_flash:
                    c = QColor("#ff2020")
                else:
                    raw = _zone_color(i)
                    name = raw.name()
                    c = QColor(
                        cfg.colour_rev_zone1 if name == "#22c55e" else
                        cfg.colour_rev_zone2 if name == "#eab308" else
                        cfg.colour_rev_zone3
                    )
                self._glow(p, x, cy, dr * 2.4, c, 0.30)
                p.setBrush(c)
            else:
                p.setBrush(_UNLIT)
            p.drawEllipse(int(x - dr), int(cy - dr), dr * 2, dr * 2)

    # ── shift_light ───────────────────────────────────────────────────────────

    def _shift_light(self, p, w, h, ratio, sr, is_flash, hiding):
        cfg = self._win._config
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.38
        if   ratio >= sr:        c = QColor("#ff2020") if not hiding else _UNLIT
        elif ratio >= sr * 0.91: c = QColor(cfg.colour_rev_zone3)
        elif ratio >= sr * 0.81: c = QColor(cfg.colour_rev_zone2)
        elif ratio >= sr * 0.67: c = QColor(cfg.colour_rev_zone1)
        else:                    c = _UNLIT
        if c != _UNLIT:
            self._glow(p, cx, cy, r * 1.5, c, 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    # ── spectrum_bars ─────────────────────────────────────────────────────────

    def _spectrum_bars(self, p, w, h, cols, hiding):
        bw  = max(10, (w - 20) // _NUM_LIGHTS - 4)
        gap = max(3, (w - _NUM_LIGHTS * bw) // (_NUM_LIGHTS + 1))
        tw  = _NUM_LIGHTS * bw + (_NUM_LIGHTS - 1) * gap
        x   = (w - tw) // 2
        lbl_h  = 14
        bottom = h - lbl_h - 2
        min_h  = max(4, int(h * 0.10))
        max_h  = bottom - 2
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(cols):
            bh   = int(min_h + (max_h - min_h) * i / (_NUM_LIGHTS - 1))
            ty   = bottom - bh
            is_lit = c != _UNLIT and not hiding
            if is_lit:
                self._glow(p, x + bw / 2, ty + bh / 2, bw * 1.4, c, 0.22)
            p.setBrush(c if is_lit else _BAR_BG)
            p.drawRoundedRect(x, ty, bw, bh, 3, 3)
            x += bw + gap
