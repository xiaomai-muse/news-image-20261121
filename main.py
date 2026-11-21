#!/usr/bin/env python3
"""
THE WORLD IN ONE IMAGE: SATURDAY 21 NOVEMBER 2026
Deterministic 1024x1024 newsprint poster generator using Python stdlib only.
"""

from __future__ import annotations

import os
import struct
import zlib

# ============================================================================
# PALETTE
# ============================================================================

WIDTH = 1024
HEIGHT = 1024

BG_PAPER = (244, 238, 225)
BG_PANEL = (250, 246, 238)
BG_ICON = (228, 224, 214)
BG_FOOTER = (20, 24, 34)

INK_BLACK = (20, 22, 26)
INK_DARK = (48, 50, 56)
INK_MUTED = (120, 116, 108)
BORDER_LIGHT = (208, 200, 186)

ACCENT_RED = (188, 38, 34)
ACCENT_BLUE = (26, 66, 124)
ACCENT_GOLD = (208, 156, 38)
WHITE = (250, 248, 242)

# Icon-specific flat vector colors
SKY_LIGHT = (214, 226, 238)
SKY_WARM = (234, 222, 206)
SKY_INDIGO = (218, 222, 236)
GREEN_LAND = (56, 132, 86)
BLUE_OCEAN = (54, 114, 172)
STEEL_DARK = (74, 82, 94)
STEEL_LIGHT = (146, 154, 166)
SMOKE_DARK = (112, 114, 118)
SMOKE_LIGHT = (168, 168, 164)
ORANGE_FLAME = (232, 116, 30)
YELLOW_FLAME = (244, 194, 52)


# ============================================================================
# CANVAS PRIMITIVES
# ============================================================================


class Canvas:
    """1024x1024 RGB framebuffer with deterministic raster primitives."""

    def __init__(self, width: int, height: int, bg: tuple[int, int, int]) -> None:
        self.width = width
        self.height = height
        self.buf = bytearray(bytes(bg) * (width * height))
        self._clip: tuple[int, int, int, int] | None = None

    def set_clip(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self._clip = (
            max(0, x0),
            max(0, y0),
            min(self.width, x1),
            min(self.height, y1),
        )

    def clear_clip(self) -> None:
        self._clip = None

    def _bounds(self) -> tuple[int, int, int, int]:
        if self._clip is not None:
            return self._clip
        return (0, 0, self.width, self.height)

    def set_px(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        x0, y0, x1, y1 = self._bounds()
        if x0 <= x < x1 and y0 <= y < y1:
            idx = (y * self.width + x) * 3
            self.buf[idx] = color[0]
            self.buf[idx + 1] = color[1]
            self.buf[idx + 2] = color[2]

    def fill_rect(
        self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]
    ) -> None:
        bx0, by0, bx1, by1 = self._bounds()
        rx0 = max(bx0, x)
        ry0 = max(by0, y)
        rx1 = min(bx1, x + w)
        ry1 = min(by1, y + h)
        if rx0 >= rx1 or ry0 >= ry1:
            return
        span = bytes(color) * (rx1 - rx0)
        stride = self.width * 3
        row_len = (rx1 - rx0) * 3
        for row in range(ry0, ry1):
            start = row * stride + rx0 * 3
            self.buf[start : start + row_len] = span

    def stroke_rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int],
        thickness: int = 1,
    ) -> None:
        if w <= 0 or h <= 0 or thickness <= 0:
            return
        t = min(thickness, w, h)
        self.fill_rect(x, y, w, t, color)
        self.fill_rect(x, y + h - t, w, t, color)
        self.fill_rect(x, y, t, h, color)
        self.fill_rect(x + w - t, y, t, h, color)

    def fill_circle(
        self, cx: int, cy: int, r: int, color: tuple[int, int, int]
    ) -> None:
        if r < 0:
            return
        if r == 0:
            self.set_px(cx, cy, color)
            return
        bx0, by0, bx1, by1 = self._bounds()
        ry0 = max(by0, cy - r)
        ry1 = min(by1 - 1, cy + r)
        r2 = r * r
        stride = self.width * 3
        c_bytes = bytes(color)
        for py in range(ry0, ry1 + 1):
            dy = py - cy
            dx_max = int((r2 - dy * dy) ** 0.5)
            rx0 = max(bx0, cx - dx_max)
            rx1 = min(bx1 - 1, cx + dx_max)
            if rx0 <= rx1:
                count = rx1 - rx0 + 1
                start = py * stride + rx0 * 3
                self.buf[start : start + count * 3] = c_bytes * count

    def stroke_circle(
        self,
        cx: int,
        cy: int,
        r: int,
        color: tuple[int, int, int],
        thickness: int = 2,
    ) -> None:
        if r <= 0 or thickness <= 0:
            return
        r_out = r
        r_in = max(0, r - thickness)
        r_out2 = r_out * r_out
        r_in2 = r_in * r_in
        bx0, by0, bx1, by1 = self._bounds()
        ry0 = max(by0, cy - r_out)
        ry1 = min(by1 - 1, cy + r_out)
        rx0_lim = max(bx0, cx - r_out)
        rx1_lim = min(bx1 - 1, cx + r_out)
        for py in range(ry0, ry1 + 1):
            dy2 = (py - cy) * (py - cy)
            for px in range(rx0_lim, rx1_lim + 1):
                d2 = (px - cx) * (px - cx) + dy2
                if r_in2 <= d2 <= r_out2:
                    self.set_px(px, py, color)

    def draw_line(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: tuple[int, int, int],
        thickness: int = 1,
    ) -> None:
        """Bresenham line with uniform circular brush for thickness > 1."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        radius = thickness // 2

        while True:
            if thickness <= 1:
                self.set_px(x0, y0, color)
            elif thickness == 2:
                self.fill_rect(x0, y0, 2, 2, color)
            else:
                self.fill_circle(x0, y0, radius, color)

            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_polygon(
        self, points: list[tuple[int, int]], color: tuple[int, int, int]
    ) -> None:
        """Scanline polygon fill."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        bx0, by0, bx1, by1 = self._bounds()
        ymin = max(by0, min(ys))
        ymax = min(by1 - 1, max(ys))
        n = len(points)
        stride = self.width * 3
        c_bytes = bytes(color)

        for py in range(ymin, ymax + 1):
            xs: list[float] = []
            for i in range(n):
                x0, y0 = points[i]
                x1, y1 = points[(i + 1) % n]
                if (y0 <= py < y1) or (y1 <= py < y0):
                    x_int = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
                    xs.append(x_int)
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                lx = max(bx0, int(xs[i] + 0.5))
                rx = min(bx1 - 1, int(xs[i + 1] + 0.5))
                if lx <= rx:
                    count = rx - lx + 1
                    start = py * stride + lx * 3
                    self.buf[start : start + count * 3] = c_bytes * count


