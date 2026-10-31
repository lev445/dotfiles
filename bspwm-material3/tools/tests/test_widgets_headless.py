#!/usr/bin/env python3
"""
headless-проверка MD3-виджетов GUI: подменяем tkinter «рекордером» и смотрим,
что рисуется (цвета/геометрия) и как идёт анимация (350/150 мс, easing).

Запуск:  python3 tools/tests/test_widgets_headless.py
"""
import importlib.util
import math
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

# --------------------------------------------------------------------------- #
# Фейковый tkinter
# --------------------------------------------------------------------------- #

CALLS = []


class FakeCanvas:
    def __init__(self, master=None, **kw):
        self.master = master
        self.opts = dict(kw)
        self.items = []
        for m in ("<Button-1>", "<ButtonRelease-1>", "<Enter>", "<Leave>", "<Motion>",
                  "<B1-Motion>", "<FocusIn>", "<FocusOut>", "<KeyPress-space>",
                  "<Return>", "<Left>", "<Right>", "<Button-4>", "<Button-5>",
                  "<MouseWheel>"):
            self._binds = {}
        self._binds = {}

    # --- API, который использует GUI ---
    def delete(self, *a):
        self.items = []

    def config(self, **kw):
        self.opts.update(kw)

    def configure(self, **kw):
        self.opts.update(kw)

    def __getitem__(self, k):
        return self.opts.get(k, 0)

    def __setitem__(self, k, v):
        self.opts[k] = v

    def bind(self, seq, fn, add=None):
        self._binds[seq] = fn

    def pack(self, **kw):
        self.opts["_packed"] = kw

    def grid(self, **kw):
        pass

    def winfo_children(self):
        return []

    def create_oval(self, x1, y1, x2, y2, **kw):
        CALLS.append(("oval", (x1, y1, x2, y2), kw))
        self.items.append(("oval", (x1, y1, x2, y2), kw))
        return len(self.items)

    def create_rectangle(self, x1, y1, x2, y2, **kw):
        CALLS.append(("rect", (x1, y1, x2, y2), kw))
        self.items.append(("rect", (x1, y1, x2, y2), kw))
        return len(self.items)

    def create_line(self, *coords, **kw):
        CALLS.append(("line", coords, kw))
        self.items.append(("line", coords, kw))
        return len(self.items)

    def create_polygon(self, pts, **kw):
        CALLS.append(("poly", tuple(pts), kw))
        self.items.append(("poly", tuple(pts), kw))
        return len(self.items)

    def create_text(self, x, y, **kw):
        CALLS.append(("text", (x, y), kw))
        self.items.append(("text", (x, y), kw))
        return len(self.items)

    def fire(self, seq, **ev):
        e = types.SimpleNamespace(x=ev.get("x", 0), y=ev.get("y", 0), delta=ev.get("delta", 0))
        fn = self._binds.get(seq)
        if fn:
            fn(e)


class FakeWidget:
    def __init__(self, master=None, **kw):
        self.master = master
        self.opts = dict(kw)
        self._children = []
        self._binds = {}

    def config(self, **kw):
        self.opts.update(kw)

    configure = config

    def __getitem__(self, k):
        return self.opts.get(k, "")

    def pack(self, **kw):
        self.opts["_packed"] = kw
        return self

    def pack_propagate(self, v):
        pass

    def grid(self, **kw):
        pass

    def bind(self, seq, fn, add=None):
        self._binds[seq] = fn

    def winfo_children(self):
        return self._children

    def insert(self, *a, **k):
        pass

    def delete(self, *a):
        pass

    def destroy(self):
        pass

    def fire(self, seq, **ev):
        e = types.SimpleNamespace(x=ev.get("x", 0), y=ev.get("y", 0))
        fn = self._binds.get(seq)
        if fn:
            fn(e)


class FakeVar:
    def __init__(self, value=None, **kw):
        self._v = value

    def set(self, v):
        self._v = v

    def get(self):
        return self._v


class FakeStyle:
    def theme_use(self, *a):
        pass


