#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md3-theme-gui.py — GUI-редактор темы Material Design 3 для bspwm.

Компоненты нарисованы вручную на tk.Canvas строго по спецификациям M3
(значения взяты из material-web tokens v0_192 и m3.material.io):

  md.comp.checkbox   container 18dp, shape 2dp, outline 2dp (on-surface-variant),
                     selected container = primary, icon = on-primary,
                     state layer 40dp / corner-full,
                     hover 8 %, pressed 12 % (unselected → primary,
                     selected → on-surface), disabled 38 %,
                     ENTER 350 ms emphasized-decelerate cubic-bezier(0.05,0.7,0.1,1.0),
                     EXIT  150 ms emphasized-accelerate cubic-bezier(0.3,0.0,0.8,0.15),
                     scale 0.6 → 1.0, opacity 50 ms linear.
  md.comp.switch     track 52×32dp, outline 2dp, handle 16/24/28dp, icon 16dp.
  md.sys.shape       none 0 · xs 4 · s 8 · medium 12 · l 16 · l+ 20 · xl 28 · xl+ 32 · xxl 48 · full
  md.sys.motion      duration short1..extra-long4, easing emphasized/standard
  md.sys.state       hover .08 · focus .12 · pressed .12 · dragged .16
  md.sys.elevation   overlay surfaceTint 5/8/11/12/14 %

Запуск:
    python3 tools/md3-theme-gui.py                # GUI
    python3 tools/md3-theme-gui.py --cli --list   # без X-сервера: список опций
    python3 tools/md3-theme-gui.py --cli --set dark=false corner_radius=16
    python3 tools/md3-theme-gui.py --cli --apply  # пересобрать и применить тему
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from md3_theme import (  # noqa: E402
    CHECKBOX, CONTRAST_PAIRS, DURATION, EASING, ELEVATION, SHAPE_SCALE, STATE_LAYER,
    SWITCH, Config, Theme, available_contrasts, available_seeds, available_schemes,
    blend_over, contrast_ratio, hex_to_rgb, load_palettes, rgb_to_hex, snake,
    write_outputs,
)

# --------------------------------------------------------------------------- #
# md.sys.motion: easing как функции времени
# --------------------------------------------------------------------------- #