# ============================================================================
# PNG ENCODER
# ============================================================================


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def encode_png(canvas: Canvas) -> bytes:
    """Encode an RGB Canvas into a deterministic PNG byte stream."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(
        ">IIBBBBB", canvas.width, canvas.height, 8, 2, 0, 0, 0
    )
    ihdr = _png_chunk(b"IHDR", ihdr_data)

    row_bytes = canvas.width * 3
    raw = bytearray((row_bytes + 1) * canvas.height)
    src = canvas.buf
    for y in range(canvas.height):
        src_start = y * row_bytes
        dst_start = y * (row_bytes + 1)
        raw[dst_start] = 0  # Filter type 0 (None)
        raw[dst_start + 1 : dst_start + 1 + row_bytes] = src[
            src_start : src_start + row_bytes
        ]

    compressed = zlib.compress(bytes(raw), level=9)
    idat = _png_chunk(b"IDAT", compressed)
    iend = _png_chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


# ============================================================================
# FONT (7x11 STROKE VECTOR GLYPHS)
# ============================================================================

# Each glyph is a list of polylines on a 7-wide (x: 0..6) by 11-tall (y: 0..10) grid.
GLYPH_W = 7
GLYPH_H = 11

FONT_GLYPHS: dict[str, list[list[tuple[int, int]]]] = {
    " ": [],
    "A": [[(0, 10), (3, 0), (6, 10)], [(1, 7), (5, 7)]],
    "B": [
        [(0, 10), (0, 0), (4, 0), (6, 2), (6, 3), (4, 5), (0, 5)],
        [(4, 5), (6, 7), (6, 8), (4, 10), (0, 10)],
    ],
    "C": [[(6, 2), (4, 0), (2, 0), (0, 2), (0, 8), (2, 10), (4, 10), (6, 8)]],
    "D": [[(0, 10), (0, 0), (4, 0), (6, 2), (6, 8), (4, 10), (0, 10)]],
    "E": [[(6, 0), (0, 0), (0, 10), (6, 10)], [(0, 5), (4, 5)]],
    "F": [[(6, 0), (0, 0), (0, 10)], [(0, 5), (4, 5)]],
    "G": [
        [(6, 2), (4, 0), (2, 0), (0, 2), (0, 8), (2, 10), (5, 10), (6, 8), (6, 5), (3, 5)]
    ],
    "H": [[(0, 0), (0, 10)], [(6, 0), (6, 10)], [(0, 5), (6, 5)]],
    "I": [[(1, 0), (5, 0)], [(3, 0), (3, 10)], [(1, 10), (5, 10)]],
    "J": [[(1, 0), (6, 0)], [(5, 0), (5, 8), (3, 10), (1, 10), (0, 8)]],
    "K": [[(0, 0), (0, 10)], [(6, 0), (0, 6)], [(2, 4), (6, 10)]],
    "L": [[(0, 0), (0, 10), (6, 10)]],
    "M": [[(0, 10), (0, 0), (3, 5), (6, 0), (6, 10)]],
    "N": [[(0, 10), (0, 0), (6, 10), (6, 0)]],
    "O": [[(2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (2, 10), (0, 8), (0, 2), (2, 0)]],
    "P": [[(0, 10), (0, 0), (4, 0), (6, 2), (6, 4), (4, 6), (0, 6)]],
    "Q": [
        [(2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (2, 10), (0, 8), (0, 2), (2, 0)],
        [(4, 7), (6, 10)],
    ],
    "R": [
        [(0, 10), (0, 0), (4, 0), (6, 2), (6, 4), (4, 5), (0, 5)],
        [(3, 5), (6, 10)],
    ],
    "S": [
        [(6, 2), (4, 0), (2, 0), (0, 2), (0, 3), (2, 5), (4, 5), (6, 7), (6, 8), (4, 10), (2, 10), (0, 8)]
    ],
    "T": [[(0, 0), (6, 0)], [(3, 0), (3, 10)]],
    "U": [[(0, 0), (0, 8), (2, 10), (4, 10), (6, 8), (6, 0)]],
    "V": [[(0, 0), (3, 10), (6, 0)]],
    "W": [[(0, 0), (1, 10), (3, 5), (5, 10), (6, 0)]],
    "X": [[(0, 0), (6, 10)], [(6, 0), (0, 10)]],
    "Y": [[(0, 0), (3, 5), (6, 0)], [(3, 5), (3, 10)]],
    "Z": [[(0, 0), (6, 0), (0, 10), (6, 10)]],
    "0": [
        [(2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (2, 10), (0, 8), (0, 2), (2, 0)],
        [(1, 8), (5, 2)],
    ],
    "1": [[(1, 2), (3, 0), (3, 10)], [(1, 10), (5, 10)]],
    "2": [[(0, 2), (2, 0), (4, 0), (6, 2), (6, 4), (0, 10), (6, 10)]],
    "3": [
        [(0, 1), (2, 0), (4, 0), (6, 2), (6, 3), (4, 5), (2, 5)],
        [(4, 5), (6, 7), (6, 8), (4, 10), (2, 10), (0, 9)],
    ],
    "4": [[(5, 10), (5, 0), (0, 6), (6, 6)]],
    "5": [[(6, 0), (0, 0), (0, 4), (4, 4), (6, 6), (6, 8), (4, 10), (1, 10), (0, 9)]],
    "6": [
        [(5, 0), (2, 0), (0, 2), (0, 8), (2, 10), (4, 10), (6, 8), (6, 6), (4, 4), (0, 4)]
    ],
    "7": [[(0, 0), (6, 0), (2, 10)]],
    "8": [
        [(2, 0), (4, 0), (6, 2), (6, 3), (4, 5), (2, 5), (0, 3), (0, 2), (2, 0)],
        [(2, 5), (0, 7), (0, 8), (2, 10), (4, 10), (6, 8), (6, 7), (4, 5)],
    ],
    "9": [
        [(6, 6), (2, 6), (0, 4), (0, 2), (2, 0), (4, 0), (6, 2), (6, 8), (4, 10), (1, 10)]
    ],
    ".": [[(2, 9), (3, 9), (3, 10), (2, 10), (2, 9)]],
    ",": [[(3, 8), (3, 9), (2, 11)]],
    ":": [[(2, 3), (3, 3), (3, 4), (2, 4)], [(2, 8), (3, 8), (3, 9), (2, 9)]],
    ";": [[(2, 3), (3, 3), (3, 4), (2, 4)], [(3, 8), (3, 9), (2, 11)]],
    "'": [[(3, 0), (3, 3)]],
    "-": [[(1, 5), (5, 5)]],
    "/": [[(5, 0), (1, 10)]],
    "(": [[(4, 0), (2, 2), (2, 8), (4, 10)]],
    ")": [[(2, 0), (4, 2), (4, 8), (2, 10)]],
    "%": [
        [(0, 1), (1, 1), (1, 2), (0, 2), (0, 1)],
        [(5, 0), (1, 10)],
        [(5, 8), (6, 8), (6, 9), (5, 9), (5, 8)],
    ],
    "$": [
        [(6, 2), (4, 1), (2, 1), (0, 2), (0, 4), (2, 5), (4, 5), (6, 6), (6, 8), (4, 9), (2, 9), (0, 8)],
        [(3, 0), (3, 10)],
    ],
    "&": [
        [(6, 10), (1, 4), (1, 1), (2, 0), (4, 0), (5, 1), (5, 3), (0, 7), (0, 9), (2, 10), (4, 10), (6, 7)]
    ],
    "+": [[(3, 2), (3, 8)], [(0, 5), (6, 5)]],
    "!": [[(3, 0), (3, 7)], [(3, 9), (3, 10)]],
    "?": [[(1, 2), (2, 0), (4, 0), (6, 2), (5, 4), (3, 5), (3, 7)], [(3, 9), (3, 10)]],
    "\u2022": [[(2, 4), (4, 4), (4, 6), (2, 6), (2, 4)]],
}


# ============================================================================
# TEXT HELPERS
# ============================================================================


def char_advance(scale: int | float, spacing: int | None = None) -> int:
    sp = round(scale) if spacing is None else spacing
    return round(GLYPH_W * scale) + sp


def measure_text(text: str, scale: int | float, spacing: int | None = None) -> int:
    if not text:
        return 0
    sp = round(scale) if spacing is None else spacing
    return len(text) * round(GLYPH_W * scale) + (len(text) - 1) * sp


def draw_text(
    canvas: Canvas,
    x: int,
    y: int,
    text: str,
    scale: int | float,
    color: tuple[int, int, int],
    thickness: int = 2,
    spacing: int | None = None,
) -> None:
    adv = char_advance(scale, spacing)
    cx = x
    for ch in text.upper():
        strokes = FONT_GLYPHS.get(ch, FONT_GLYPHS[" "])
        for poly in strokes:
            for i in range(len(poly) - 1):
                px0 = round(cx + poly[i][0] * scale)
                py0 = round(y + poly[i][1] * scale)
                px1 = round(cx + poly[i + 1][0] * scale)
                py1 = round(y + poly[i + 1][1] * scale)
                canvas.draw_line(px0, py0, px1, py1, color, thickness=thickness)
        cx += adv


def wrap_text(
    text: str, max_width: int, scale: int | float, spacing: int | None = None
) -> list[str]:
    """Greedy word-wrap using measure_text."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for word in words:
        cand = word if not cur else f"{cur} {word}"
        if measure_text(cand, scale, spacing) <= max_width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ============================================================================