class FakeRoot:
    def __init__(self):
        self.pending = []
        self._binds = {}

    def title(self, *a):
        pass

    def geometry(self, *a):
        pass

    def minsize(self, *a):
        pass

    def config(self, **kw):
        pass

    configure = config

    def update_idletasks(self):
        pass

    def protocol(self, *a):
        pass

    def mainloop(self):
        pass

    def destroy(self):
        pass

    def withdraw(self):
        pass

    def after(self, ms, fn=None):
        if fn:
            self.pending.append(fn)
        return len(self.pending)

    def step(self, n=1):
        """выполнить n отложенных кадров анимации"""
        for _ in range(n):
            if not self.pending:
                return False
            batch, self.pending = self.pending[:], []
            for fn in batch:
                fn()
        return True


def install_fake_tkinter():
    tk = types.ModuleType("tkinter")
    tk.Canvas = FakeCanvas
    tk.Frame = FakeWidget
    tk.Label = FakeWidget
    tk.Entry = FakeWidget
    tk.OptionMenu = FakeWidget
    tk.StringVar = FakeVar
    tk.Tk = FakeRoot
    tk.Widget = FakeWidget

    font = types.ModuleType("tkinter.font")

    class FakeFont:
        def __init__(self, **kw):
            self.kw = kw

    font.Font = FakeFont
    font.families = lambda root=None: ["DejaVu Sans"]
    tk.font = font

    ttk = types.ModuleType("tkinter.ttk")
    ttk.Style = lambda root=None: FakeStyle()
    ttk.Scrollbar = FakeWidget
    tk.ttk = ttk

    cc = types.ModuleType("tkinter.colorchooser")
    cc.askcolor = lambda color=None, title=None: ((102, 84, 163), "#6655a3")
    tk.colorchooser = cc

    sys.modules["tkinter"] = tk
    sys.modules["tkinter.font"] = font
    sys.modules["tkinter.ttk"] = ttk
    sys.modules["tkinter.colorchooser"] = cc
    return tk


install_fake_tkinter()

spec = importlib.util.spec_from_file_location("gui", ROOT / "tools" / "md3-theme-gui.py")
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)

from md3_theme import CHECKBOX, Config, Theme, relative_luminance  # noqa: E402

# --------------------------------------------------------------------------- #
# Мини-«приложение»
# --------------------------------------------------------------------------- #


class MiniApp:
    def __init__(self):
        self.cfg = Config()
        self.theme = Theme(self.cfg)
        self.root = FakeRoot()
        self.bg = self.theme.role("surfaceContainer")
        self.card_bg = self.theme.elevation[1]
        self.fg = self.theme.role("onSurface")
        self.fg_muted = self.theme.role("onSurfaceVariant")
        self.accent = self.theme.role("primary")
        self.outline_variant = self.theme.role("outlineVariant")

    def font(self, token):
        return ("font", token)


PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✔ {name}")
    else:
        FAIL += 1
        print(f"  ✘ {name} {extra}")


app = MiniApp()

print("\n=== MD3 Checkbox: геометрия и цвета ===")
CALLS.clear()
cb = gui.Md3Checkbox(app, FakeWidget(), "Тест", value=False)
canvas = cb.canvas
# unselected: есть outline-круг/полигон цветом on-surface-variant, нет фона primary
unsel = list(canvas.items)
check("unselected: рисуется контейнер", len(unsel) >= 1, f"items={len(unsel)}")
outline_polys = [i for i in unsel if i[0] == "poly" and i[2].get("outline")]
check("unselected: outline = on-surface-variant",
      any(i[2]["outline"] == app.theme.role("onSurfaceVariant") for i in outline_polys),
      str([i[2].get("outline") for i in outline_polys]))
check("unselected: нет заливки primary",
      not any(i[2].get("fill") == app.theme.role("primary") for i in unsel if i[0] == "poly"))

