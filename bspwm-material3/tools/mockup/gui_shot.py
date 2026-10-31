#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_shot.py — «скриншот» GUI-редактора темы БЕЗ X11.

Прогоняем настоящий tools/md3-theme-gui.py (класс App) поверх фейкового
tkinter из tools/tests/test_widgets_headless.py, досчитываем анимации до
установившегося состояния, затем мини-движок pack-раскладки расставляет
виджеты, а записанные canvas-команды + Label/Entry рендерятся в SVG → PNG.

    python3 tools/mockup/gui_shot.py [out.svg]
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "tests"))

# берём ТОЛЬКО fake-tk часть тестового харнеса (до загрузки GUI и самих тестов)
_src = (ROOT / "tools/tests/test_widgets_headless.py").read_text(encoding="utf-8")
_cut = _src.index('spec = importlib.util.spec_from_file_location("gui"')
H = types.ModuleType("harness")
H.__dict__["__name__"] = "harness"
H.__dict__["__file__"] = str(ROOT / "tools/tests/test_widgets_headless.py")
exec(compile(_src[:_cut], "test_widgets_headless.py(fakes)", "exec"), H.__dict__)
H.install_fake_tkinter()

tk = sys.modules["tkinter"]
ttk = sys.modules["tkinter.ttk"]

#------------------------------------------------------------------------------
# 1. Расширяем фейки: дети, kind, create_window, Entry.get/insert, OptionMenu
#------------------------------------------------------------------------------
_orig_canvas_init = H.FakeCanvas.__init__
_orig_widget_init = H.FakeWidget.__init__


def _canvas_init(self, master=None, **kw):
    _orig_canvas_init(self, master, **kw)
    self.kind = "canvas"
    self._children = []
    self._windows = []
    if master is not None and hasattr(master, "_children"):
        master._children.append(self)


def _widget_init(self, master=None, **kw):
    _orig_widget_init(self, master, **kw)
    self._children = []
    if master is not None and hasattr(master, "_children"):
        master._children.append(self)


H.FakeCanvas.__init__ = _canvas_init
H.FakeWidget.__init__ = _widget_init
H.FakeCanvas.create_window = lambda self, pos, window=None, **kw: (
    self._windows.append((pos, window)) or len(self._windows))
H.FakeCanvas.bbox = lambda self, *a: (0, 0, 800, 600)
H.FakeCanvas.itemconfigure = lambda self, *a, **kw: None
H.FakeCanvas.yview_scroll = lambda self, *a, **kw: None
H.FakeCanvas.yview = lambda self, *a: (0.0, 1.0)
H.FakeCanvas.update = lambda self: None
H.FakeWidget.winfo_children = lambda self: list(getattr(self, "_children", []))
H.FakeWidget.update = lambda self: None
H.FakeWidget.update_idletasks = lambda self: None
H.FakeWidget.winfo_width = lambda self: 600
H.FakeWidget.insert = lambda self, i, s: self.opts.setdefault("_text", "") or self.opts.update(_text=self.opts.get("_text", "") + s)
H.FakeWidget.get = lambda self: self.opts.get("_text", "")
H.FakeWidget.delete = lambda self, *a: self.opts.update(_text="")
for _m in ("attributes", "resizable", "iconphoto", "state", "deiconify", "focus_set", "lift"):
    setattr(H.FakeRoot, _m, lambda self, *a, **kw: None)
H.FakeRoot._children = []


def _mk(kind):
    def f(master=None, *args, **kw):
        w = H.FakeWidget(master, **kw)
        w.kind = kind
        if kind == "option" and args:
            w.opts["_var"] = args[0]
            w.opts["_choices"] = list(args[1:])
        return w
    return f


# недостающие API для запуска ВСЕГО приложения (тестам они не требовались)
H.FakeWidget.set = lambda self, *a, **k: None
for _m in ("yview", "xview", "yview_scroll", "xview_scroll", "itemconfigure", "update"):
    setattr(H.FakeCanvas, _m, lambda self, *a, **k: None)