# MASTHEAD
# ============================================================================


def draw_masthead(canvas: Canvas) -> None:
    """Top newspaper masthead band: y=20..158."""
    x0, x1 = 24, WIDTH - 24
    w = x1 - x0

    # Top thick rule + thin accent rule
    canvas.fill_rect(x0, 20, w, 4, INK_BLACK)
    canvas.fill_rect(x0, 27, w, 1, ACCENT_RED)

    # Overline
    overline = "THE WORLD IN ONE IMAGE"
    ov_scale = 2
    ov_w = measure_text(overline, ov_scale, spacing=3)
    draw_text(
        canvas,
        (WIDTH - ov_w) // 2,
        36,
        overline,
        ov_scale,
        ACCENT_RED,
        thickness=3,
        spacing=3,
    )

    # Big title
    title = "SATURDAY 21 NOVEMBER 2026"
    t_scale = 4
    t_sp = 4
    t_w = measure_text(title, t_scale, spacing=t_sp)
    draw_text(
        canvas,
        (WIDTH - t_w) // 2,
        66,
        title,
        t_scale,
        INK_BLACK,
        thickness=5,
        spacing=t_sp,
    )

    # Subline
    subline = "SIX STORIES THAT DEFINED THE DAY"
    s_scale = 2
    s_sp = 2
    s_w = measure_text(subline, s_scale, spacing=s_sp)
    draw_text(
        canvas,
        (WIDTH - s_w) // 2,
        122,
        subline,
        s_scale,
        ACCENT_BLUE,
        thickness=2,
        spacing=s_sp,
    )

    # Bottom double rule
    canvas.fill_rect(x0, 152, w, 3, INK_BLACK)
    canvas.fill_rect(x0, 157, w, 1, ACCENT_GOLD)