# hover → state layer 8 % от on-surface
CALLS.clear()
cb.canvas.fire("<Enter>")
hover_items = list(cb.canvas.items)
expected_layer = gui.mix_alpha(app.theme.role("primary"), app.card_bg, 0.08)  # md.comp.checkbox: hover layer = primary
check("hover: state layer = primary @ 8 % (md.comp.checkbox), овал ~40dp",
      any(i[0] == "oval" and i[2].get("fill") == expected_layer for i in hover_items),
      f"want {expected_layer}")
ovals = [i for i in hover_items if i[0] == "oval"]
if ovals:
    x1, y1, x2, y2 = ovals[0][1]
    check("hover: state layer ≈ 36dp (40dp минус поля ячейки)", 30 <= (x2 - x1) <= 40,
          f"size={x2-x1}")

# checked → container = primary, icon = on-primary
CALLS.clear()
cb.set(True, animate=False)
checked = list(cb.canvas.items)
check("checked: контейнер залит primary",
      any(i[0] == "poly" and i[2].get("fill") == app.theme.role("primary") for i in checked))
check("checked: галочка = on-primary",
      any(i[0] == "line" and i[2].get("fill") == app.theme.role("onPrimary") for i in checked))
lines = [i for i in checked if i[0] == "line"]
check("checked: ровно 2 mark-сегмента (short+long), как в material-web", len(lines) == 2,
      f"lines={len(lines)}")
if len(lines) == 2:
    (ox, oy) = lines[0][1][0:2]
    (sx, sy) = lines[0][1][2:4]
    (lx, ly) = lines[1][1][2:4]
    short = math.hypot(sx - ox, sy - oy)
    long_ = math.hypot(lx - ox, ly - oy)
    check(f"short mark ≈ √32 = 5.657 (получено {short:.3f})", abs(short - math.sqrt(32)) < 0.6)
    check(f"long mark ≈ √128 = 11.314 (получено {long_:.3f})", abs(long_ - math.sqrt(128)) < 1.0)
    check("stroke 2dp", lines[0][2].get("width") == 2, str(lines[0][2].get("width")))

# indeterminate
CALLS.clear()
cb.state = "indeterminate"
cb.progress = 1.0
cb.redraw()
ind = [i for i in cb.canvas.items if i[0] == "line"]
check("indeterminate: одна горизонтальная черта 10dp", len(ind) == 1 and
      abs((ind[0][1][2] - ind[0][1][0]) - 10) < 0.6, str(ind[:1]))

# disabled 38 %
CALLS.clear()
cb.set_disabled(True)
dis = list(cb.canvas.items)
exp = gui.mix_alpha(app.theme.role("onSurface"), app.card_bg, 0.38)
check("disabled: контейнер = on-surface @ 38 %",
      any(i[0] == "poly" and i[2].get("fill") == exp for i in dis), f"want {exp}")

print("\n=== MD3 Checkbox: анимация (350 ms enter / 150 ms exit) ===")
cb2 = gui.Md3Checkbox(app, FakeWidget(), "Анимация", value=False)
app.root.pending.clear()
t0 = time.perf_counter()
cb2.set(True, animate=True)
frames = 0
samples = []
while app.root.pending and frames < 400:
    time.sleep(0.004)
    app.root.step(1)
    frames += 1
    samples.append((time.perf_counter() - t0, cb2.progress))
dur = samples[-1][0] if samples else 0
check(f"enter trwa ~350 ms (получено {dur*1000:.0f} ms, кадров {frames})",
      0.30 <= dur <= 0.45, f"dur={dur:.3f}")
check("progress: 0 → 1", samples and samples[0][1] < 0.35 and samples[-1][1] == 1.0,
      f"first={samples[0][1]:.3f}" if samples else "")
# easing: emphasized-decelerate должен «выстрелить» вперёд в первой четверти
q = [p for t, p in samples if t <= dur * 0.25]
check("easing = emphasized-decelerate (быстрый старт)",
      bool(q) and max(q) > 0.6, f"max@25%={max(q) if q else None}")