H.FakeCanvas.bbox = lambda self, *a: (0, 0, 800, 600)
H.FakeCanvas.create_window = lambda self, pos, window=None, **kw: (
    self._windows.append((pos, window)) or len(self._windows))
for _m in ("attributes", "resizable", "iconphoto", "state", "overrideredirect",
           "columnconfigure", "rowconfigure", "focus_set", "clipboard_clear",
           "clipboard_append", "option_add", "tk_strictMotif"):
    setattr(H.FakeRoot, _m, lambda self, *a, **k: None)

tk.Frame = _mk("frame")
tk.Label = _mk("label")
tk.Entry = _mk("entry")
tk.OptionMenu = _mk("option")
ttk.Scrollbar = _mk("scrollbar")

_sf = sys.modules["tkinter.font"]


def _measure(self, s):
    return len(s) * 0.6 * self.kw.get("size", 11)


_sf.Font.measure = _measure
_sf.Font.metrics = lambda self, *a: {"ascent": self.kw.get("size", 11), "descent": 3}

#------------------------------------------------------------------------------
# 2. Виртуальные часы → анимации досчитываются мгновенно
#------------------------------------------------------------------------------
_gspec = importlib.util.spec_from_file_location("md3_theme_gui", ROOT / "tools/md3-theme-gui.py")
G = importlib.util.module_from_spec(_gspec)
sys.modules["md3_theme_gui"] = G
_gspec.loader.exec_module(G)


class VTime:
    def __init__(self):
        self.t = 1000.0

    def perf_counter(self):
        self.t += 9.0
        return self.t / 1000.0

    def sleep(self, s):
        pass

    def time(self):
        return self.perf_counter()


G.time = VTime()

from md3_theme import Config  # noqa: E402

app = G.App(Config.load())
for _ in range(6000):
    if not app.root.step(1):
        break

#------------------------------------------------------------------------------
# 3. Мини-движок pack-раскладки
#------------------------------------------------------------------------------
ADV = 0.6


def fsize(w):
    f = w.opts.get("font")
    return (f.kw.get("size", 11) if hasattr(f, "kw") else 11), (f.kw.get("weight", "normal") if hasattr(f, "kw") else "normal")


def wrap(text, width_px, size):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if len(t) * ADV * size <= width_px or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def req_size(w, avail_w):
    kind = getattr(w, "kind", "canvas")
    if kind == "canvas":
        try:
            return int(w.opts["width"]), int(w.opts["height"])
        except KeyError:
            xs = [0]
            ys = [0]
            for _t, coords, _k in w.items:
                nums = list(coords)
                xs += nums[0::2]
                ys += nums[1::2]
            return int(max(xs)) + 4, int(max(ys)) + 4
    if kind == "label":
        size, _w = fsize(w)
        text = w.opts.get("text") or (w.opts.get("textvariable").get() if w.opts.get("textvariable") else "")
        wl = w.opts.get("wraplength") or avail_w
        lines = wrap(str(text), min(wl, avail_w), size)
        h = len(lines) * int(size * 1.5)
        return int(max(len(l) for l in lines) * ADV * size) + 4, h + 2
    if kind == "entry":
        size, _w = fsize(w)
        return int(w.opts.get("width", 10)) * int(ADV * size) + 14, int(size * 1.6) + 10
    if kind == "option":
        size, _w = fsize(w)
        var = w.opts.get("_var")
        txt = var.get() if var else ""
        return int(len(txt) * ADV * size) + 34, int(size * 1.6) + 10
    if kind == "scrollbar":
        return 13, 100
    # frame: дети
    pad = padx = pady = 0
    cw = ch = 0
    left_x = top_y = 0
    for c in getattr(w, "_children", []):
        pk = c.opts.get("_packed", {})
        side = pk.get("side", "top")
        cw_, ch_ = req_size(c, avail_w - 40)
        ppx, ppy = norm_pad(pk.get("padx", 0)), norm_pad(pk.get("pady", 0))
        if side in ("left", "right"):
            left_x += cw_ + ppx[0] + ppx[1]
            ch = max(ch, ch_ + ppy[0] + ppy[1])
        else:
            top_y += ch_ + ppy[0] + ppy[1]
            cw = max(cw, cw_ + ppx[0] + ppx[1])
    if getattr(w, "_children", None):
        return max(cw, left_x), max(ch, top_y)
    try:
        return int(w.opts.get("width", 0)), int(w.opts.get("height", 0))
    except TypeError:
        return 0, 0