# ============================================================================
# FOOTER
# ============================================================================

FOOTER_ITEMS = [
    "GUPTA JAILED 19 YEARS IN PANNUN PLOT",
    "MYANMAR REJECTS ICJ GENOCIDE RULING",
    "INDIA V NZ: DAY 3 OF 1ST TEST",
    "IRAN CLAIMS WATERS BEYOND HORMUZ",
    "TRUMP FLOATS CHIEF OF STAFF FOR 2028",
]


def draw_footer(canvas: Canvas) -> None:
    """Dark bottom ticker strip: y=928..1004."""
    fy0 = 928
    fh = 76
    canvas.fill_rect(24, fy0, WIDTH - 48, fh, BG_FOOTER)
    canvas.fill_rect(24, fy0, WIDTH - 48, 3, ACCENT_GOLD)

    sp = 2
    f_scale = 1.5
    lines = [
        " \u2022 ".join(FOOTER_ITEMS[:2]),
        " \u2022 ".join(FOOTER_ITEMS[2:4]),
        FOOTER_ITEMS[4],
    ]

    y_start = fy0 + 9
    line_step = 21
    for i, line in enumerate(lines):
        lw = measure_text(line, scale=f_scale, spacing=sp)
        lx = (WIDTH - lw) // 2
        ly = y_start + i * line_step
        # Draw text, highlighting bullet characters in gold
        adv = char_advance(f_scale, sp)
        cx = lx
        for ch in line:
            col = ACCENT_GOLD if ch == "\u2022" else WHITE
            draw_text(canvas, cx, ly, ch, scale=f_scale, color=col, thickness=2, spacing=sp)
            cx += adv