app.root.pending.clear()
t0 = time.perf_counter()
cb2.set(False, animate=True)
frames = 0
samples = []
while app.root.pending and frames < 400:
    time.sleep(0.002)
    app.root.step(1)
    frames += 1
    samples.append((time.perf_counter() - t0, cb2.progress))
dur2 = samples[-1][0] if samples else 0
check(f"exit trwa ~150 ms (получено {dur2*1000:.0f} ms)", 0.12 <= dur2 <= 0.24, f"dur={dur2:.3f}")
check("exit быстрее enter (как в MD3)", dur2 < dur * 0.75, f"{dur2:.3f} vs {dur:.3f}")

print("\n=== MD3 Switch: track 52×32, handle 16/24/28 ===")
sw = gui.Md3Switch(app, FakeWidget(), "Switch", value=False)
sw.redraw()
items = list(sw.canvas.items)
track = [i for i in items if i[0] == "oval"]
check("track рисуется овалом", len(track) >= 1)
if track:
    x1, y1, x2, y2 = track[0][1]
    check(f"track 52×32 dp (получено {x2-x1:.0f}×{y2-y1:.0f})",
          abs((x2 - x1) - 52) < 1 and abs((y2 - y1) - 32) < 1)
    check("track = surface-container-highest (unselected)",
          track[0][2].get("fill") == app.theme.role("surfaceContainerHighest"),
          str(track[0][2].get("fill")))
handle = [i for i in items if i[0] == "oval"][1:]
if handle:
    hx1, hy1, hx2, hy2 = handle[-1][1]
    check(f"handle unselected = 16dp (получено {hx2-hx1:.0f})", abs((hx2 - hx1) - 16) < 1)
sw.set(True, animate=False)
items = list(sw.canvas.items)
ov = [i for i in items if i[0] == "oval"]
hx1, hy1, hx2, hy2 = ov[-1][1]
check(f"handle selected = 24dp (получено {hx2-hx1:.0f})", abs((hx2 - hx1) - 24) < 1)
check("selected track = primary",
      any(i[2].get("fill") == app.theme.role("primary") for i in ov))
sw.pressed = True
sw.redraw()
ov = [i for i in sw.canvas.items if i[0] == "oval"]
hx1, hy1, hx2, hy2 = ov[-1][1]
check(f"handle pressed = 28dp (получено {hx2-hx1:.0f})", abs((hx2 - hx1) - 28) < 1)

print("\n=== MD3 Slider ===")
sl = gui.Md3Slider(app, FakeWidget(), "Углы", 0, 32, 12, 2, "dp", lambda v: None)
sl.canvas.opts["width"] = 520
sl.redraw()
lines = [i for i in sl.canvas.items if i[0] == "line"]
check("трек из 2 частей (active/inactive)", len(lines) == 2, str(len(lines)))
check("active = primary", any(i[2].get("fill") == app.theme.role("primary") for i in lines))
check("inactive = surface-container-highest",
      any(i[2].get("fill") == app.theme.role("surfaceContainerHighest") for i in lines))
ov = [i for i in sl.canvas.items if i[0] == "oval"]
check("handle 20dp", ov and abs((ov[0][1][2] - ov[0][1][0]) - 20) < 1,
      str(ov[0][1] if ov else None))
x_at_12 = sl._x_for(12)
check("позиция handle соответствует значению 12/32",
      abs((x_at_12 - 20) / (520 - 40) - 12 / 32) < 0.02, f"x={x_at_12}")
sl._set(20, animate=False)
check("значение меняется + callback", sl.value == 20 and "20dp" in sl.readout.opts.get("text", ""))

print("\n=== Segmented button ===")
seg = gui.Md3Segmented(app, FakeWidget(), ["dark", "light"], "dark", lambda v: None, width=260)
seg.redraw()
polys = [i for i in seg.canvas.items if i[0] == "poly"]
check("выбранный сегмент = secondary-container",
      any(p[2].get("fill") == app.theme.role("secondaryContainer") for p in polys))