def norm_pad(p):
    if isinstance(p, (tuple, list)):
        return int(p[0]), int(p[1] if len(p) > 1 else p[0])
    return int(p), int(p)


BOXES = {}   # id(widget) → (x, y, w, h)


def layout(w, x, y, avail_w, avail_h):
    """pack-подобная раскладка детей w внутри (x,y,avail_w,avail_h)."""
    BOXES[id(w)] = (x, y, avail_w, avail_h)
    free = [x, y, avail_w, avail_h]
    for c in getattr(w, "_children", []):
        pk = c.opts.get("_packed", {})
        side = pk.get("side", "top")
        fill = pk.get("fill", "")
        expand = pk.get("expand", False)
        ppx, ppy = norm_pad(pk.get("padx", 0)), norm_pad(pk.get("pady", 0))
        cw, ch = req_size(c, free[2])
        if expand and side in ("left", "right"):
            cw = max(cw, free[2] - ppx[0] - ppx[1])
        if c.kind == "canvas" and fill in ("x", "both"):
            cw = free[2] - ppx[0] - ppx[1]
        if fill in ("x", "both") and side in ("top", "bottom", ""):
            cw = free[2] - ppx[0] - ppx[1]
        if fill in ("y", "both") and side in ("left", "right"):
            ch = free[3] - ppy[0] - ppy[1]
        if side == "left":
            cx, cy = free[0] + ppx[0], free[1] + (free[3] - ch) // 2
            free[0] += cw + ppx[0] + ppx[1]
            free[2] -= cw + ppx[0] + ppx[1]
        elif side == "right":
            cx = free[0] + free[2] - cw - ppx[1]
            cy = free[1] + (free[3] - ch) // 2
            free[2] -= cw + ppx[0] + ppx[1]
        elif side == "bottom":
            cx = free[0] + (free[2] - cw) // 2
            cy = free[1] + free[3] - ch - ppy[1]
            free[3] -= ch + ppy[0] + ppy[1]
        else:  # top
            cx = free[0] + (free[2] - cw) // 2
            cy = free[1] + ppy[0]
            free[1] += ch + ppy[0] + ppy[1]
            free[3] -= ch + ppy[0] + ppy[1]
        layout(c, cx, cy, cw, ch)


WIN_W, WIN_H = 1240, 880
# верхняя панель / нижняя панель / тело — как в _build
appbar, bottom, body = app.appbar, app.bottom_bar, None
for ch in app.root._children:
    if ch not in (appbar, bottom):
        body = ch
layout(appbar, 0, 0, WIN_W, 64)
layout(bottom, 0, WIN_H - 64, WIN_W, 64)
bx, by, bw, bh = 0, 64, WIN_W, WIN_H - 128
BOXES[id(body)] = (bx, by, bw, bh)
right = None
for ch in body._children:
    if getattr(ch, "opts", {}).get("width") == 600:
        right = ch
left_outer = [c for c in body._children if c is not right][0]
rw = 608
layout(right, bx + bw - rw, by, rw - 8, bh)
lox, loy, low, loh = bx, by, bw - rw, bh
BOXES[id(left_outer)] = (lox, loy, low, loh)
vsb = [c for c in left_outer._children if getattr(c, "kind", "") == "scrollbar"]
lcan = [c for c in left_outer._children if c not in vsb][0]
if vsb:
    layout(vsb[0], lox + low - 13, loy, 13, loh)
layout(lcan, lox, loy, low - (13 if vsb else 0), loh)
# контент скролл-области: create_window(left_inner) с (0,0)
for _pos, win in lcan._windows:
    layout(win, lox, loy, low - 13, 4000)