# ============================================================================
# ICONS
# ============================================================================


def _draw_icon_poland(canvas: Canvas, x0: int, y0: int, w: int, h: int) -> None:
    """Missile streaking across sky above a shield."""
    canvas.fill_rect(x0, y0, w, h, SKY_LIGHT)
    # Soft cloud band
    canvas.fill_circle(x0 + 28, y0 + 36, 14, WHITE)
    canvas.fill_circle(x0 + 44, y0 + 32, 16, WHITE)
    canvas.fill_circle(x0 + 60, y0 + 38, 12, WHITE)

    # Heraldic shield (bottom-center)
    scx = x0 + w // 2
    sy = y0 + 58
    shield_outer = [
        (scx - 24, sy),
        (scx + 24, sy),
        (scx + 24, sy + 24),
        (scx, sy + 50),
        (scx - 24, sy + 24),
    ]
    canvas.fill_polygon(shield_outer, ACCENT_BLUE)
    shield_inner = [
        (scx - 18, sy + 5),
        (scx + 18, sy + 5),
        (scx + 18, sy + 22),
        (scx, sy + 42),
        (scx - 18, sy + 22),
    ]
    canvas.fill_polygon(shield_inner, WHITE)
    # Lower half red (Polish colors inside shield)
    shield_red = [
        (scx - 18, sy + 22),
        (scx + 18, sy + 22),
        (scx, sy + 42),
    ]
    canvas.fill_polygon(shield_red, ACCENT_RED)

    # Contrail streak
    canvas.draw_line(x0 + 14, y0 + 46, x0 + 76, y0 + 24, WHITE, thickness=5)
    # Exhaust flame
    flame = [(x0 + 56, y0 + 31), (x0 + 78, y0 + 20), (x0 + 80, y0 + 28)]
    canvas.fill_polygon(flame, ORANGE_FLAME)
    # Missile body (diagonal top-right)
    body = [
        (x0 + 74, y0 + 21),
        (x0 + 104, y0 + 11),
        (x0 + 107, y0 + 19),
        (x0 + 77, y0 + 29),
    ]
    canvas.fill_polygon(body, STEEL_DARK)
    # Nose cone
    nose = [(x0 + 104, y0 + 11), (x0 + 118, y0 + 10), (x0 + 107, y0 + 19)]
    canvas.fill_polygon(nose, ACCENT_RED)
    # Tail fins
    fin_top = [(x0 + 74, y0 + 21), (x0 + 68, y0 + 14), (x0 + 82, y0 + 18)]
    fin_bot = [(x0 + 77, y0 + 29), (x0 + 76, y0 + 36), (x0 + 86, y0 + 26)]
    canvas.fill_polygon(fin_top, ACCENT_RED)
    canvas.fill_polygon(fin_bot, ACCENT_RED)