texts = [i for i in seg.canvas.items if i[0] == "text"]
check("метка выбранного сегмента с галочкой",
      any(str(t[2].get("text", "")).startswith("✓") for t in texts), str([t[2].get("text") for t in texts]))
seg._click(types.SimpleNamespace(x=200, y=20))
check("клик переключает значение", seg.value == "light", seg.value)

print("\n=== Превью рабочего стола и палитры ===")
CALLS.clear()
prev = gui.DesktopPreview(app, FakeWidget())
prev.redraw()
items = list(prev.canvas.items)
check("превью рисуется (>30 примитивов)", len(items) > 30, str(len(items)))
check("в превью есть primary (рамка активного окна)",
      any(i[2].get("fill") == app.theme.role("primary") for i in items if i[0] == "poly"))
check("в превью есть elevation-2 панель",
      any(i[2].get("fill") == app.theme.elevation[2] for i in items if i[0] == "poly"))
check("в превью есть elevation-3 диалог",
      any(i[2].get("fill") == app.theme.elevation[3] for i in items if i[0] == "poly"))

strip = gui.TonalStrip(app, FakeWidget())
strip.redraw()
rects = [i for i in strip.canvas.items if i[0] == "rect"]
check(f"тональная палитра: {len(gui.TonalStrip.TONES)}×{len(gui.TonalStrip.ROWS)} ячеек",
      len(rects) == len(gui.TonalStrip.TONES) * len(gui.TonalStrip.ROWS), str(len(rects)))
check("первая ячейка = primary tone 0 (#000000-ish)",
      rects[0][2].get("fill") == app.theme.palettes["primary"]["0"], rects[0][2].get("fill"))

cc = gui.ContrastCard(app, FakeWidget())
cc.redraw()
check("отчёт о контрасте рисуется", len(cc.canvas.items) > 10)

print("\n=== Кнопки MD3 ===")
for kind, want_role in (("filled", "primary"), ("tonal", "secondaryContainer"),
                        ("outlined", "surface"), ("text", "surface")):
    CALLS.clear()
    b = gui.Md3Button(app, FakeWidget(), "OK", lambda: None, kind=kind)
    b.redraw()
    polys = [i for i in b.w.items if i[0] == "poly"]
    fills = {p[2].get("fill") for p in polys}
    if kind in ("filled", "tonal"):
        check(f"{kind}: контейнер = {want_role}", app.theme.role(want_role) in fills, str(fills))
    elif kind == "outlined":
        check(f"{kind}: рисуется без падения", len(polys) >= 1)
    else:  # text
        texts_ = [i for i in b.w.items if i[0] == "text"]
        check("text: подпись = primary",
              texts_ and texts_[0][2].get("fill") == app.theme.role("primary"),
              str([t[2].get("fill") for t in texts_]))
        b.w.fire("<Enter>")
        hovered = [i for i in b.w.items if i[0] == "poly"]
        check("text: state layer появляется только при hover",
              any(pp[2].get("fill") == gui.mix_alpha(app.theme.role("primary"), app.card_bg, 0.08)
                  for pp in hovered), str([pp[2].get("fill") for pp in hovered]))
        b.w.fire("<Leave>")
    b.w.fire("<Button-1>")
    b.w.fire("<ButtonRelease-1>")

print("\n=== Смена темы перерисовывает всё ===")
app.cfg.set("dark", False)
app.cfg.set("seed", "#006A6A")
app.theme = Theme(app.cfg)
app.bg = app.theme.role("surfaceContainer")
app.card_bg = app.theme.elevation[1]
app.fg = app.theme.role("onSurface")
app.fg_muted = app.theme.role("onSurfaceVariant")
for w in gui.THEMABLES:
    w.retheme(app.theme)
check("после смены темы чекбокс знает новый primary",
      cb2.theme.role("primary") == app.theme.role("primary"))
check("light-схема: surface светлее", relative_luminance(app.theme.role("surface")) > 0.5)

print(f"\n{'='*60}\nИТОГ: {PASS} проверок пройдено, {FAIL} провалено\n{'='*60}")
sys.exit(1 if FAIL else 0)