def cubic_bezier_fn(p1x: float, p1y: float, p2x: float, p2y: float) -> Callable[[float], float]:
    """
    cubic-bezier(x1,y1,x2,y2) → f(t)=y. Решаем x(u)=t методом Ньютона
    (как это делают браузеры), с fallback на бисекцию.
    """

    def cx(u: float) -> float:
        v = 1.0 - u
        return 3 * v * v * u * p1x + 3 * v * u * u * p2x + u * u * u

    def cy(u: float) -> float:
        v = 1.0 - u
        return 3 * v * v * u * p1y + 3 * v * u * u * p2y + u * u * u

    def dx(u: float) -> float:
        v = 1.0 - u
        return 3 * v * v * p1x + 6 * v * u * (p2x - p1x) + 3 * u * u * (1 - p2x)

    def solve(x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        u = x
        for _ in range(8):                      # Newton-Raphson
            err = cx(u) - x
            if abs(err) < 1e-6:
                return u
            d = dx(u)
            if abs(d) < 1e-6:
                break
            u -= err / d
            u = min(1.0, max(0.0, u))
        lo, hi = 0.0, 1.0                       # бисекция
        u = x
        for _ in range(24):
            v = cx(u)
            if abs(v - x) < 1e-6:
                return u
            if v < x:
                lo = u
            else:
                hi = u
            u = (lo + hi) / 2
        return u

    return lambda t: cy(solve(t))


EASE = {name: cubic_bezier_fn(*pts) for name, pts in EASING.items()}
EMPHASIZED_DECELERATE = EASE["emphasized-decelerate"]   # enter
EMPHASIZED_ACCELERATE = EASE["emphasized-accelerate"]   # exit
STANDARD = EASE["standard"]
LINEAR = lambda t: t                                     # noqa: E731


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_hex(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex((lerp(r1, r2, t), lerp(g1, g2, t), lerp(b1, b2, t)))


def mix_alpha(fg: str, bg: str, alpha: float) -> str:
    """state layer: наложение fg с прозрачностью поверх bg (без stipple-артефактов)."""
    return blend_over(fg, bg, alpha)


# --------------------------------------------------------------------------- #
# Типографика md.sys.typescale
# --------------------------------------------------------------------------- #

TYPE_SCALE = {
    "display-small": (24, "normal"),
    "headline-small": (20, "bold"),
    "title-medium": (14, "bold"),
    "title-small": (12, "bold"),
    "label-large": (12, "bold"),
    "label-medium": (11, "normal"),
    "body-large": (12, "normal"),
    "body-medium": (11, "normal"),
}


def pick_family() -> str:
    try:
        import tkinter.font as tkfont
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        families = set(tkfont.families(root))
        root.destroy()
        for cand in ("Product Sans", "Roboto", "Google Sans", "Inter",
                     "JetBrainsMono Nerd Font", "DejaVu Sans", "Helvetica", "Arial"):
            if cand in families:
                return cand
    except Exception:
        pass
    return "DejaVu Sans"


# --------------------------------------------------------------------------- #
# Базовый «темизируемый» виджет
# --------------------------------------------------------------------------- #

THEMABLES: List["Md3Widget"] = []


class Md3Widget:
    """Общий предок: регистрация в теме + анимационный тикер."""

    def __init__(self, app: "App"):
        self.app = app
        self.theme: Theme = app.theme
        THEMABLES.append(self)

    def retheme(self, theme: Theme) -> None:
        self.theme = theme
        self.redraw()

    # -- переопределяется в наследниках --
    def redraw(self) -> None:
        raise NotImplementedError

    # -- анимация --
    def animate(self, duration_ms: int, ease: Callable[[float], float],
                on_frame: Callable[[float], None],
                on_done: Optional[Callable[[], None]] = None) -> None:
        """Запускает анимацию 0→1 (MD3 duration + easing). Прерываемая."""
        self._anim_cancel = True                # прервать предыдущую (retargeting)
        start = time.perf_counter()
        dur = max(1, duration_ms) / 1000.0

        def tick() -> None:
            if getattr(self, "_anim_cancel", False):
                return
            t = (time.perf_counter() - start) / dur
            if t >= 1.0:
                on_frame(1.0)
                if on_done:
                    on_done()
                return
            on_frame(ease(t))
            self.app.root.after(8, tick)        # ~120 fps

        self._anim_cancel = False
        tick()


# --------------------------------------------------------------------------- #
# MD3 CHECKBOX  (md.comp.checkbox)
# --------------------------------------------------------------------------- #


class Md3Checkbox(Md3Widget):
    """
    Чекбокс M3 с настоящей анимацией:
      unselected → selected : 350 ms, emphasized-decelerate, scale 0.6 → 1.0
      selected → unselected : 150 ms, emphasized-accelerate, scale 1.0 → 0.6
      opacity иконки/фона   : 50 ms linear (short1) — как в material-web
      state layer           : 40 dp, corner-full, hover 8 %, pressed 12 %
      touch target          : 48 dp
    """

    SIZE = int(CHECKBOX["container-size"])          # 18
    SHAPE = int(CHECKBOX["container-shape"])        # 2
    OUTLINE = int(CHECKBOX["outline-width"])        # 2
    LAYER = int(CHECKBOX["state-layer-size"])       # 40
    SCALE_FROM = float(CHECKBOX["scale-from"])      # 0.6
    ENTER_MS = int(CHECKBOX["enter-duration"])      # 350
    EXIT_MS = int(CHECKBOX["exit-duration"])        # 150
    ICON_FADE_MS = int(CHECKBOX["icon-opacity-duration"])  # 50

    def __init__(self, app: "App", parent, text: str, key: Optional[str] = None,
                 value: bool = False, command: Optional[Callable[[bool], None]] = None,
                 tristate: bool = False, tooltip: str = ""):
        super().__init__(app)
        import tkinter as tk

        self.text = text
        self.key = key
        self.command = command
        self.tristate = tristate
        self.tooltip = tooltip
        self.state: Any = bool(value)               # True / False / "indeterminate"
        self.hover = False
        self.pressed = False
        self.focused = False
        self.disabled = False
        self.progress = 1.0 if self.state is True else 0.0   # 0 = unselected, 1 = selected
        self.icon_progress = self.progress

        self.frame = tk.Frame(parent, bg=app.card_bg)
        self.canvas = tk.Canvas(self.frame, width=self.LAYER, height=self.LAYER,
                                highlightthickness=0, bd=0, bg=app.card_bg)
        self.canvas.pack(side="left")
        self.label = tk.Label(self.frame, text=text, bg=app.card_bg, fg=app.fg,
                              font=app.font("body-large"), anchor="w",
                              justify="left", wraplength=520)
        self.label.pack(side="left", fill="x", expand=True, padx=(4, 0))

        for w in (self.canvas, self.label):
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<FocusIn>", lambda e: self._set_focus(True))
            w.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.frame.bind("<Button-1>", self._on_press)
        self.frame.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<KeyPress-space>", self._toggle_key)
        self.canvas.bind("<Return>", self._toggle_key)
        self.canvas.config(takefocus=True)
        self.redraw()

    # -- API --
    def set(self, value: Any, animate: bool = True) -> None:
        if value == self.state:
            return
        self.state = value
        self._run(animate)
        if self.command:
            self.command(value)

    def get(self) -> Any:
        return self.state

    def pack(self, **kw):
        self.frame.pack(**kw)

    def grid(self, **kw):
        self.frame.grid(**kw)

    def set_disabled(self, disabled: bool) -> None:
        self.disabled = disabled
        self.redraw()

    # -- события --
    def _on_press(self, _e=None):
        if self.disabled:
            return
        self.pressed = True
        self.redraw()

    def _on_release(self, e=None):
        if self.disabled or not self.pressed:
            return
        self.pressed = False
        self._toggle()
        self.redraw()

    def _on_enter(self, _e=None):
        self.hover = True
        self.redraw()

    def _on_leave(self, _e=None):
        self.hover = False
        self.pressed = False
        self.redraw()

    def _set_focus(self, on: bool):
        self.focused = on
        self.redraw()

    def _toggle_key(self, _e=None):
        if not self.disabled:
            self._toggle()

    def _toggle(self):
        if self.tristate:
            order = [False, True, "indeterminate"]
            self.state = order[(order.index(self.state) + 1) % 3]
        else:
            self.state = self.state is not True
        self._run(True)
        if self.command:
            self.command(self.state)

    # -- анимация (md.sys.motion) --
    def _run(self, animate: bool) -> None:
        target = 1.0 if self.state is True else 0.0
        if self.state == "indeterminate":
            target = 1.0
        if not animate:
            self.progress = self.icon_progress = target
            self.redraw()
            return
        if target > self.progress:
            # ENTER: 350 ms, emphasized-decelerate (scale), 50 ms linear (opacity)
            self.animate(self.ENTER_MS, EMPHASIZED_DECELERATE,
                         lambda t: self._frame_at(t, target, self.ENTER_MS))
        else:
            # EXIT: 150 ms, emphasized-accelerate
            self.animate(self.EXIT_MS, EMPHASIZED_ACCELERATE,
                         lambda t: self._frame_at(t, target, self.EXIT_MS))

    def _frame_at(self, t: float, target: float, total_ms: int) -> None:
        start = 1.0 - target
        self.progress = lerp(start, target, t)
        # opacity иконки/фона живёт 50 ms (md.sys.motion.duration.short1, linear)
        fade_t = min(1.0, t * total_ms / self.ICON_FADE_MS)
        self.icon_progress = lerp(start, target, fade_t)
        self.redraw()

    # -- отрисовка --
    def redraw(self) -> None:
        import tkinter as tk

        c = self.canvas
        c.delete("all")
        th = self.theme
        R = th.roles
        S = self.SIZE / 2.0                          # 9 — половина контейнера
        cx = cy = self.LAYER / 2.0                   # центр state layer'а

        # state layer смешивается с тем фоном, на котором лежит чекбокс —
        # это карточка (md.comp.card, elevation 1), а не surface окна.
        layer_bg = self.app.card_bg
        # --- state layer (md.sys.state) ---
        # md.comp.checkbox (tokens v0_192):
        #   hover/focus state layer = primary (и для selected, и для unselected)
        #   pressed state layer     = primary (unselected) / on-surface (selected)
        layer_color, layer_alpha = None, 0.0
        if self.disabled:
            layer_color, layer_alpha = None, 0.0
        elif self.pressed:
            layer_color = R["onSurface"] if self.state is True else R["primary"]
            layer_alpha = STATE_LAYER["press"]        # 0.12
        elif self.focused:
            layer_color = R["primary"]
            layer_alpha = STATE_LAYER["focus"]        # 0.12
        elif self.hover:
            layer_color = R["primary"]
            layer_alpha = STATE_LAYER["hover"]        # 0.08
        if layer_color and layer_alpha > 0:
            c.create_oval(cx - self.LAYER / 2 + 2, cy - self.LAYER / 2 + 2,
                          cx + self.LAYER / 2 - 2, cy + self.LAYER / 2 - 2,
                          fill=mix_alpha(layer_color, layer_bg, layer_alpha),
                          outline="")

        # --- контейнер: scale 0.6 → 1.0 (md.comp.checkbox enter/exit) ---
        scale = lerp(self.SCALE_FROM, 1.0, self.progress) if self.state is not False \
            else lerp(1.0, self.SCALE_FROM, 1.0 - self.progress)
        half = (S * scale)

        # фон (primary) — появляется вместе с scale
        if self.progress > 0.001:
            fill = R["primary"]
            if self.disabled:
                fill = mix_alpha(R["onSurface"], layer_bg, 0.38)
            self._round_rect(c, cx - half, cy - half, cx + half, cy + half,
                             self.SHAPE * scale, fill=fill, outline="",
                             alpha=self.icon_progress)

        # outline (2 dp, on-surface-variant → on-surface при hover/press)
        outline_color = R["onSurfaceVariant"]
        if self.hover or self.pressed or self.focused:
            outline_color = R["onSurface"]
        if self.disabled:
            outline_color = mix_alpha(R["onSurface"], layer_bg, 0.38)
        outline_alpha = max(0.0, 1.0 - self.icon_progress)
        if outline_alpha > 0.02:
            self._round_rect(c, cx - S, cy - S, cx + S, cy + S, self.SHAPE,
                             fill="", outline=outline_color,
                             width=self.OUTLINE, alpha=outline_alpha)

        # --- иконка ---
        icon_color = R["onPrimary"]
        if self.disabled:
            icon_color = R["surface"]
        if self.state == "indeterminate":
            self._draw_indeterminate(c, cx, cy, scale, icon_color)
        elif self.progress > 0.02:
            self._draw_check(c, cx, cy, scale, icon_color)

    def _draw_check(self, c, cx, cy, scale, color) -> None:
        """
        Галочка по геометрии material-web: два «mark»-сегмента, которые растут
        из нижней точки знака (short: √32 ≈ 5.66dp, long: √128 ≈ 11.31dp),
        stroke 2dp, поворот 45°.
        """
        s = scale
        ox, oy = cx - 2.5 * s, cy + 2.0 * s        # нижняя точка галочки
        short_len = (32 ** 0.5) * s
        long_len = (128 ** 0.5) * s
        t = max(0.0, min(1.0, (self.progress - 0.05) / 0.95))
        # short: вверх-влево под 45°
        sx = ox - short_len * 0.7071 * t
        sy = oy - short_len * 0.7071 * t
        # long: вверх-вправо под 45°
        lx = ox + long_len * 0.7071 * t
        ly = oy - long_len * 0.7071 * t
        width = max(1, int(round(2 * s)))
        c.create_line(ox, oy, sx, sy, fill=color, width=width,
                      capstyle="round", joinstyle="round")
        c.create_line(ox, oy, lx, ly, fill=color, width=width,
                      capstyle="round", joinstyle="round")

    def _draw_indeterminate(self, c, cx, cy, scale, color) -> None:
        s = scale
        half = 5.0 * s
        c.create_line(cx - half, cy, cx + half, cy, fill=color,
                      width=max(1, int(round(2 * s))), capstyle="round")

    def _round_rect(self, c, x1, y1, x2, y2, r, fill="", outline="", width=1, alpha=1.0) -> None:
        """Скруглённый прямоугольник + «прозрачность» через смешение с фоном."""
        if fill and alpha < 1.0:
            fill = mix_alpha(fill, self.app.bg, alpha)
        if outline and alpha < 1.0:
            outline = mix_alpha(outline, self.app.bg, alpha)
        r = max(0.0, min(r, min(x2 - x1, y2 - y1) / 2))
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        kw = {"smooth": True, "width": width}
        if fill:
            kw["fill"] = fill
        if outline:
            kw["outline"] = outline
        else:
            kw["outline"] = fill or ""
        c.create_polygon(pts, **kw)


# --------------------------------------------------------------------------- #
# MD3 SWITCH  (md.comp.switch)
# --------------------------------------------------------------------------- #


class Md3Switch(Md3Widget):
    """
    Переключатель M3: track 52×32dp (corner-full), outline 2dp,
    handle 16dp (unselected) → 24dp (selected) → 28dp (pressed),
    selected track = primary, handle = on-primary, иконка 16dp.
    Движение — md.sys.motion: enter 350 emphasized-decelerate / exit 150 emphasized-accelerate.
    """

    W = int(SWITCH["track-width"])      # 52
    H = int(SWITCH["track-height"])     # 32
    PAD = 6                             # поля внутри ячейки (state layer 40dp)
    CELL_H = 44

    def __init__(self, app: "App", parent, text: str, value: bool = False,
                 command: Optional[Callable[[bool], None]] = None, tooltip: str = ""):
        super().__init__(app)
        import tkinter as tk

        self.text = text
        self.value = bool(value)
        self.command = command
        self.tooltip = tooltip
        self.progress = 1.0 if value else 0.0
        self.hover = self.pressed = False

        self.frame = tk.Frame(parent, bg=app.card_bg)
        self.canvas = tk.Canvas(self.frame, width=self.W + 2 * self.PAD,
                                height=self.CELL_H, highlightthickness=0,
                                bd=0, bg=app.card_bg)
        self.canvas.pack(side="left")
        self.label = tk.Label(self.frame, text=text, bg=app.card_bg, fg=app.fg,
                              font=app.font("body-large"), anchor="w", wraplength=460,
                              justify="left")
        self.label.pack(side="left", fill="x", expand=True, padx=(6, 0))
        for w in (self.canvas, self.label, self.frame):
            w.bind("<Button-1>", self._press)
            w.bind("<ButtonRelease-1>", self._release)
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
        self.redraw()

    def set(self, value: bool, animate: bool = True) -> None:
        value = bool(value)
        if value == self.value:
            return
        self.value = value
        self._run(animate)
        if self.command:
            self.command(value)

    def pack(self, **kw):
        self.frame.pack(**kw)

    def _press(self, _e=None):
        self.pressed = True
        self.redraw()

    def _release(self, _e=None):
        if not self.pressed:
            return
        self.pressed = False
        self.value = not self.value
        self._run(True)
        if self.command:
            self.command(self.value)

    def _hover(self, on: bool):
        self.hover = on
        self.pressed = False
        self.redraw()

    def _run(self, animate: bool) -> None:
        target = 1.0 if self.value else 0.0
        if not animate:
            self.progress = target
            self.redraw()
            return
        if target > self.progress:
            self.animate(350, EMPHASIZED_DECELERATE, self._at)
        else:
            self.animate(150, EMPHASIZED_ACCELERATE, self._at)

    def _at(self, t: float) -> None:
        self.progress = t if self.value else 1.0 - t
        self.redraw()

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        R = self.theme.roles
        bg = self.app.card_bg          # switch тоже лежит внутри карточки
        cx0, cy = self.PAD, self.CELL_H / 2
        x1, y1 = cx0, cy - self.H / 2
        x2, y2 = cx0 + self.W, cy + self.H / 2
        p = max(0.0, min(1.0, self.progress))

        # state layer (40dp, corner-full)
        if self.hover or self.pressed:
            color = R["primary"] if self.value else R["onSurface"]
            alpha = STATE_LAYER["press"] if self.pressed else STATE_LAYER["hover"]
            hcx = lerp(x1 + 16, x2 - 16, p)
            c.create_oval(hcx - 20, cy - 20, hcx + 20, cy + 20,
                          fill=mix_alpha(color, bg, alpha), outline="")

        # track
        track_unsel = R["surfaceContainerHighest"]
        track_sel = R["primary"]
        track = lerp_hex(track_unsel, track_sel, p)
        c.create_oval(x1, y1, x2, y2, fill=track, outline="")
        # outline 2dp (outline → primary)
        if p < 0.999:
            ol = lerp_hex(R["outline"], track_sel, p)
            c.create_oval(x1 + 1, y1 + 1, x2 - 1, y2 - 1, outline=ol, width=2)

        # handle: 16 → 24 dp (28 при нажатии)
        size = lerp(int(SWITCH["handle-unselected"]), int(SWITCH["handle-selected"]), p)
        if self.pressed:
            size = int(SWITCH["handle-pressed"])
        hcx = lerp(x1 + 16, x2 - 16, p)
        handle_color = lerp_hex(R["outline"], R["onPrimary"], p)
        if self.value and (self.hover or self.pressed):
            handle_color = R["primaryContainer"]
        c.create_oval(hcx - size / 2, cy - size / 2, hcx + size / 2, cy + size / 2,
                      fill=handle_color, outline="")
        # иконка «check» 16dp внутри handle, когда включено
        if p > 0.55 and size >= 20:
            icon = R["onPrimaryContainer"] if (self.hover or self.pressed) else R["onPrimary"]
            if self.value and (self.hover or self.pressed):
                icon = R["onPrimaryContainer"]
            r = 3.2
            c.create_line(hcx - r, cy, hcx - r * 0.2, cy + r * 0.8,
                          fill=icon, width=2, capstyle="round")
            c.create_line(hcx - r * 0.2, cy + r * 0.8, hcx + r, cy - r * 0.9,
                          fill=icon, width=2, capstyle="round")
        elif p < 0.45 and size >= 14:
            icon = R["surfaceContainerHighest"]
            c.create_line(hcx - 3, cy - 3, hcx + 3, cy + 3, fill=icon, width=2,
                          capstyle="round")
            c.create_line(hcx + 3, cy - 3, hcx - 3, cy + 3, fill=icon, width=2,
                          capstyle="round")


# --------------------------------------------------------------------------- #
# MD3 SLIDER  (md.comp.slider)
# --------------------------------------------------------------------------- #


class Md3Slider(Md3Widget):
    """
    Слайдер M3: трек 4dp (inactive = surface-container-highest, active = primary),
    handle 20dp (primary) + state layer 40dp, hover 8 %, pressed 12 %.
    Анимация handle — 200 md.sys.motion.duration.short4, standard easing.
    """

    H = 44
    TRACK_H = 4
    HANDLE = 20

    def __init__(self, app: "App", parent, text: str, lo: float, hi: float,
                 value: float, step: float = 1, unit: str = "",
                 command: Optional[Callable[[float], None]] = None):
        super().__init__(app)
        import tkinter as tk

        self.text, self.lo, self.hi, self.step, self.unit = text, lo, hi, step, unit
        self.value = value
        self.command = command
        self.hover = self.pressed = False
        self.shown = float(value)          # анимируемое значение

        self.frame = tk.Frame(parent, bg=app.card_bg)
        self.head = tk.Frame(self.frame, bg=app.card_bg)
        self.head.pack(fill="x")
        self.label = tk.Label(self.head, text=text, bg=app.card_bg, fg=app.fg,
                              font=app.font("body-large"), anchor="w")
        self.label.pack(side="left")
        self.readout = tk.Label(self.head, text="", bg=app.card_bg, fg=app.accent,
                                font=app.font("label-large"), anchor="e")
        self.readout.pack(side="right")

        self.canvas = tk.Canvas(self.frame, width=520, height=self.H,
                                highlightthickness=0, bd=0, bg=app.card_bg)
        self.canvas.pack(fill="x", pady=(2, 0))
        self.canvas.bind("<Button-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.canvas.bind("<Enter>", lambda e: self._hover(True))
        self.canvas.bind("<Leave>", lambda e: self._hover(False))
        self.canvas.bind("<Motion>", self._move)
        self.canvas.config(takefocus=True)
        self.canvas.bind("<Left>", lambda e: self._nudge(-1))
        self.canvas.bind("<Right>", lambda e: self._nudge(1))
        self._update_readout()
        self.redraw()

    # -- geometry --
    def _pad(self) -> int:
        return self.HANDLE

    def _x_for(self, v: float) -> float:
        w = max(1, int(self.canvas["width"]) - 2 * self._pad())
        t = 0 if self.hi == self.lo else (v - self.lo) / (self.hi - self.lo)
        return self._pad() + w * max(0.0, min(1.0, t))

    def _v_for(self, x: float) -> float:
        w = max(1, int(self.canvas["width"]) - 2 * self._pad())
        t = (x - self._pad()) / w
        t = max(0.0, min(1.0, t))
        raw = self.lo + t * (self.hi - self.lo)
        if self.step:
            raw = round(raw / self.step) * self.step
        return max(self.lo, min(self.hi, raw))

    # -- events --
    def _down(self, e):
        self.pressed = True
        self._set(self._v_for(e.x), animate=False)

    def _drag(self, e):
        self._set(self._v_for(e.x), animate=False)

    def _up(self, _e):
        self.pressed = False
        self.redraw()

    def _move(self, e):
        self.hover_x = e.x
        self.redraw()

    def _hover(self, on: bool):
        self.hover = on
        self.redraw()

    def _nudge(self, direction: int):
        step = self.step or 1
        self._set(max(self.lo, min(self.hi, self.value + direction * step)), animate=True)

    def _set(self, v: float, animate: bool = True) -> None:
        v = round(v, 6)
        changed = abs(v - self.value) > 1e-9
        self.value = v
        self._update_readout()
        if changed and self.command:
            self.command(v)
        if animate and changed:
            start = self.shown

            def frame(t):
                self.shown = lerp(start, v, t)
                self.redraw()

            self.animate(int(DURATION["short4"]), STANDARD, frame)
        else:
            self.shown = v
            self.redraw()

    def set(self, v: float, animate: bool = False) -> None:
        self.value = v
        self._update_readout()
        self._set(v, animate=animate)

    def _update_readout(self):
        val = self.value
        txt = f"{int(val)}" if float(val).is_integer() else f"{val:.2f}"
        self.readout.config(text=f"{txt}{self.unit}")

    def pack(self, **kw):
        self.frame.pack(**kw)

    # -- draw --
    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        R = self.theme.roles
        bg = self.app.card_bg
        w = int(c["width"])
        cy = self.H / 2
        x1, x2 = self._pad(), w - self._pad()
        xp = self._x_for(self.shown)

        # неактивная часть трека
        c.create_line(xp, cy, x2, cy, fill=R["surfaceContainerHighest"],
                      width=self.TRACK_H, capstyle="round")
        # активная часть трека — primary
        c.create_line(x1, cy, xp, cy, fill=R["primary"], width=self.TRACK_H,
                      capstyle="round")

        # state layer
        if self.hover or self.pressed:
            alpha = STATE_LAYER["press"] if self.pressed else STATE_LAYER["hover"]
            c.create_oval(xp - 20, cy - 20, xp + 20, cy + 20,
                          fill=mix_alpha(R["primary"], bg, alpha), outline="")

        # handle 20dp
        r = self.HANDLE / 2 + (2 if self.pressed else 0)
        c.create_oval(xp - r, cy - r, xp + r, cy + r, fill=R["primary"], outline="")
        # точка внутри handle (md.comp.slider: inactive handle dot)
        c.create_oval(xp - 2, cy - 2, xp + 2, cy + 2, fill=R["onPrimary"], outline="")


# --------------------------------------------------------------------------- #
# MD3 BUTTONS (filled / tonal / text) и SEGMENTED BUTTON
# --------------------------------------------------------------------------- #


class Md3Button(Md3Widget):
    """
    Кнопка M3. kind:
      filled     — container primary, label on-primary
      tonal      — container secondary-container, label on-secondary-container
      outlined   — outline 1dp, label primary
      text       — без контейнера, label primary
    shape: md.sys.shape.full (пилюля, 20dp при высоте 40dp), hover layer 8 %.
    """

    H = 40

    def __init__(self, app: "App", parent, text: str, command: Callable[[], None],
                 kind: str = "filled", icon: str = ""):
        super().__init__(app)
        import tkinter as tk

        self.text, self.command, self.kind, self.icon = text, command, kind, icon
        self.hover = self.pressed = False
        self.w = tk.Canvas(parent, height=self.H, width=max(96, 14 * (len(text) + len(icon) + 2)),
                           highlightthickness=0, bd=0, bg=app.card_bg, cursor="hand2")
        self.w.pack(side="left", padx=(0, 8), pady=4)
        self.w.bind("<Button-1>", self._down)
        self.w.bind("<ButtonRelease-1>", self._up)
        self.w.bind("<Enter>", lambda e: self._hover(True))
        self.w.bind("<Leave>", lambda e: self._hover(False))
        self.redraw()

    def _hover(self, on):
        self.hover = on
        self.redraw()

    def _down(self, _e):
        self.pressed = True
        self.redraw()

    def _up(self, _e):
        if self.pressed:
            self.pressed = False
            self.redraw()
            if self.command:
                self.command()

    def pack(self, **kw):
        self.w.pack(**kw)

    def redraw(self) -> None:
        import tkinter as tk

        c = self.w
        c.delete("all")
        R = self.theme.roles
        bg = self.app.card_bg
        w = int(c["width"])
        h = self.H
        radius = min(h / 2, 20)                    # md.sys.shape.full

        if self.kind == "filled":
            cont, lab = R["primary"], R["onPrimary"]
            layer = R["onPrimary"]
        elif self.kind == "tonal":
            cont, lab = R["secondaryContainer"], R["onSecondaryContainer"]
            layer = R["onSecondaryContainer"]
        elif self.kind == "outlined":
            cont, lab = "none", R["primary"]
            layer = R["primary"]
        else:                                       # text
            cont, lab = "none", R["primary"]
            layer = R["primary"]

        fill = cont
        if cont != "none" and (self.hover or self.pressed):
            alpha = STATE_LAYER["press"] if self.pressed else STATE_LAYER["hover"]
            fill = mix_alpha(layer, cont, alpha)

        if cont != "none":
            self._pill(c, 1, 1, w - 1, h - 1, radius, fill=fill)
        elif self.hover or self.pressed:
            # md.comp.text-button: state layer появляется только при наведении
            alpha = STATE_LAYER["press"] if self.pressed else STATE_LAYER["hover"]
            self._pill(c, 1, 1, w - 1, h - 1, radius,
                       fill=mix_alpha(layer, bg, alpha))

        if self.kind == "outlined":
            self._pill(c, 1, 1, w - 1, h - 1, radius, fill="", outline=R["outline"], width=1)

        label = f"{self.icon}  {self.text}" if self.icon else self.text
        c.create_text(w / 2, h / 2 + 1, text=label, fill=lab,
                      font=self.app.font("label-large"))

    def _pill(self, c, x1, y1, x2, y2, r, fill="", outline="", width=1):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        kw = {"smooth": True, "width": width}
        kw["fill"] = fill if fill else outline if outline else self.app.bg
        kw["outline"] = outline if outline else (fill if fill else self.app.bg)
        c.create_polygon(pts, **kw)


class Md3Segmented(Md3Widget):
    """
    md.comp.segmented-button: пилюля из N сегментов, outline 1dp (outline),
    выбранный сегмент — secondary-container + on-secondary-container + галочка,
    shape: полный по краям (md.sys.shape.full), radius 20dp.
    """

    H = 40

    def __init__(self, app: "App", parent, items: List[str], value: str,
                 command: Callable[[str], None], width: int = 420):
        super().__init__(app)
        import tkinter as tk

        self.items = items
        self.value = value
        self.command = command
        self.width = width
        self.hover_idx: Optional[int] = None
        self.canvas = tk.Canvas(parent, width=width, height=self.H,
                                highlightthickness=0, bd=0, bg=app.bg, cursor="hand2")
        self.canvas.pack(pady=4)
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<Button-1>", self._click)
        self.redraw()

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def set(self, value: str) -> None:
        if value == self.value:
            return
        self.value = value
        self.redraw()

    def _seg_w(self) -> float:
        return self.width / max(1, len(self.items))

    def _index(self, x: float) -> Optional[int]:
        i = int(x // self._seg_w())
        return i if 0 <= i < len(self.items) else None

    def _motion(self, e):
        self.hover_idx = self._index(e.x)
        self.redraw()

    def _leave(self, _e):
        self.hover_idx = None
        self.redraw()

    def _click(self, e):
        i = self._index(e.x)
        if i is None:
            return
        self.value = self.items[i]
        self.redraw()
        if self.command:
            self.command(self.value)

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        R = self.theme.roles
        bg = self.app.bg
        r = self.H / 2
        sw = self._seg_w()

        # общий контур пилюли
        self._pill(c, 1, 1, self.width - 1, self.H - 1, r,
                   fill=R["surface"], outline=R["outline"], width=1)

        for i, item in enumerate(self.items):
            x1 = i * sw
            x2 = x1 + sw
            selected = (item == self.value)
            hovered = (self.hover_idx == i)
            if selected:
                fill = R["secondaryContainer"]
                fg = R["onSecondaryContainer"]
            else:
                fill = mix_alpha(R["onSurface"], R["surface"], STATE_LAYER["hover"]) if hovered else ""
                fg = R["onSurfaceVariant"]
            if fill:
                # скругляем только крайние сегменты (md.sys.shape: inner corners)
                rr_l = r if i == 0 else 0
                rr_r = r if i == len(self.items) - 1 else 0
                self._seg(c, x1 + 2, 2, x2 - 2, self.H - 2, rr_l, rr_r, fill)
            label = f"✓ {item}" if selected else item
            c.create_text((x1 + x2) / 2, self.H / 2 + 1, text=label, fill=fg,
                          font=self.app.font("label-large"))
            if i > 0:
                c.create_line(x1, 8, x1, self.H - 8, fill=R["outlineVariant"], width=1)

    def _pill(self, c, x1, y1, x2, y2, r, fill="", outline="", width=1):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        kw = {"smooth": True, "width": width}
        kw["fill"] = fill or outline or self.app.bg
        kw["outline"] = outline or fill or self.app.bg
        c.create_polygon(pts, **kw)

    def _seg(self, c, x1, y1, x2, y2, rl, rr, fill):
        pts = [x1 + rl, y1, x2 - rr, y1, x2, y1, x2, y1 + rr, x2, y2 - rr, x2, y2,
               x2 - rr, y2, x1 + rl, y2, x1, y2, x1, y2 - rl, x1, y1 + rl, x1, y1]
        c.create_polygon(pts, smooth=True, fill=fill, outline=fill)


# --------------------------------------------------------------------------- #
# Превью рабочего стола
# --------------------------------------------------------------------------- #


class DesktopPreview(Md3Widget):
    """
    Живое превью: монитор → polybar → два тайловых окна (рамка primary /
    outline-variant) → плавающий диалог с тенью elevation и скруглением
    md.sys.shape. Все размеры масштабируются из реальных значений конфига
    (corner_radius, border_width, gap, padding, shadow).
    """

    W = 560
    H = 340

    def __init__(self, app: "App", parent):
        super().__init__(app)
        import tkinter as tk

        self.canvas = tk.Canvas(parent, width=self.W, height=self.H,
                                highlightthickness=0, bd=0, bg=app.bg)
        self.canvas.pack()

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        th = self.theme
        R = th.roles
        cfg = self.app.cfg

        W, H = self.W, self.H
        # «экран» = md.sys.color.surface, рамка монитора = outline-variant
        self._rr(c, 8, 8, W - 8, H - 8, 16, fill=R["surface"], outline=R["outlineVariant"], width=1)

        sx, sy = 8, 8
        sw, sh = W - 16, H - 16

        # --- панель (elevation 2, высота 38dp → масштаб ~0.09) ---
        bar_h = 34
        bar_bg = th.elevation[2]
        self._rr(c, sx, sy, sx + sw, sy + bar_h, 0, fill=bar_bg, outline="")

        # пилюли рабочих столов (md.comp.navigation-item)
        x = sx + 12
        for i, name in enumerate(["1", "2", "3", "4", "5"]):
            w = 26
            if i == 0:
                self._rr(c, x, sy + 8, x + w, sy + bar_h - 8, 8,
                         fill=R["primaryContainer"], outline="")
                fg = R["onPrimaryContainer"]
            elif i == 1:
                self._rr(c, x, sy + 8, x + w, sy + bar_h - 8, 8,
                         fill=R["secondaryContainer"], outline="")
                fg = R["onSecondaryContainer"]
            else:
                fg = R["onSurfaceVariant"]
            c.create_text(x + w / 2, sy + bar_h / 2 + 1, text=name, fill=fg,
                          font=self.app.font("label-medium"))
            x += w + 6

        # заголовок окна
        c.create_text(x + 16, sy + bar_h / 2 + 1, anchor="w",
                      text="alacritty — bspwm · material 3",
                      fill=R["onSurfaceVariant"], font=self.app.font("body-medium"))

        # часы: primary pill
        tw = 74
        self._rr(c, sx + sw - tw - 56, sy + 6, sx + sw - 56, sy + bar_h - 6, 10,
                 fill=R["primary"], outline="")
        c.create_text(sx + sw - 56 - tw / 2, sy + bar_h / 2 + 1, text="17:42",
                      fill=R["onPrimary"], font=self.app.font("label-large"))
        # трей
        self._rr(c, sx + sw - 48, sy + 6, sx + sw - 8, sy + bar_h - 6, 10,
                 fill=R["surfaceContainerHigh"], outline="")
        for k in range(3):
            c.create_oval(sx + sw - 42 + k * 12, sy + 13, sx + sw - 34 + k * 12, sy + 21,
                          fill=R["onSurfaceVariant"], outline="")

        # --- окна (тайлинг) ---
        gap = int(cfg.values["gap"])
        pad = int(cfg.values["padding"])
        bw = int(cfg.values["border_width"])
        radius = int(cfg.values["corner_radius"])
        k = 2.2                                    # масштаб dp → px превью
        g = max(3, int(gap * k * 0.5))
        p = max(4, int(pad * k * 0.5))
        r = max(0, int(radius * k * 0.5))

        ox, oy = sx + p, sy + bar_h + p
        ow, oh = sw - 2 * p, sh - bar_h - 2 * p
        left_w = int(ow * 0.56)

        focus = str(cfg.values["focus_style"])
        focus_color = {"primary": R["primary"],
                       "primary-container": R["primaryContainer"],
                       "tertiary": R["tertiary"]}.get(focus, R["primary"])

        # окно 1 — активное
        self._window(c, ox, oy, ox + left_w - g // 2, oy + oh, r, bw,
                     focus_color, th.elevation[1], R["onSurface"], "1  terminal")
        # окно 2 — неактивное
        self._window(c, ox + left_w + g // 2, oy, ox + ow, oy + oh, r, bw,
                     R["outlineVariant"], R["surface"], R["onSurfaceVariant"], "2  browser")

        # --- плавающий диалог: elevation 3 + тень md.sys.color.shadow ---
        dw, dh = 190, 120
        dx = ox + ow - dw - 12
        dy = oy + oh - dh - 12
        sh_ = th.shadow
        # тень (смещение + blur имитируем несколькими слоями)
        for i, a in enumerate((0.10, 0.16, 0.24)):
            off = int(sh_["offset_y"] * 0.5) + i * 2
            blur = int(sh_["blur"] * 0.25) + i * 2
            self._rr(c, dx - blur, dy - blur + off, dx + dw + blur, dy + dh + blur + off,
                     r + 4, fill=mix_alpha(th.shadow_color, R["surface"], a * sh_["alpha"] / 0.3),
                     outline="")
        self._rr(c, dx, dy, dx + dw, dy + dh, r, fill=th.elevation[3],
                 outline=R["outlineVariant"], width=1)
        c.create_text(dx + 16, dy + 20, anchor="w", text="Dialog",
                      fill=R["onSurface"], font=self.app.font("title-small"))
        c.create_text(dx + 16, dy + 42, anchor="w",
                      text=f"elevation 3 · radius {radius}dp",
                      fill=R["onSurfaceVariant"], font=self.app.font("body-medium"))
        # кнопки диалога: text + filled (md.comp.button)
        self._pill_button(c, dx + dw - 96, dy + dh - 40, dx + dw - 16, dy + dh - 14,
                          R["primary"], R["onPrimary"], "OK")
        self._pill_button(c, dx + dw - 176, dy + dh - 40, dx + dw - 104, dy + dh - 14,
                          "", R["primary"], "Cancel")

    # -- helpers --
    def _window(self, c, x1, y1, x2, y2, r, bw, border, bg, fg, title):
        th = self.theme
        R = th.roles
        # рамка
        self._rr(c, x1, y1, x2, y2, r, fill=border, outline="")
        inn = max(1, bw)
        self._rr(c, x1 + inn, y1 + inn, x2 - inn, y2 - inn, max(0, r - inn),
                 fill=bg, outline="")
        # «контент» окна
        c.create_text(x1 + inn + 10, y1 + inn + 14, anchor="w", text=title,
                      fill=fg, font=self.app.font("label-medium"))
        for i in range(4):
            w = (x2 - x1) * (0.7 - 0.12 * i)
            c.create_line(x1 + inn + 10, y1 + inn + 34 + i * 12,
                          x1 + inn + 10 + w, y1 + inn + 34 + i * 12,
                          fill=mix_alpha(R["onSurfaceVariant"], bg, 0.35), width=3)

    def _pill_button(self, c, x1, y1, x2, y2, fill, fg, text):
        r = (y2 - y1) / 2
        if fill:
            self._rr(c, x1, y1, x2, y2, r, fill=fill, outline="")
        c.create_text((x1 + x2) / 2, (y1 + y2) / 2 + 1, text=text, fill=fg,
                      font=self.app.font("label-medium"))

    def _rr(self, c, x1, y1, x2, y2, r, fill="", outline="", width=1):
        r = max(0.0, min(float(r), min(x2 - x1, y2 - y1) / 2))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        kw = {"smooth": True, "width": width}
        kw["fill"] = fill or outline or self.app.bg
        kw["outline"] = outline or fill or self.app.bg
        c.create_polygon(pts, **kw)


# --------------------------------------------------------------------------- #
# Палитра тонов и отчёт о контрасте
# --------------------------------------------------------------------------- #


class TonalStrip(Md3Widget):
    """md.ref.palette.* — тона 0..100 для 6 ключевых цветов."""

    TONES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100]
    ROWS = ["primary", "secondary", "tertiary", "error", "neutral", "neutralVariant"]

    def __init__(self, app: "App", parent):
        super().__init__(app)
        import tkinter as tk

        self.canvas = tk.Canvas(parent, width=560, height=132, highlightthickness=0,
                                bd=0, bg=app.bg)
        self.canvas.pack()

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        pal = self.theme.palettes
        cell = 38
        for ri, row in enumerate(self.ROWS):
            y = 16 + ri * 19
            tones = pal.get(row, {})
            for ci, t in enumerate(self.TONES):
                x = 96 + ci * 35
                col = tones.get(str(t), "#000000")
                c.create_rectangle(x, y, x + 33, y + 17, fill=col, outline=col)
            c.create_text(88, y + 9, anchor="e", text=row.replace("neutralVariant", "neutral-var"),
                          fill=self.app.fg_muted, font=self.app.font("label-medium"))
        c.create_text(96, 6, anchor="w", text="md.ref.palette — тона 0…100 (тон = L* в HCT)",
                      fill=self.app.fg_muted, font=self.app.font("body-medium"))


class ContrastCard(Md3Widget):
    """Проверка пар md.sys.color по WCAG (M3 требует ≥ 3:1, для текста ≥ 4.5:1)."""

    def __init__(self, app: "App", parent):
        super().__init__(app)
        import tkinter as tk

        self.canvas = tk.Canvas(parent, width=560, height=26 + 22 * len(CONTRAST_PAIRS),
                                highlightthickness=0, bd=0, bg=app.bg)
        self.canvas.pack()

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        R = self.theme.roles
        c.create_text(4, 10, anchor="w", text="Пары цветов (WCAG)",
                      fill=self.app.fg, font=self.app.font("title-small"))
        y = 30
        for fg, bg in CONTRAST_PAIRS:
            ratio = contrast_ratio(R.get(fg, "#000"), R.get(bg, "#fff"))
            ok = ratio >= 4.5
            mid = ratio >= 3.0
            badge = R["primary"] if ok else (R["tertiary"] if mid else R["error"])
            badge_fg = R["onPrimary"] if ok else (R["onTertiary"] if mid else R["onError"])
            c.create_rectangle(4, y - 8, 74, y + 8, fill=badge, outline=badge)
            c.create_text(39, y + 1, text=f"{ratio:.2f}:1", fill=badge_fg,
                          font=self.app.font("label-medium"))
            c.create_text(84, y + 1, anchor="w",
                          text=f"{fg}  →  {bg}", fill=self.app.fg_muted,
                          font=self.app.font("body-medium"))
            # мини-превью пары
            c.create_rectangle(392, y - 9, 556, y + 9, fill=R.get(bg, "#000"),
                               outline=R.get("outlineVariant", "#333"))
            c.create_text(474, y + 1, text="Aa 123", fill=R.get(fg, "#fff"),
                          font=self.app.font("label-medium"))
            y += 22


# --------------------------------------------------------------------------- #
# Карточка (md.comp.card, elevation 1)
# --------------------------------------------------------------------------- #


class Card:
    """md.comp.card: container = elevation 1, shape = medium (12dp), padding 16dp."""

    def __init__(self, app: "App", parent, title: str, subtitle: str = ""):
        import tkinter as tk

        self.app = app
        self.frame = tk.Frame(parent, bg=app.card_bg, highlightbackground=app.outline_variant,
                              highlightthickness=1, bd=0)
        self.frame.pack(fill="x", padx=12, pady=8)
        head = tk.Frame(self.frame, bg=app.card_bg)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text=title, bg=app.card_bg, fg=app.fg,
                 font=app.font("title-medium"), anchor="w").pack(side="left")
        if subtitle:
            tk.Label(self.frame, text=subtitle, bg=app.card_bg, fg=app.fg_muted,
                     font=app.font("body-medium"), anchor="w", justify="left",
                     wraplength=600).pack(fill="x", padx=16, pady=(0, 6))
        self.body = tk.Frame(self.frame, bg=app.card_bg)
        self.body.pack(fill="x", padx=16, pady=(4, 14))

    def retheme(self, theme: Theme) -> None:
        import tkinter as tk

        bg = self.app.card_bg
        self.frame.config(bg=bg, highlightbackground=self.app.outline_variant)
        for w in self.frame.winfo_children():
            self._recolor(w, bg)

    @staticmethod
    def _recolor(w, bg) -> None:
        import tkinter as tk

        try:
            if isinstance(w, (tk.Frame, tk.Label)):
                w.config(bg=bg)
            if isinstance(w, tk.Label):
                pass
        except Exception:
            pass
        for ch in w.winfo_children():
            Card._recolor(ch, bg)


# --------------------------------------------------------------------------- #
# Приложение
# --------------------------------------------------------------------------- #


class App:
    def __init__(self, cfg: Config):
        import tkinter as tk
        from tkinter import ttk

        self.cfg = cfg
        self.theme = Theme(cfg)
        self.family = pick_family()
        self.status_text = tk.StringVar(value="готово")
        self.pending_restart = False

        self.root = tk.Tk()
        self.root.title("Material Design 3 — тема bspwm")
        self.root.geometry("1240x880")
        self.root.minsize(1120, 720)

        self._fonts: Dict[str, Any] = {}
        self._apply_palette()
        self._build()
        self.retheme(animate=False)

    # -- шрифты/палитра --
    def font(self, token: str):
        import tkinter.font as tkfont

        if token not in self._fonts:
            size, weight = TYPE_SCALE.get(token, (11, "normal"))
            self._fonts[token] = tkfont.Font(family=self.family, size=size, weight=weight)
        return self._fonts[token]

    def _apply_palette(self):
        R = self.theme.roles
        self.bg = R["surfaceContainer"]              # фон окна = surface-container
        self.card_bg = self.theme.elevation[1]       # карточки = elevation 1
        self.fg = R["onSurface"]
        self.fg_muted = R["onSurfaceVariant"]
        self.accent = R["primary"]
        self.outline_variant = R["outlineVariant"]

    # -- сборка UI --
    def _build(self):
        import tkinter as tk
        from tkinter import ttk

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        self.root.config(bg=self.bg)

        # --- top app bar (md.comp.top-app-bar, small) ---
        self.appbar = tk.Frame(self.root, height=64, bg=self.bg)
        self.appbar.pack(fill="x", side="top")
        self.appbar.pack_propagate(False)
        tk.Label(self.appbar, text="Material Design 3", bg=self.bg, fg=self.fg,
                 font=self.font("headline-small")).pack(side="left", padx=20, pady=(10, 0))
        self.subtitle = tk.Label(self.appbar, text="", bg=self.bg, fg=self.fg_muted,
                                 font=self.font("body-medium"), anchor="w")
        self.subtitle.pack(side="left", padx=0, pady=(16, 0))
        self.mode_seg_holder = tk.Frame(self.appbar, bg=self.bg)
        self.mode_seg_holder.pack(side="right", padx=16)

        # --- основная область ---
        body = tk.Frame(self.root, bg=self.bg)
        body.pack(fill="both", expand=True)

        # левая колонка: скроллируемые настройки
        left_outer = tk.Frame(body, bg=self.bg)
        left_outer.pack(side="left", fill="both", expand=True)
        self.left = tk.Canvas(left_outer, bg=self.bg, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(left_outer, orient="vertical", command=self.left.yview)
        self.left.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.left.pack(side="left", fill="both", expand=True)
        self.left_inner = tk.Frame(self.left, bg=self.bg)
        self._left_win = self.left.create_window((0, 0), window=self.left_inner, anchor="nw")
        self.left_inner.bind("<Configure>",
                             lambda e: self.left.configure(scrollregion=self.left.bbox("all")))
        self.left.bind("<Configure>", lambda e: self.left.itemconfigure(self._left_win, width=e.width))
        # прокрутка колесом
        for w in (self.left, self.left_inner):
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>", lambda e: self._scroll(-1))
            w.bind("<Button-5>", lambda e: self._scroll(1))

        # правая колонка: превью
        right = tk.Frame(body, bg=self.bg, width=600)
        right.pack(side="right", fill="y", padx=(0, 8))
        right.pack_propagate(False)
        self.right = right

        self._build_left()
        self._build_right()
        self._build_bottom()

    def _on_wheel(self, e):
        self._scroll(-1 if e.delta > 0 else 1)

    def _scroll(self, direction: int):
        self.left.yview_scroll(direction * 2, "units")

    # -- левая колонка --
    def _build_left(self):
        import tkinter as tk

        c = self.cfg.values

        # ===== ЦВЕТ =====
        card = Card(self, self.left, "Стили")
        self.card_color = card

        holder = tk.Frame(card.body, bg=self.card_bg)
        holder.pack(fill="x")
        self.seg_mode = Md3Segmented(self, holder, ["dark", "light"],
                                     "dark" if c["dark"] else "light",
                                     self._on_mode, width=160)
        self.seg_mode.pack(side="left")
        self.seg_contrast = Md3Segmented(self, holder, available_contrasts(),
                                         c["contrast"], self._on_contrast, width=220)
        self.seg_contrast.pack(side="left", padx=(12, 0))
        tk.Label(holder, text="схема:", bg=self.card_bg, fg=self.fg_muted,
                 font=self.font("label-medium")).pack(side="left", padx=(16, 4))
        self.scheme_var = tk.StringVar(value=c["scheme"])
        self.scheme_box = tk.OptionMenu(holder, self.scheme_var, *available_schemes(),
                                        command=self._on_scheme)
        self.scheme_box.config(bg=self.card_bg, fg=self.fg, relief="flat",
                               font=self.font("label-large"), highlightthickness=1,
                               highlightbackground=self.theme.role("outline"), bd=0)
        self.scheme_box.pack(side="left")

        # сиды
        seeds_frame = tk.Frame(card.body, bg=self.card_bg)
        seeds_frame.pack(fill="x", pady=(12, 4))
        tk.Label(seeds_frame, text="основной цвет", bg=self.card_bg, fg=self.fg,
                 font=self.font("label-medium")).pack(side="left")
        self.seed_entry = tk.Entry(seeds_frame, width=10, font=self.font("label-large"),
                                   bg=self.theme.role("surfaceContainerHigh"),
                                   fg=self.fg, insertbackground=self.fg,
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=self.theme.role("outline"))
        self.seed_entry.pack(side="right")
        self.seed_entry.insert(0, c["seed"])
        self.seed_entry.bind("<Return>", lambda e: self._on_seed(self.seed_entry.get()))
        self.seed_entry.bind("<FocusOut>", lambda e: self._on_seed(self.seed_entry.get()))

        self.chips = tk.Frame(card.body, bg=self.card_bg)
        self.chips.pack(fill="x", pady=(6, 0))
        self._build_seed_chips()

        pick = tk.Frame(card.body, bg=self.card_bg)
        pick.pack(fill="x", pady=(10, 0))
        Md3Button(self, pick, "Выбрать цвет…", self._pick_color, kind="tonal").pack(side="left")
        self.seed_info = tk.Label(pick, text="", bg=self.card_bg, fg=self.fg_muted,
                                  font=self.font("body-medium"))
        self.seed_info.pack(side="left", padx=12)

        # ===== ФОРМА И ELEVATION =====
        card = Card(self, self.left, "Форма и тени")
        self.card_shape = card
        self.slider_radius = Md3Slider(self, card.body, "Скругление углов",
                                       0, 32, c["corner_radius"], 2, "dp",
                                       self._on_radius)
        self.slider_radius.pack(fill="x")
        self.shape_tokens = tk.Label(card.body, text="", bg=self.card_bg, fg=self.fg_muted,
                                     font=self.font("body-medium"), anchor="w", justify="left")
        self.shape_tokens.pack(fill="x", pady=(2, 6))
        self.cb_round_dialogs = Md3Checkbox(self, card.body,
                                            "Скруглять диалоги и меню",
                                            value=c["round_dialogs"],
                                            command=lambda v: self._set("round_dialogs", v))
        self.cb_round_dialogs.pack(fill="x", pady=2)
        self.cb_shadows = Md3Checkbox(self, card.body, "Тени окон",
                                      value=c["shadows"],
                                      command=lambda v: self._set("shadows", v))
        self.cb_shadows.pack(fill="x", pady=2)
        self.cb_tinted = Md3Checkbox(self, card.body,
                                     "Оттенок теней под цвет темы",
                                     value=c["tinted_shadows"],
                                     command=lambda v: self._set("tinted_shadows", v))
        self.cb_tinted.pack(fill="x", pady=2)
        self.slider_elev = Md3Slider(self, card.body, "Глубина тени",
                                     1, 5, c["shadow_elevation"], 1, "",
                                     self._on_elevation)
        self.slider_elev.pack(fill="x", pady=(8, 0))
        self.elev_info = tk.Label(card.body, text="", bg=self.card_bg, fg=self.fg_muted,
                                  font=self.font("body-medium"), anchor="w")
        self.elev_info.pack(fill="x", pady=(2, 0))

        # ===== ПРОЗРАЧНОСТЬ И РАЗМЫТИЕ =====
        card = Card(self, self.left, "Прозрачность и размытие")
        self.card_alpha = card
        self.cb_dim = Md3Checkbox(self, card.body,
                                  "Затемнять неактивные окна",
                                  value=c["inactive_dim"],
                                  command=lambda v: self._set("inactive_dim", v))
        self.cb_dim.pack(fill="x", pady=2)
        self.slider_inactive = Md3Slider(self, card.body, "Непрозрачность неактивных окон",
                                         0.6, 1.0, c["inactive_opacity"], 0.01, "",
                                         self._on_inactive)
        self.slider_inactive.pack(fill="x", pady=(8, 0))
        self.slider_frame = Md3Slider(self, card.body, "Непрозрачность рамок",
                                      0.5, 1.0, c["frame_opacity"], 0.01, "",
                                      lambda v: self._set("frame_opacity", round(v, 2), quiet=True))
        self.slider_frame.pack(fill="x", pady=(8, 0))
        self.cb_blur = Md3Checkbox(self, card.body,
                                   "Размытие фона у меню и уведомлений",
                                   value=c["blur"], command=lambda v: self._set("blur", v))
        self.cb_blur.pack(fill="x", pady=(10, 2))
        self.slider_blur = Md3Slider(self, card.body, "Сила размытия",
                                     2, 40, c["blur_strength"], 1, "",
                                     lambda v: self._set("blur_strength", int(v), quiet=True))
        self.slider_blur.pack(fill="x", pady=(4, 0))

        # ===== MOTION =====
        card = Card(self, self.left, "Анимации")
        self.card_motion = card
        self.cb_anim = Md3Checkbox(self, card.body,
                                   "Анимации окон",
                                   value=c["animations"],
                                   command=lambda v: self._set("animations", v))
        self.cb_anim.pack(fill="x", pady=2)
        self.slider_scale = Md3Slider(self, card.body, "Масштаб при появлении",
                                      0.85, 1.0, c["animation_scale"], 0.01, "",
                                      lambda v: self._set("animation_scale", round(v, 2), quiet=True))
        self.slider_scale.pack(fill="x", pady=(8, 0))
        self.cb_fade = Md3Checkbox(self, card.body, "Плавное растворение окон",
                                   value=c["fade"], command=lambda v: self._set("fade", v))
        self.cb_fade.pack(fill="x", pady=(10, 2))

        # ===== BSPWM =====
        card = Card(self, self.left, "Окна и отступы")
        self.card_wm = card
        self.slider_gap = Md3Slider(self, card.body, "Расстояние между окнами", 0, 40, c["gap"], 2, "px",
                                    lambda v: self._set("gap", int(v), quiet=True))
        self.slider_gap.pack(fill="x")
        self.slider_pad = Md3Slider(self, card.body, "Отступы от краёв экрана", 0, 48, c["padding"], 2, "px",
                                    lambda v: self._set("padding", int(v), quiet=True))
        self.slider_pad.pack(fill="x", pady=(8, 0))
        self.slider_bw = Md3Slider(self, card.body, "Толщина рамки окна", 0, 8, c["border_width"], 1, "px",
                                   lambda v: self._set("border_width", int(v), quiet=True))
        self.slider_bw.pack(fill="x", pady=(8, 0))

        holder = tk.Frame(card.body, bg=self.card_bg)
        holder.pack(fill="x", pady=(12, 0))
        tk.Label(holder, text="рамка активного окна:", bg=self.card_bg, fg=self.fg_muted,
                 font=self.font("label-medium")).pack(side="left")
        self.seg_focus = Md3Segmented(self, holder,
                                      ["primary", "primary-container", "tertiary"],
                                      c["focus_style"], self._on_focus, width=360)
        self.seg_focus.pack(side="left", padx=(8, 0))

        backend_holder = tk.Frame(card.body, bg=self.card_bg)
        backend_holder.pack(fill="x", pady=(4, 0))
        tk.Label(backend_holder, text="рендер:", bg=self.card_bg, fg=self.fg_muted,
                 font=self.font("label-medium")).pack(side="left")
        self.seg_backend = Md3Segmented(self, backend_holder, ["egl", "glx"],
                                        c["backend"], self._on_backend, width=180)
        self.seg_backend.pack(side="left", padx=(8, 0))

        # ===== ОКРУЖЕНИЕ =====
        card = Card(self, self.left, "Система")
        self.card_env = card
        self.cb_bar = Md3Checkbox(self, card.body, "Запускать панель (polybar)",
                                  value=c["bar"], command=lambda v: self._set("bar", v))
        self.cb_bar.pack(fill="x", pady=2)
        self.cb_tray = Md3Checkbox(self, card.body, "Системный трей в панели",
                                   value=c["tray"], command=lambda v: self._set("tray", v))
        self.cb_tray.pack(fill="x", pady=2)
        self.cb_term = Md3Checkbox(self, card.body,
                                   "Перекрашивать терминал",
                                   value=c["terminal_colors"],
                                   command=lambda v: self._set("terminal_colors", v))
        self.cb_term.pack(fill="x", pady=2)
        self.cb_auto = Md3Checkbox(self, card.body,
                                   "Применять тему сразу",
                                   value=c["auto_apply"],
                                   command=lambda v: self._set("auto_apply", v))
        self.cb_auto.pack(fill="x", pady=2)

    def _build_seed_chips(self):
        import tkinter as tk

        for w in self.chips.winfo_children():
            w.destroy()
        self.chip_canvases = []
        for seed in available_seeds():
            cv = tk.Canvas(self.chips, width=34, height=34, highlightthickness=0,
                           bd=0, bg=self.card_bg, cursor="hand2")
            cv.pack(side="left", padx=(0, 6), pady=4)
            cv.bind("<Button-1>", lambda e, s=seed: self._on_seed(s))
            self.chip_canvases.append((cv, seed))
        self._paint_chips()

    def _paint_chips(self):
        cur = str(self.cfg.values["seed"]).upper()
        if not cur.startswith("#"):
            cur = "#" + cur
        for cv, seed in self.chip_canvases:
            cv.delete("all")
            cv.config(bg=self.card_bg)
            selected = (seed.upper() == cur)
            if selected:
                cv.create_oval(1, 1, 33, 33, outline=self.theme.role("primary"), width=3)
            cv.create_oval(5, 5, 29, 29, fill=seed, outline=self.theme.role("outlineVariant"),
                           width=1)

    # -- правая колонка --
    def _build_right(self):
        import tkinter as tk

        card = Card(self, self.right, "Превью")
        self.card_preview = card
        self.preview = DesktopPreview(self, card.body)
        self.preview.pack()

        card = Card(self, self.right, "Контраст")
        self.card_contrast = card
        self.contrast = ContrastCard(self, card.body)
        self.contrast.pack()

        card = Card(self, self.right, "Палитра")
        self.card_palette = card
        self.strip = TonalStrip(self, card.body)
        self.strip.pack()

    # -- нижняя панель (md.comp.bottom-app-bar с действиями) --
    def _build_bottom(self):
        import tkinter as tk

        bar = tk.Frame(self.root, bg=self.bg, height=64)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.bottom_bar = bar

        left = tk.Frame(bar, bg=self.bg)
        left.pack(side="left", padx=16)
        self.status = tk.Label(left, textvariable=self.status_text, bg=self.bg,
                               fg=self.fg_muted, font=self.font("body-medium"),
                               anchor="w")
        self.status.pack(side="left")

        right = tk.Frame(bar, bg=self.bg)
        right.pack(side="right", padx=16)
        self.btn_reset = Md3Button(self, right, "Сбросить", self.on_reset, kind="text")
        self.btn_reset.pack(side="left")
        self.btn_cli = Md3Button(self, right, "Открыть папку", self.on_open_folder, kind="outlined")
        self.btn_cli.pack(side="left")
        self.btn_apply = Md3Button(self, right, "Применить тему", self.on_apply, kind="tonal")
        self.btn_apply.pack(side="left")
        self.btn_save = Md3Button(self, right, "Сохранить и перезапустить", self.on_save_restart,
                                  kind="filled")
        self.btn_save.pack(side="left")

    # ======================================================================= #
    # Обработчики
    # ======================================================================= #
    def _set(self, key: str, value: Any, quiet: bool = False) -> None:
        self.cfg.set(key, value)
        if key in ("corner_radius",) and not quiet:
            pass
        if not quiet:
            self.refresh(animate=False)
            self._autosave(apply_now=True)
        else:
            # «тихие» изменения (слайдеры в движении) — только превью, сохраним позже
            self._refresh_theme_only()

    def _on_mode(self, mode: str) -> None:
        self._set("dark", mode == "dark")

    def _on_contrast(self, value: str) -> None:
        self._set("contrast", value)

    def _on_scheme(self, value: str) -> None:
        self._set("scheme", value)

    def _on_focus(self, value: str) -> None:
        self._set("focus_style", value)

    def _on_backend(self, value: str) -> None:
        self._set("backend", value)

    def _on_seed(self, value: str) -> None:
        value = str(value).strip()
        if not value:
            return
        if not value.startswith("#"):
            value = "#" + value
        value = value.upper()
        if len(value) != 7:
            self._status(f"«{value}» — нужен формат #RRGGBB", error=True)
            return
        try:
            hex_to_rgb(value)
        except Exception:
            self._status(f"«{value}» — не hex-цвет", error=True)
            return
        self.seed_entry.delete(0, "end")
        self.seed_entry.insert(0, value)
        self._set("seed", value)

    def _pick_color(self):
        from tkinter import colorchooser

        rgb, hexv = colorchooser.askcolor(color=self.cfg.values["seed"],
                                          title="source color (seed)")
        if hexv:
            self._on_seed(hexv)

    def _on_radius(self, v: float) -> None:
        self._set("corner_radius", int(v), quiet=True)
        self._refresh_theme_only()

    def _on_elevation(self, v: float) -> None:
        self._set("shadow_elevation", int(v), quiet=True)
        self._refresh_theme_only()

    def _on_inactive(self, v: float) -> None:
        self._set("inactive_opacity", round(v, 2), quiet=True)
        self._refresh_theme_only()

    # ======================================================================= #
    # Обновление темы
    # ======================================================================= #
    def _refresh_theme_only(self) -> None:
        """Пересчитать Theme и перерисовать превью БЕЗ записи на диск."""
        try:
            self.theme = Theme(self.cfg)
        except Exception as exc:
            self._status(f"ошибка темы: {exc}", error=True)
            return
        self._apply_palette()
        for w in THEMABLES:
            try:
                w.retheme(self.theme)
            except Exception:
                pass
        self._update_labels()

    def refresh(self, animate: bool = True) -> None:
        self._refresh_theme_only()
        self._paint_chips()

    def _update_labels(self) -> None:
        th, c = self.theme, self.cfg.values
        hct = load_palettes().get("seedHct", {}).get(th.seed)
        if hct:
            self.seed_info.config(
                text=f"тон {hct['tone']:.0f} · оттенок {hct['hue']:.0f}° · "
                     f"насыщенность {hct['chroma']:.0f}")
        else:
            self.seed_info.config(text=th.seed)

        self.subtitle.config(
            text=f"  {'тёмная' if th.dark else 'светлая'} · {th.scheme} · {th.seed}")

        r = c["corner_radius"]
        word = ("без скруглений" if r <= 0 else "едва заметные" if r <= 4 else
                "маленькие" if r <= 8 else "средние" if r <= 12 else
                "большие" if r <= 16 else "очень большие" if r <= 20 else "огромные")
        self.shape_tokens.config(text=f"углы: {word}")

        lvl = th.elevation_level
        depth = "лёгкая" if lvl <= 1 else "средняя" if lvl <= 3 else "глубокая"
        self.elev_info.config(text=f"тень: {depth} · размытие {th.shadow['blur']}px")

    # ======================================================================= #
    # Сохранение / применение
    # ======================================================================= #
    def _autosave(self, apply_now: bool = True) -> None:
        try:
            self.cfg.save()
            write_outputs(self.theme, self.cfg)
        except Exception as exc:
            self._status(f"не удалось сохранить: {exc}", error=True)
            return
        if apply_now and self.cfg.values["auto_apply"]:
            self._run_apply()
        else:
            self._status("сохранено · нажмите «Применить тему», чтобы применить к сессии")

    def _run_apply(self) -> None:
        script = HERE.parent / "bin" / "md3-apply"
        if not script.exists():
            self._status("сохранено · md3-apply не найден", error=True)
            return
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            self._status("сохранено · нет DISPLAY — применяю только файлы")
            return
        try:
            res = subprocess.run(["bash", str(script), "--quiet", "--restart"],
                                 capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                self._status("тема применена к сессии ✔")
            else:
                self._status(f"md3-apply: {(res.stderr or res.stdout or 'ошибка').strip()[:160]}",
                             error=True)
        except FileNotFoundError:
            self._status("сохранено · bash не найден")
        except subprocess.TimeoutExpired:
            self._status("md3-apply завис (>60 c) — проверьте лог", error=True)

    def on_apply(self) -> None:
        self._autosave(apply_now=False)
        self._run_apply()

    def on_save_restart(self) -> None:
        self._autosave(apply_now=False)
        self._status("перезапускаю сессию (bspc wm -r)…")
        self.root.update_idletasks()
        for cmd in (["bspc", "wm", "-r"],):
            try:
                subprocess.run(cmd, capture_output=True, timeout=10)
            except Exception:
                pass
        self._status("готово: bspwmrc перечитан (SIGHUP-путь: сервисы перезапущены)")

    def on_reset(self) -> None:
        self.cfg = Config()
        for w in THEMABLES:
            w.theme = None      # будет переустановлен в refresh
        self.theme = Theme(self.cfg)
        self._sync_widgets_from_cfg()
        self.refresh()
        self._autosave(apply_now=True)
        self._status("сброшено к baseline M3 (source #6750A4, tonal-spot, dark)")

    def on_open_folder(self) -> None:
        path = HERE.parent
        self._status(f"конфиги: {path}")
        for opener in (("xdg-open",), ("thunar",), ("nautilus",), ("pcmanfm",)):
            try:
                subprocess.Popen(list(opener) + [str(path)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue

    def _sync_widgets_from_cfg(self):
        c = self.cfg.values
        self.seg_mode.set("dark" if c["dark"] else "light")
        self.seg_contrast.set(c["contrast"])
        self.scheme_var.set(c["scheme"])
        self.seg_focus.set(c["focus_style"])
        self.seg_backend.set(c["backend"])
        self.seed_entry.delete(0, "end")
        self.seed_entry.insert(0, c["seed"])
        for cb, key in ((self.cb_round_dialogs, "round_dialogs"), (self.cb_shadows, "shadows"),
                        (self.cb_tinted, "tinted_shadows"), (self.cb_dim, "inactive_dim"),
                        (self.cb_blur, "blur"), (self.cb_anim, "animations"),
                        (self.cb_fade, "fade"), (self.cb_bar, "bar"),
                        (self.cb_tray, "tray"), (self.cb_term, "terminal_colors"),
                        (self.cb_auto, "auto_apply")):
            cb.set(bool(c[key]), animate=False)
        for sl, key in ((self.slider_radius, "corner_radius"),
                        (self.slider_elev, "shadow_elevation"),
                        (self.slider_inactive, "inactive_opacity"),
                        (self.slider_frame, "frame_opacity"),
                        (self.slider_blur, "blur_strength"),
                        (self.slider_scale, "animation_scale"),
                        (self.slider_gap, "gap"), (self.slider_pad, "padding"),
                        (self.slider_bw, "border_width")):
            sl.set(float(c[key]), animate=False)

    def _status(self, text: str, error: bool = False) -> None:
        self.status_text.set(text)
        self.status.config(fg=self.theme.role("error") if error else self.fg_muted)

    # -- перекраска всего окна при смене темы --
    def retheme(self, animate: bool = True) -> None:
        self._apply_palette()
        self.root.config(bg=self.bg)
        for frame in (self.appbar, self.bottom_bar, self.left, self.left_inner, self.right):
            try:
                frame.config(bg=self.bg)
            except Exception:
                pass
        self.subtitle.config(bg=self.bg, fg=self.fg_muted)
        self.status.config(bg=self.bg)
        for card in (self.card_color, self.card_shape, self.card_alpha, self.card_motion,
                     self.card_wm, self.card_env,
                     self.card_preview, self.card_contrast, self.card_palette):
            card.retheme(self.theme)
        self.seed_entry.config(bg=self.theme.role("surfaceContainerHigh"), fg=self.fg,
                               insertbackground=self.fg,
                               highlightbackground=self.theme.role("outline"))
        self.scheme_box.config(bg=self.card_bg, fg=self.fg,
                               highlightbackground=self.theme.role("outline"))
        try:
            self.scheme_box["menu"].config(bg=self.card_bg, fg=self.fg,
                                           activebackground=self.theme.role("primaryContainer"),
                                           activeforeground=self.theme.role("onPrimaryContainer"))
        except Exception:
            pass
        for w in THEMABLES:
            try:
                w.retheme(self.theme)
            except Exception:
                pass
        self._paint_chips()
        self._update_labels()

    def run(self) -> None:
        self.refresh(animate=False)
        self.retheme(animate=False)

        # при смене темы перерисовываем и фон окна
        orig_refresh = self.refresh

        def refresh_and_retheme(animate=True):
            orig_refresh(animate=animate)
            self.retheme(animate=animate)

        self.refresh = refresh_and_retheme
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        try:
            self.cfg.save()
            write_outputs(self.theme, self.cfg)
        finally:
            self.root.destroy()


# --------------------------------------------------------------------------- #
# CLI-режим (без X-сервера)
# --------------------------------------------------------------------------- #


def cli(argv: List[str]) -> int:
    cfg = Config.load()
    if "--list" in argv:
        print("Опции (generated/theme-state.json):")
        for k, v in sorted(Config().values.items()):
            cur = cfg.values[k]
            mark = "*" if cur != v else " "
            print(f" {mark} {k:22} = {cur!r:22} (по умолчанию {v!r})")
        print("\nseed-цвета :", " ".join(available_seeds()))
        print("schemes    :", " ".join(available_schemes()))
        print("contrasts  :", " ".join(available_contrasts()))
        print("shape scale:", " ".join(f"{k}={v}" for k, v in SHAPE_SCALE.items()))
        return 0
    if "--set" in argv:
        i = argv.index("--set")
        pairs = argv[i + 1:]
        for p in pairs:
            if "=" not in p:
                print(f"пропускаю '{p}' (нужно key=value)", file=sys.stderr)
                continue
            k, v = p.split("=", 1)
            cfg.set(k.strip(), v.strip())
        cfg.save()
        th = Theme(cfg)
        write_outputs(th, cfg)
        print(f"сохранено: seed={th.seed} scheme={th.scheme}/{th.contrast}/"
              f"{'dark' if th.dark else 'light'} radius={cfg.values['corner_radius']}dp")
    if "--apply" in argv:
        script = HERE.parent / "bin" / "md3-apply"
        return subprocess.call(["bash", str(script), "--restart"])
    if "--print" in argv:
        print(Theme(cfg).to_shell())
        return 0
    print(__doc__)
    return 1


def main(argv: List[str]) -> int:
    if "--cli" in argv or "--help" in argv or "-h" in argv:
        return cli(argv)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("tkinter не найден (нужен пакет python3-tk).", file=sys.stderr)
        print("Работает headless-режим:  md3-theme-gui.py --cli --list", file=sys.stderr)
        return cli(argv + ["--list"])
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("Нет DISPLAY — запускаю CLI-режим.", file=sys.stderr)
        return cli(argv + ["--list"])
    try:
        cfg = Config.load()
        App(cfg).run()
        return 0
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print(f"\nGUI не запустился: {exc}\nДоступен CLI: {sys.argv[0]} --cli --list",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