def _draw_icon_climate(canvas: Canvas, x0: int, y0: int, w: int, h: int) -> None:
    """Globe with a thermometer beside it."""
    canvas.fill_rect(x0, y0, w, h, SKY_LIGHT)
    gx = x0 + 48
    gy = y0 + h // 2
    gr = 36

    # Ocean
    canvas.fill_circle(gx, gy, gr, BLUE_OCEAN)
    # Continents (kept well inside radius)
    c1 = [(gx - 22, gy - 16), (gx - 4, gy - 22), (gx + 4, gy - 6), (gx - 12, gy + 4), (gx - 24, gy - 4)]
    c2 = [(gx + 8, gy - 14), (gx + 24, gy - 8), (gx + 20, gy + 10), (gx + 4, gy + 6)]
    c3 = [(gx - 10, gy + 10), (gx + 4, gy + 14), (gx - 2, gy + 26), (gx - 14, gy + 20)]
    canvas.fill_polygon(c1, GREEN_LAND)
    canvas.fill_polygon(c2, GREEN_LAND)
    canvas.fill_polygon(c3, GREEN_LAND)
    # Globe outline
    canvas.stroke_circle(gx, gy, gr, INK_BLACK, thickness=3)

    # Thermometer on the right
    tx = x0 + 104
    t_top = y0 + 18
    t_bot = y0 + 88
    # Outer dark casing
    canvas.draw_line(tx, t_top, tx, t_bot, INK_BLACK, thickness=14)
    canvas.fill_circle(tx, t_bot + 4, 13, INK_BLACK)
    # Inner white tube
    canvas.draw_line(tx, t_top + 1, tx, t_bot, WHITE, thickness=9)
    # Red mercury bulb + high column
    canvas.fill_circle(tx, t_bot + 4, 9, ACCENT_RED)
    canvas.draw_line(tx, t_top + 14, tx, t_bot + 2, ACCENT_RED, thickness=5)
    # Scale ticks
    for ty in range(t_top + 12, t_bot - 6, 12):
        canvas.draw_line(tx - 12, ty, tx - 7, ty, INK_BLACK, thickness=2)


def _draw_icon_business(canvas: Canvas, x0: int, y0: int, w: int, h: int) -> None:
    """Falling bar chart with a downward arrow."""
    canvas.fill_rect(x0, y0, w, h, BG_ICON)
    # Subtle chart grid lines
    for gy in (y0 + 26, y0 + 50, y0 + 74, y0 + 98):
        canvas.draw_line(x0 + 12, gy, x0 + w - 12, gy, BORDER_LIGHT, thickness=2)

    base_y = y0 + 104
    heights = [68, 52, 36, 20]
    bar_w = 18
    gap = 8
    start_x = x0 + 18
    for i, bh in enumerate(heights):
        bx = start_x + i * (bar_w + gap)
        col = ACCENT_RED if i == len(heights) - 1 else ACCENT_BLUE
        canvas.fill_rect(bx, base_y - bh, bar_w, bh, col)

    # Baseline
    canvas.draw_line(x0 + 12, base_y, x0 + w - 12, base_y, INK_BLACK, thickness=3)

    # Downward red arrow above bars
    pts = [(x0 + 20, y0 + 18), (x0 + 58, y0 + 36), (x0 + 76, y0 + 28), (x0 + 108, y0 + 62)]
    for i in range(len(pts) - 1):
        canvas.draw_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], ACCENT_RED, thickness=5)
    # Arrowhead
    head = [(x0 + 114, y0 + 68), (x0 + 96, y0 + 66), (x0 + 110, y0 + 50)]
    canvas.fill_polygon(head, ACCENT_RED)


def _draw_icon_games(canvas: Canvas, x0: int, y0: int, w: int, h: int) -> None:
    """Game controller above gold coins."""
    canvas.fill_rect(x0, y0, w, h, SKY_INDIGO)

    # Gold coins at bottom (drawn first)
    coin_y = y0 + 92
    for cx in (x0 + 36, x0 + 66, x0 + 96):
        canvas.fill_circle(cx, coin_y, 15, ACCENT_GOLD)
        canvas.stroke_circle(cx, coin_y, 15, INK_BLACK, thickness=2)
        canvas.draw_line(cx, coin_y - 7, cx, coin_y + 7, INK_BLACK, thickness=2)

    # Game controller above coins
    gy = y0 + 36
    # Grips
    canvas.fill_circle(x0 + 36, gy + 18, 16, STEEL_DARK)
    canvas.fill_circle(x0 + 98, gy + 18, 16, STEEL_DARK)
    # Main body
    canvas.fill_rect(x0 + 34, gy - 4, 66, 30, STEEL_DARK)
    canvas.fill_circle(x0 + 36, gy + 10, 15, STEEL_DARK)
    canvas.fill_circle(x0 + 98, gy + 10, 15, STEEL_DARK)
    # D-pad on left
    canvas.fill_rect(x0 + 30, gy + 8, 16, 5, WHITE)
    canvas.fill_rect(x0 + 35, gy + 3, 5, 16, WHITE)
    # Action buttons on right
    canvas.fill_circle(x0 + 98, gy + 4, 3, ACCENT_RED)
    canvas.fill_circle(x0 + 104, gy + 10, 3, ACCENT_GOLD)
    canvas.fill_circle(x0 + 98, gy + 16, 3, ACCENT_BLUE)
    canvas.fill_circle(x0 + 92, gy + 10, 3, GREEN_LAND)
    # Center bridge buttons
    canvas.fill_rect(x0 + 58, gy + 8, 6, 4, STEEL_LIGHT)
    canvas.fill_rect(x0 + 70, gy + 8, 6, 4, STEEL_LIGHT)