#------------------------------------------------------------------------------
# 4. SVG-эмиссия
#------------------------------------------------------------------------------
esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
SVG = []


def emit_canvas(w):
    x, y, cw, ch = BOXES[id(w)]
    bg = w.opts.get("bg", "")
    if bg and bg != "":
        SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="{bg}"/>')
    for kind, coords, kw in w.items:
        fill = kw.get("fill", "")
        outline = kw.get("outline", "")
        width = kw.get("width", 1)
        if kind == "rect":
            x1, y1, x2, y2 = coords
            attrs = f'x="{x + x1}" y="{y + y1}" width="{max(0, x2 - x1)}" height="{max(0, y2 - y1)}"'
            if fill and fill != "":
                SVG.append(f"<rect {attrs} fill=\"{fill}\"/>")
            if outline and outline != "":
                SVG.append(f"<rect {attrs} fill=\"none\" stroke=\"{outline}\" stroke-width=\"{width}\"/>")
        elif kind == "oval":
            x1, y1, x2, y2 = coords
            cx, cy = x + (x1 + x2) / 2, y + (y1 + y2) / 2
            rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
            if fill and fill != "":
                SVG.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}"/>')
            if outline and outline != "":
                SVG.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{outline}" stroke-width="{width}"/>')
        elif kind == "line":
            pts = " ".join(f"{x + coords[i]},{y + coords[i + 1]}" for i in range(0, len(coords), 2))
            cap = "round" if kw.get("cap" ) == "round" else "butt"
            SVG.append(f'<polyline points="{pts}" fill="none" stroke="{fill or outline}" stroke-width="{width}" stroke-linecap="{cap}"/>')
        elif kind == "poly":
            pts = " ".join(f"{x + coords[i]},{y + coords[i + 1]}" for i in range(0, len(coords), 2))
            SVG.append(f'<polygon points="{pts}" fill="{fill}" stroke="{outline or "none"}" stroke-width="{width if outline else 0}"/>')
        elif kind == "text":
            tx, ty = x + coords[0], y + coords[1]
            f = kw.get("font")
            size = f.kw.get("size", 11) if hasattr(f, "kw") else 11
            weight = f.kw.get("weight", "normal") if hasattr(f, "kw") else "normal"
            anchor = kw.get("anchor", "center")
            ta = {"w": "start", "sw": "start", "nw": "start", "e": "end", "se": "end", "ne": "end"}.get(anchor, "middle")
            vb = {"nw": "hanging", "n": "hanging", "ne": "hanging", "sw": "auto", "s": "auto", "se": "auto"}.get(anchor, "central")
            fw = ' font-weight="700"' if weight == "bold" else ""
            SVG.append(f'<text x="{tx}" y="{ty}" font-size="{size}"{fw} fill="{kw.get("fill", "#fff")}" '
                       f'text-anchor="{ta}" dominant-baseline="{vb}" xml:space="preserve">{esc(kw.get("text", ""))}</text>')


