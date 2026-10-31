#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md3-wall.py — генератор обоев из тональных палитр текущей MD3-темы.

Форма — «органические» пятна (M3 любит большие мягкие формы и наслоение
surface/elevation), цвет — только роли md.sys.color.* и тона md.ref.palette.*
текущей темы. Ничего случайного: всё выводится из source color.

  python3 tools/md3-wall.py                     # wallpapers/md3-{dark,light}.svg
  python3 tools/md3-wall.py --size 3840x2160
  python3 tools/md3-wall.py --png               # + конвертация, если есть чем

Конвертация в PNG (опционально, ищется по порядку):
  rsvg-convert · inkscape · convert (ImageMagick) · magick · cairosvg · Pillow+svglib
Если ничего нет — остаётся .svg (feh/nitrogen/hyprpaper его понимают).
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from md3_theme import Config, Theme, hex_to_rgb  # noqa: E402

ROOT = HERE.parent
WALL_DIR = ROOT / "wallpapers"


def blob_path(cx: float, cy: float, r: float, points: int = 9,
              wobble: float = 0.18, phase: float = 0.0) -> str:
    """
    Замкнутая органическая форма: радиус модулируется суммой синусоид
    (детерминированно — никакого random, чтобы обои были воспроизводимы).
    Возвращает path из кубических кривых Безье.
    """
    pts = _ctrl_points(cx, cy, r, points, wobble, phase)

    d = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    n = len(pts)
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        # Catmull-Rom → Bezier
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append(f"C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    d.append("Z")
    return " ".join(d)


def theme_shapes(theme: Theme, w: int, h: int):
    """Единый список форм (SVG и PNG рендерят одну и ту же геометрию)."""
    R, pal = theme.roles, theme.palettes
    dark = theme.dark
    return [
        # (цвет, центр x, центр y, радиус, wobble, phase, opacity)
        (R["primaryContainer"],   w * 0.22, h * 0.30, h * 0.62, 0.16, 0.4, 0.95),
        (R["secondaryContainer"], w * 0.78, h * 0.22, h * 0.50, 0.20, 2.1, 0.85),
        (R["tertiaryContainer"],  w * 0.66, h * 0.86, h * 0.52, 0.18, 4.2, 0.80),
        (theme.elevation[3],      w * 0.44, h * 0.62, h * 0.34, 0.22, 1.3, 0.85),
        (R["primary"],            w * 0.12, h * 0.92, h * 0.22, 0.24, 3.0, 0.55),
        (pal["neutralVariant"]["70" if not dark else "30"], w * 0.93, h * 0.62, h * 0.30, 0.19, 5.1, 0.55),
    ]


def _ctrl_points(cx, cy, r, points=9, wobble=0.18, phase=0.0):
    ctrl = []
    for i in range(points):
        a = phase + 2 * math.pi * i / points
        k = 1.0 + wobble * (
            0.55 * math.sin(3 * a + phase)
            + 0.30 * math.sin(5 * a - 1.1)
            + 0.15 * math.sin(2 * a + 0.7)
        )
        ctrl.append((cx + r * k * math.cos(a), cy + r * k * math.sin(a)))
    return ctrl


def _subdivide(ctrl, per=14):
    """Catmull-Rom по контрольным точкам → плотный полигон (гладкий контур)."""
    out = []
    n = len(ctrl)
    for i in range(n):
        p0 = ctrl[(i - 1) % n]; p1 = ctrl[i]
        p2 = ctrl[(i + 1) % n]; p3 = ctrl[(i + 2) % n]
        for t_i in range(per):
            t = t_i / per
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def build_svg(theme: Theme, w: int, h: int) -> str:
    R = theme.roles
    pal = theme.palettes
    dark = theme.dark

    base = R["surface"]
    shapes = theme_shapes(theme, w, h)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" version="1.1">',
        f'  <!-- Material Design 3 wallpaper · source {theme.seed} · '
        f'{theme.scheme}/{theme.contrast}/{"dark" if dark else "light"} -->',
        f'  <rect width="{w}" height="{h}" fill="{base}"/>',
    ]

    defs = []
    for i, (color, cx, cy, r, wob, ph, op) in enumerate(shapes):
        rgb = hex_to_rgb(color)
        lighter = "#{:02x}{:02x}{:02x}".format(*(min(255, int(c * 1.12 + 8)) for c in rgb))
        gid = f"g{i}"
        defs.append(
            f'    <radialGradient id="{gid}" cx="38%" cy="32%" r="78%">'
            f'<stop offset="0%" stop-color="{lighter}"/>'
            f'<stop offset="100%" stop-color="{color}"/></radialGradient>'
        )
        parts.append(
            f'  <path d="{blob_path(cx, cy, r, 9, wob, ph)}" '
            f'fill="url(#{gid})" opacity="{op:.2f}"/>'
        )

    # «elevation ring»: тонкое кольцо primary — акцент M3
    parts.append(
        f'  <circle cx="{w*0.22:.0f}" cy="{h*0.30:.0f}" r="{h*0.30:.0f}" '
        f'fill="none" stroke="{R["primary"]}" stroke-opacity="0.22" stroke-width="{max(2, h//600)}"/>'
    )

    # тональная шкала md.ref.palette — узкая полоса снизу (тон 0..100)
    tones = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100]
    strip_h = max(8, h // 110)
    cell = w / len(tones)
    for i, t in enumerate(tones):
        parts.append(
            f'  <rect x="{i*cell:.1f}" y="{h - strip_h}" width="{cell + 0.6:.1f}" '
            f'height="{strip_h}" fill="{pal["primary"][str(t)]}" opacity="0.75"/>'
        )

    parts.insert(2, "  <defs>\n" + "\n".join(defs) + "\n  </defs>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def to_png(svg: Path, png: Path) -> bool:
    """Пытаемся сконвертировать SVG → PNG тем, что есть в системе."""
    attempts = [
        (["rsvg-convert", "-w", str(png_width(svg)), "-o", str(png), str(svg)], "rsvg-convert"),
        (["inkscape", str(svg), f"--export-filename={png}", "-w", str(png_width(svg))], "inkscape"),
        (["convert", "-density", "96", "-background", "none", str(svg), str(png)], "convert"),
        (["magick", "-density", "96", str(svg), str(png)], "magick"),
    ]
    for cmd, name in attempts:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)
                if png.exists():
                    return True
            except Exception as exc:
                print(f"[md3-wall] {name}: {exc}", file=sys.stderr)
    try:
        import cairosvg  # type: ignore

        cairosvg.svg2png(url=str(svg), write_to=str(png),
                         output_width=png_width(svg))
        return png.exists()
    except Exception:
        return False



#----------------------------------------------------------------------------
# Чистый Python-растеризатор: PNG без Pillow/cairo/rsvg.
# Рендерим в маленький буфер (BW×BH) и поднимаем билинейно — формы крупные
# и мягкие, так что артефактов не видно, а время приемлемое.
#----------------------------------------------------------------------------

SS = 2          # суперсэмплинг ×2: рендерим в 2x и усредняем 4px → гладкие края
LUT_N = 256


def render_png(theme: Theme, w: int, h: int) -> bytes:
    """
    Растр в ФИНАЛЬНОМ разрешении (с суперсэмплингом SS), без апскейла:
    формы заливаются scanline-методом по сглаженному Catmull-Rom контуру,
    радиальный градиент и альфа — через LUT (256 ступеней), чтобы не
    считать float-математику на каждый пиксель заново.
    """
    R, pal = theme.roles, theme.palettes
    dark = theme.dark
    W, H = w * SS, h * SS
    base = hex_to_rgb(R["surface"])
    buf = bytearray(bytes(base) * (W * H))

    shapes = theme_shapes(theme, w, h)
    sqrt = math.sqrt
    for color, cx, cy, r, wob, ph, op in shapes:
        c = hex_to_rgb(color)
        lite = tuple(min(255, int(v * 1.12 + 8)) for v in c)
        cx, cy, r = cx * SS, cy * SS, r * SS
        poly = _subdivide(_ctrl_points(cx, cy, r, 9, wob, ph))
        xs = [p_[0] for p_ in poly]; ys = [p_[1] for p_ in poly]
        x0, x1 = max(0, int(min(xs)) - 1), min(W - 1, int(max(xs)) + 1)
        y0, y1 = max(0, int(min(ys)) - 1), min(H - 1, int(max(ys)) + 1)
        fx, fy = cx - 0.22 * (x1 - x0), cy - 0.24 * (y1 - y0)
        # LUT: ступень t∈[0,1] → цвет градиента и premultiplied-вклад
        mr = [0.0] * LUT_N; mg = [0.0] * LUT_N; mb = [0.0] * LUT_N
        sr = [0.0] * LUT_N; sg = [0.0] * LUT_N; sb = [0.0] * LUT_N
        for i in range(LUT_N):
            t = i / (LUT_N - 1)
            a = op * (0.85 + 0.15 * (1.0 - t))
            mr[i] = 1.0 - a
            sr[i] = (lite[0] + (c[0] - lite[0]) * t) * a
            sg[i] = (lite[1] + (c[1] - lite[1]) * t) * a
            sb[i] = (lite[2] + (c[2] - lite[2]) * t) * a
        n = len(poly)
        edges = [(poly[i], poly[(i + 1) % n]) for i in range(n)]
        inv_r = (LUT_N - 1) / max(1.0, r)
        row_w3 = W * 3
        for by in range(y0, y1 + 1):
            yy = by + 0.5
            cuts = []
            for (ax, ay), (bx2, by2) in edges:
                if (ay > yy) != (by2 > yy):
                    cuts.append(ax + (yy - ay) * (bx2 - ax) / (by2 - ay))
            if len(cuts) < 2:
                continue
            cuts.sort()
            dy2 = (yy - fy) * (yy - fy)
            row = by * row_w3
            for i in range(0, len(cuts) - 1, 2):
                sxa = max(x0, int(cuts[i])); sxb = min(x1, int(cuts[i + 1]))
                o = row + sxa * 3
                for bx in range(sxa, sxb + 1):
                    dx = bx + 0.5 - fx
                    t = sqrt(dx * dx + dy2) * inv_r
                    idx = int(t) if t < LUT_N - 1 else LUT_N - 1
                    ma = mr[idx]
                    buf[o] = int(buf[o] * ma + sr[idx])
                    buf[o + 1] = int(buf[o + 1] * ma + sg[idx])
                    buf[o + 2] = int(buf[o + 2] * ma + sb[idx])
                    o += 3

    # кольцо primary (акцент M3)
    ring = hex_to_rgb(R["primary"])
    rcx, rcy, rr = w * 0.22 * SS, h * 0.30 * SS, h * 0.30 * SS
    thick = max(1.0, rr * 0.012) * SS
    y0 = max(0, int(rcy - rr - thick)); y1 = min(H - 1, int(rcy + rr + thick))
    x0 = max(0, int(rcx - rr - thick)); x1 = min(W - 1, int(rcx + rr + thick))
    for by in range(y0, y1 + 1):
        dy = by + 0.5 - rcy
        row = by * W * 3
        for bx in range(x0, x1 + 1):
            dx = bx + 0.5 - rcx
            if abs(sqrt(dx * dx + dy * dy) - rr) <= thick:
                o = row + bx * 3
                buf[o] = int(buf[o] * 0.78 + ring[0] * 0.22)
                buf[o + 1] = int(buf[o + 1] * 0.78 + ring[1] * 0.22)
                buf[o + 2] = int(buf[o + 2] * 0.78 + ring[2] * 0.22)

    # тональная шкала md.ref.palette[primary] внизу
    tones = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100]
    strip = max(2, int(h // 110 * SS))
    cell = W / len(tones)
    for i, t in enumerate(tones):
        c = hex_to_rgb(pal["primary"][str(t)])
        xs0 = int(i * cell); xs1 = min(W, int((i + 1) * cell))
        for by in range(H - strip, H):
            row = by * W * 3
            for bx in range(xs0, xs1):
                o = row + bx * 3
                buf[o] = int(buf[o] * 0.25 + c[0] * 0.75)
                buf[o + 1] = int(buf[o + 1] * 0.25 + c[1] * 0.75)
                buf[o + 2] = int(buf[o + 2] * 0.25 + c[2] * 0.75)

    # даунскейл ×SS: усреднение блока SS×SS (box-filter = антиалиасинг)
    out = bytearray(w * h * 3)
    o = 0
    for y in range(h):
        for x in range(w):
            for k in range(3):
                acc = 0
                for sy in range(SS):
                    ro = ((y * SS + sy) * W + x * SS) * 3 + k
                    for sx in range(SS):
                        acc += buf[ro + sx * 3]
                out[o] = (acc + (SS * SS) // 2) // (SS * SS)
                o += 1
    return bytes(out)


def write_png(path: Path, data: bytes, w: int, h: int) -> None:
    import zlib

    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)                                    # фильтр None
        raw += data[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (len(payload).to_bytes(4, "big") + tag + payload
                + zlib.crc32(tag + payload).to_bytes(4, "big"))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big")
                 + bytes([8, 2, 0, 0, 0]))                # 8-bit truecolor RGB
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def png_width(svg: Path) -> int:
    try:
        for tok in svg.read_text().split():
            if tok.startswith("width="):
                return int("".join(ch for ch in tok if ch.isdigit()) or 2560)
    except Exception:
        pass
    return 2560


def generate(size: str = "2560x1440", png: bool = False) -> None:
    w, _, hh = size.partition("x")
    w, hh = int(w), int(hh or 1440)
    cfg = Config.load()
    WALL_DIR.mkdir(parents=True, exist_ok=True)

    for dark in (True, False):
        cfg.set("dark", dark)
        theme = Theme(cfg)
        name = "dark" if dark else "light"
        svg = WALL_DIR / f"md3-{name}.svg"
        svg.write_text(build_svg(theme, w, hh), encoding="utf-8")
        print(f"[md3-wall] {svg}  ({theme.seed} · {theme.scheme}/{theme.contrast}/{name})")
        if png:
            out = svg.with_suffix(".png")
            ok = to_png(svg, out)
            if ok:
                print(f"[md3-wall] ✔ PNG (внешний конвертер): {out}")
            else:
                try:
                    write_png(out, render_png(theme, w, hh), w, hh)
                    ok = out.exists()
                    print(f"[md3-wall] ✔ PNG (чистый Python, без зависимостей): {out}"
                          if ok else "[md3-wall] ✘ PNG: не получилось")
                except Exception as exc:
                    print(f"[md3-wall] ✘ PNG: {exc} — оставил SVG")

    # Config.set меняет значения только в памяти — theme-state.json не трогаем,
    # поэтому переключения dark/light в сгенерированных конфигах не произойдёт.


def main() -> int:
    ap = argparse.ArgumentParser(description="MD3-обои из тональных палитр темы")
    ap.add_argument("--size", default="2560x1440", help="WxH (по умолчанию 2560x1440)")
    ap.add_argument("--png", action="store_true", help="попытаться сконвертировать в PNG")
    args = ap.parse_args()
    generate(args.size, args.png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