def _draw_icon_saudi(canvas: Canvas, x0: int, y0: int, w: int, h: int) -> None:
    """Tall skyscraper with a smoke plume."""
    canvas.fill_rect(x0, y0, w, h, SKY_WARM)

    # Smoke plume (drawn behind/around upper-right)
    smoke_blobs = [
        (x0 + 66, y0 + 48, 11, SMOKE_DARK),
        (x0 + 78, y0 + 38, 13, SMOKE_DARK),
        (x0 + 92, y0 + 28, 15, SMOKE_LIGHT),
        (x0 + 108, y0 + 20, 14, SMOKE_LIGHT),
    ]
    for sx, sy, sr, scol in smoke_blobs:
        canvas.fill_circle(sx, sy, sr, scol)

    # Tall tapered skyscraper on left-center
    tx = x0 + 44
    base_y = y0 + 112
    tower = [
        (tx - 16, base_y),
        (tx - 12, y0 + 30),
        (tx, y0 + 16),
        (tx + 12, y0 + 30),
        (tx + 16, base_y),
    ]
    canvas.fill_polygon(tower, ACCENT_BLUE)
    # Spire
    canvas.draw_line(tx, y0 + 8, tx, y0 + 20, INK_BLACK, thickness=3)
    # Windows
    for wy in range(y0 + 38, base_y - 8, 11):
        canvas.fill_rect(tx - 7, wy, 5, 6, SKY_LIGHT)
        canvas.fill_rect(tx + 2, wy, 5, 6, SKY_LIGHT)

    # Impact flash on right side of upper tower
    flash = [(tx + 10, y0 + 46), (tx + 26, y0 + 42), (tx + 18, y0 + 56)]
    canvas.fill_polygon(flash, ORANGE_FLAME)
    canvas.fill_circle(tx + 14, y0 + 49, 5, YELLOW_FLAME)


def _draw_icon_bangladesh(canvas: Canvas, x0: int, y0: int, w: int, h: int) -> None:
    """Building with flames."""
    canvas.fill_rect(x0, y0, w, h, SKY_WARM)

    # Smoke above
    canvas.fill_circle(x0 + 54, y0 + 24, 12, SMOKE_LIGHT)
    canvas.fill_circle(x0 + 72, y0 + 20, 14, SMOKE_DARK)
    canvas.fill_circle(x0 + 88, y0 + 26, 11, SMOKE_LIGHT)

    # Building (drawn before foreground flames)
    bx = x0 + 28
    by = y0 + 54
    bw = 78
    bh = 56
    canvas.fill_rect(bx, by, bw, bh, STEEL_DARK)
    canvas.fill_rect(bx - 4, by - 6, bw + 8, 8, INK_BLACK)
    # Doorway and windows
    canvas.fill_rect(bx + 32, by + 34, 14, 22, INK_BLACK)
    for wx in (bx + 10, bx + 32, bx + 54):
        canvas.fill_rect(wx, by + 10, 14, 14, YELLOW_FLAME)

    # Flames rising from roof and sides
    flames_outer = [
        [(bx + 8, by - 4), (bx + 18, by - 30), (bx + 28, by - 4)],
        [(bx + 26, by - 4), (bx + 40, by - 36), (bx + 54, by - 4)],
        [(bx + 48, by - 4), (bx + 62, by - 28), (bx + 72, by - 4)],
    ]
    for poly in flames_outer:
        canvas.fill_polygon(poly, ACCENT_RED)

    flames_inner = [
        [(bx + 12, by - 4), (bx + 18, by - 20), (bx + 24, by - 4)],
        [(bx + 32, by - 4), (bx + 40, by - 26), (bx + 48, by - 4)],
        [(bx + 53, by - 4), (bx + 62, by - 18), (bx + 68, by - 4)],
    ]
    for poly in flames_inner:
        canvas.fill_polygon(poly, ORANGE_FLAME)


ICON_DRAWERS = {
    "POLAND": _draw_icon_poland,
    "CLIMATE": _draw_icon_climate,
    "BUSINESS": _draw_icon_business,
    "GAMES": _draw_icon_games,
    "SAUDI": _draw_icon_saudi,
    "BANGLADESH": _draw_icon_bangladesh,
}