def emit_widget(w):
    kind = getattr(w, "kind", "frame")
    x, y, cw, ch = BOXES.get(id(w), (0, 0, 0, 0))
    if kind == "canvas":
        emit_canvas(w)
        for c in getattr(w, "_children", []):
            emit_widget(c)
        for _pos, win in getattr(w, "_windows", []):
            emit_widget(win)
        return
    bg = w.opts.get("bg", "")
    if kind == "label":
        if bg:
            SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="{bg}"/>')
        size, weight = fsize(w)
        text = w.opts.get("text") or (w.opts.get("textvariable").get() if w.opts.get("textvariable") else "")
        lines = wrap(str(text), max(40, cw + 2), size)
        fw = ' font-weight="700"' if weight == "bold" else ""
        for i, ln in enumerate(lines):
            SVG.append(f'<text x="{x + 2}" y="{y + int(size * 1.1) + i * int(size * 1.5)}" font-size="{size}"{fw} '
                       f'fill="{w.opts.get("fg", "#fff")}" xml:space="preserve">{esc(ln)}</text>')
    elif kind == "entry":
        SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="6" fill="{w.opts.get("bg", "#222")}"/>')
        SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="6" fill="none" '
                   f'stroke="{w.opts.get("highlightbackground", "#666")}" stroke-width="1"/>')
        size, _wt = fsize(w)
        SVG.append(f'<text x="{x + 7}" y="{y + ch / 2}" font-size="{size}" fill="{w.opts.get("fg", "#fff")}" '
                   f'dominant-baseline="central">{esc(w.get())}</text>')
    elif kind == "option":
        SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="6" fill="{w.opts.get("bg", "#222")}"/>')
        SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="6" fill="none" '
                   f'stroke="{w.opts.get("highlightbackground", "#666")}" stroke-width="1"/>')
        size, _wt = fsize(w)
        var = w.opts.get("_var")
        SVG.append(f'<text x="{x + 8}" y="{y + ch / 2}" font-size="{size}" fill="{w.opts.get("fg", "#fff")}" '
                   f'dominant-baseline="central">{esc(var.get() if var else "")}</text>')
        SVG.append(f'<polygon points="{x + cw - 16},{y + ch / 2 - 3} {x + cw - 8},{y + ch / 2 - 3} '
                   f'{x + cw - 12},{y + ch / 2 + 3}" fill="{w.opts.get("fg", "#fff")}"/>')
    elif kind == "scrollbar":
        SVG.append(f'<rect x="{x + 4}" y="{y}" width="5" height="{ch}" rx="2.5" fill="#3b383e"/>')
    elif kind == "frame":
        ht = w.opts.get("highlightthickness", 0)
        if ht:
            SVG.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="12" fill="{bg or "none"}" '
                       f'stroke="{w.opts.get("highlightbackground", "#444")}" stroke-width="{ht}"/>')
    for c in getattr(w, "_children", []):
        emit_widget(c)
    for _pos, win in getattr(w, "_windows", []):
        emit_widget(win)


# окно поверх обоев, как сфокусированное окно bspwm: рамка primary, radius 12
WP = (ROOT / "wallpapers/md3-dark.png").read_bytes()
import base64
wp64 = base64.b64encode(WP).decode()
OX, OY = 340, 100
R = app.theme.roles
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">',
    f'<defs><style>text{{font-family:"JetBrains Mono";}}</style>'
    f'<filter id="ws" x="-20%" y="-20%" width="140%" height="140%">'
    f'<feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#000" flood-opacity="0.55"/></filter>'
    f'<clipPath id="wc"><rect x="0" y="0" width="{WIN_W}" height="{WIN_H}" rx="12"/></clipPath></defs>',
    f'<image x="0" y="0" width="1920" height="1080" href="data:image/png;base64,{wp64}" preserveAspectRatio="xMidYMid slice"/>',
    f'<g filter="url(#ws)"><rect x="{OX}" y="{OY}" width="{WIN_W}" height="{WIN_H}" rx="12" fill="{app.bg}"/></g>',
    f'<g clip-path="url(#wc)" transform="translate({OX},{OY})">',
]
import os as _os
if _os.environ.get("GUI_DEBUG"):
    print("DEBUG lcan._windows:", len(lcan._windows))
    if lcan._windows:
        li = lcan._windows[0][1]
        print("DEBUG left_inner children:", len(li._children),
              [getattr(c, "kind", "?") for c in li._children])
        print("DEBUG BOXES left_inner:", BOXES.get(id(li)))
    print("DEBUG body children:", [(getattr(c, "kind", "?"), BOXES.get(id(c))) for c in body._children])
SVG.clear()
for ch in app.root._children:
    emit_widget(ch)
parts.extend(SVG)
parts.append("</g>")
parts.append(f'<rect x="{OX}" y="{OY}" width="{WIN_W}" height="{WIN_H}" rx="12" fill="none" '
             f'stroke="{R["primary"]}" stroke-width="2"/>')
parts.append("</svg>")
out = HERE / (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".svg") else "gui.svg")
out.write_text("\n".join(parts), encoding="utf-8")
print("✔", out, len(SVG), "draw-операций")