# ============================================================================
# PANELS
# ============================================================================

STORIES = [
    {
        "kicker": "POLAND",
        "headline": "RUSSIAN MISSILES LAND IN POLAND",
        "deck": "WARSAW CALLS IT PROVOCATION; NATO JETS SCRAMBLED",
    },
    {
        "kicker": "CLIMATE",
        "headline": "COP31 TALKS AT CRUNCH TIME",
        "deck": "NO DEAL IN SIGHT AS SUMMIT NEARS END",
    },
    {
        "kicker": "BUSINESS",
        "headline": "ANTHROPIC SLIDES 9% AFTER IPO",
        "deck": "SHARES FALL DAY AFTER RECORD DEBUT",
    },
    {
        "kicker": "GAMES",
        "headline": "GTA VI HAULS $3.79 BILLION IN A DAY",
        "deck": "RECORD FIRST-DAY RETAIL SALES",
    },
    {
        "kicker": "SAUDI",
        "headline": "HOUTHIS HIT RIYADH TOWER",
        "deck": "REBELS CLAIM NEW STRIKES ON SAUDI ARABIA",
    },
    {
        "kicker": "BANGLADESH",
        "headline": "FRESH ARSON IN BANGLADESH UNREST",
        "deck": "VIOLENCE FLARES BEFORE HASINA RETURN",
    },
]


def draw_panel(
    canvas: Canvas, px: int, py: int, pw: int, ph: int, story: dict[str, str]
) -> None:
    """Draw a single story panel with kicker, headline, icon box, and deck."""
    canvas.fill_rect(px, py, pw, ph, BG_PANEL)
    canvas.stroke_rect(px, py, pw, ph, BORDER_LIGHT, thickness=2)
    # Top accent bar on panel
    canvas.fill_rect(px, py, pw, 4, ACCENT_BLUE)

    pad = 14
    icon_w = 134
    icon_h = 120
    ix = px + pw - pad - icon_w
    iy = py + 14

    # Icon box with strict clipping
    canvas.set_clip(ix, iy, ix + icon_w, iy + icon_h)
    ICON_DRAWERS[story["kicker"]](canvas, ix, iy, icon_w, icon_h)
    canvas.clear_clip()
    canvas.stroke_rect(ix, iy, icon_w, icon_h, BORDER_LIGHT, thickness=2)

    # Left text area beside icon
    tx = px + pad
    text_w = ix - tx - 12

    # Kicker
    draw_text(
        canvas,
        tx,
        py + 16,
        story["kicker"],
        scale=2,
        color=ACCENT_RED,
        thickness=3,
        spacing=2,
    )

    # Headline (at most 2 lines, scale 2, bold thickness=3)
    h_lines = wrap_text(story["headline"], text_w, scale=2, spacing=2)
    hy = py + 48
    for line in h_lines[:2]:
        draw_text(
            canvas,
            tx,
            hy,
            line,
            scale=2,
            color=INK_BLACK,
            thickness=3,
            spacing=2,
        )
        hy += 32

    # Subtle divider above deck
    div_y = py + 144
    canvas.fill_rect(px + pad, div_y, pw - 2 * pad, 1, BORDER_LIGHT)

    # Deck (at most 2 lines, full panel width, scale 2, thickness=2)
    deck_w = pw - 2 * pad
    d_lines = wrap_text(story["deck"], deck_w, scale=2, spacing=2)
    dy = div_y + 12
    for line in d_lines[:2]:
        draw_text(
            canvas,
            px + pad,
            dy,
            line,
            scale=2,
            color=INK_DARK,
            thickness=2,
            spacing=2,
        )
        dy += 30


# ============================================================================
# RENDER
# ============================================================================


def render_poster() -> Canvas:
    canvas = Canvas(WIDTH, HEIGHT, BG_PAPER)
    draw_masthead(canvas)

    # 2-column x 3-row grid
    margin_x = 24
    col_gap = 12
    row_gap = 14
    pw = (WIDTH - 2 * margin_x - col_gap) // 2  # 482
    top_y = 172
    bottom_y = 914
    ph = (bottom_y - top_y - 2 * row_gap) // 3  # 238

    for idx, story in enumerate(STORIES):
        col = idx % 2
        row = idx // 2
        px = margin_x + col * (pw + col_gap)
        py = top_y + row * (ph + row_gap)
        draw_panel(canvas, px, py, pw, ph, story)

    draw_footer(canvas)
    return canvas


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")

    canvas = render_poster()
    png_bytes = encode_png(canvas)
    with open(out_path, "wb") as f:
        f.write(png_bytes)


if __name__ == "__main__":
    main()
