#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md3_theme.py — движок темы Material Design 3 для bspwm/picom/polybar.

ЕДИНСТВЕННЫЙ источник правды о цветах. Ничего «от балды»:

  * роли (md.sys.color.*) берутся из датасета `md3_palettes.json.gz`, который
    сгенерирован ОФИЦИАЛЬНОЙ библиотекой Material Color Utilities
    (@material/material-color-utilities, см. tools/md3-dump.mjs):
    SchemeTonalSpot/SchemeContent/SchemeMonochrome + MaterialDynamicColors;
  * тональные палитры (md.ref.palette.*) — оттуда же, поэтому терминальная
    палитра и тени elevation тонированы тем же source color, что и WM;
  * тени считаются по spec'у M3 Elevation: overlay surfaceTint с opacity
    5/8/11/12/14 % для level 1..5, цвет тени = md.sys.color.shadow.

Использование:
    md3_theme.py show                       # текущее состояние
    md3_theme.py set --dark true --seed '#006A6A' --corner-radius 16
    md3_theme.py generate                   # theme.json -> theme.conf (+ json)
    md3_theme.py export shell|json          # дамп ролей в stdout
    md3_theme.py list-seeds | list-schemes

Как библиотека:  from md3_theme import Config, Theme; Theme(Config.load()).roles
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Пути
# --------------------------------------------------------------------------- #

TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent                       # .../bspwm-material3
PALETTES_GZ = TOOLS_DIR / "md3_palettes.json.gz"

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
XDG_STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")

STATE_DIR = ROOT_DIR / "generated"
STATE_FILE = STATE_DIR / "theme-state.json"
THEME_JSON = STATE_DIR / "theme.json"
THEME_CONF = STATE_DIR / "theme.conf"

DEFAULT_SEED = "#6750A4"        # md.ref.palette baseline (M3 purple)
DEFAULT_SCHEME = "tonal-spot"   # дефолтная схема Material Theme Builder
DEFAULT_CONTRAST = "standard"   # standard | medium | high

# --------------------------------------------------------------------------- #
# Справочники токенов M3
# --------------------------------------------------------------------------- #

# md.sys.shape — шкала углов (https://m3.material.io/styles/shape/corner-radius-scale)
SHAPE_SCALE = {
    "none": 0,
    "extra-small": 4,
    "small": 8,
    "medium": 12,          # <- дефолт этого конфига (corner-radius: 12px)
    "large": 16,
    "large-increased": 20,
    "extra-large": 28,
    "extra-large-increased": 32,
    "extra-extra-large": 48,
    "full": 9999,
}
SHAPE_NAMES = {v: k for k, v in SHAPE_SCALE.items()}

# md.sys.elevation — уровни и opacity тонирующего overlay (surfaceTint)
ELEVATION = {
    0: 0.00,
    1: 0.05,
    2: 0.08,
    3: 0.11,
    4: 0.12,
    5: 0.14,
}

# md.sys.state — opacity state layer'ов
STATE_LAYER = {"drag": 0.16, "focus": 0.12, "hover": 0.08, "press": 0.12}

# md.sys.motion.duration (https://m3.material.io/styles/motion/easing-and-duration/tokens-specs)
DURATION = {
    "short1": 50, "short2": 100, "short3": 150, "short4": 200,
    "medium1": 250, "medium2": 300, "medium3": 350, "medium4": 400,
    "long1": 450, "long2": 500, "long3": 550, "long4": 600,
    "extra-long1": 700, "extra-long2": 800, "extra-long3": 900, "extra-long4": 1000,
}

# md.sys.motion.easing — CSS cubic-bezier'ы из той же страницы
EASING = {
    "emphasized": (0.2, 0.0, 0.0, 1.0),              # standard как fallback для CSS
    "emphasized-decelerate": (0.05, 0.7, 0.1, 1.0),
    "emphasized-accelerate": (0.3, 0.0, 0.8, 0.15),
    "standard": (0.2, 0.0, 0.0, 1.0),
    "standard-decelerate": (0.0, 0.0, 0.0, 1.0),
    "standard-accelerate": (0.3, 0.0, 1.0, 1.0),
}

# md.comp.checkbox — метрики компонента (tokens v0_192 + material-web checkbox)
CHECKBOX = {
    "container-size": 18,
    "container-shape": 2,          # md.sys.shape.corner-extra-small = 2px
    "outline-width": 2,
    "icon-size": 18,
    "state-layer-size": 40,
    "state-layer-shape": "full",
    "enter-duration": 350,         # md.sys.motion.duration.medium3
    "exit-duration": 150,          # md.sys.motion.duration.short3
    "icon-opacity-duration": 50,   # md.sys.motion.duration.short1 (linear)
    "scale-from": 0.6,
    "touch-target": 48,
}

# md.comp.switch — метрики (tokens v0_192)
SWITCH = {
    "track-width": 52, "track-height": 32, "track-outline-width": 2,
    "handle-unselected": 16, "handle-selected": 24, "handle-pressed": 28,
    "icon-size": 16, "state-layer-size": 40,
}

# Пары «фон / контент» для проверки контраста (M3 требует >= 3:1 для пар ролей,
# 4.5:1 — для body-текста)
CONTRAST_PAIRS = [
    ("onSurface", "surface"),
    ("onSurfaceVariant", "surfaceContainer"),
    ("onPrimary", "primary"),
    ("onPrimaryContainer", "primaryContainer"),
    ("onSecondaryContainer", "secondaryContainer"),
    ("onTertiaryContainer", "tertiaryContainer"),
    ("onError", "error"),
    ("onErrorContainer", "errorContainer"),
]

# 16 цветов терминала -> тона M3-палитр (ANSI-порядок)
TERMINAL_MAP: List[Tuple[str, str, int]] = [
    ("color0",  "neutral", 0), ("color8",  "neutral", 30),
    ("color1",  "error", 50), ("color9",  "error", 80),
    ("color2",  "tertiary", 40), ("color10", "tertiary", 80),
    ("color3",  "secondary", 50), ("color11", "secondary", 80),
    ("color4",  "primary", 60), ("color12", "primary", 80),
    ("color5",  "tertiary", 60), ("color13", "tertiary", 80),
    ("color6",  "secondary", 60), ("color14", "secondary", 90),
    ("color7",  "neutral", 90), ("color15", "neutral", 100),
]

# --------------------------------------------------------------------------- #
# Утилиты цвета
# --------------------------------------------------------------------------- #


def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        *[max(0, min(255, int(round(c)))) for c in rgb]
    )


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hexc: str) -> float:
    r, g, b = hex_to_rgb(hexc)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio (1..21)."""
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def blend_over(fg: str, bg: str, alpha: float) -> str:
    """Наложение fg c alpha поверх bg (sRGB). Используется для elevation overlay."""
    f, b = hex_to_rgb(fg), hex_to_rgb(bg)
    return rgb_to_hex(tuple(alpha * fc + (1 - alpha) * bc for fc, bc in zip(f, b)))


def with_alpha(hexc: str, alpha: float) -> str:
    """#RRGGBBAA (формат, который понимает picom для shadow-color)."""
    r, g, b = hex_to_rgb(hexc)
    return "#{:02x}{:02x}{:02x}{:02x}".format(r, g, b, int(round(alpha * 255)))


def polybar_color(hexc: str, alpha: float = 1.0) -> str:
    """polybar хочет #AARRGGBB."""
    r, g, b = hex_to_rgb(hexc)
    return "#{:02x}{:02x}{:02x}{:02x}".format(int(round(alpha * 255)), r, g, b)


def is_dark(hexc: str) -> bool:
    return relative_luminance(hexc) < 0.2


def snake(role: str) -> str:
    """onPrimaryContainer -> ON_PRIMARY_CONTAINER, container-size -> CONTAINER_SIZE"""
    out: List[str] = []
    for i, ch in enumerate(role):
        if ch in "-. ":                       # md-токены могут содержать дефисы
            out.append("_")
            continue
        if ch.isupper() and i and not role[i - 1].isupper() and role[i - 1] not in "-. ":
            out.append("_")
        out.append(ch.upper())
    return "".join(out)


def cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float) -> str:
    """cubic-bezier(...) ровно в том виде, в каком его печатает m3.material.io."""
    def fmt(v: float) -> str:
        s = f"{v:.3f}".rstrip("0")
        if s.endswith("."):
            s += "0"
        return s
    return "cubic-bezier({}, {}, {}, {})".format(*(fmt(v) for v in (p1x, p1y, p2x, p2y)))


# --------------------------------------------------------------------------- #
# Конфигурация (то, чем управляет GUI)
# --------------------------------------------------------------------------- #

DEFAULTS: Dict[str, Any] = {
    # --- цвет (md.sys.color) ---
    "seed": DEFAULT_SEED,
    "scheme": DEFAULT_SCHEME,          # tonal-spot | content | monochrome
    "contrast": DEFAULT_CONTRAST,      # standard | medium | high
    "dark": True,

    # --- форма (md.sys.shape) ---
    "corner_radius": 12,               # medium = 12dp
    "round_dialogs": True,

    # --- elevation / тени ---
    "shadows": True,
    "shadow_elevation": 2,             # 1..5
    "tinted_shadows": True,            # тень от md.sys.color.shadow, не чистый чёрный

    # --- прозрачность ---
    "inactive_dim": True,
    "inactive_opacity": 0.94,
    "active_opacity": 1.0,
    "frame_opacity": 1.0,
    "blur": True,
    "blur_strength": 14,

    # --- motion (md.sys.motion) ---
    "animations": True,                # picom animations (требуется picom с поддержкой)
    "animation_scale": 0.96,
    "fade": True,

    # --- bspwm ---
    "gap": 12,
    "padding": 16,
    "border_width": 2,
    "focus_style": "primary",          # primary | primary-container | tertiary
    "single_desktop_mode": False,

    # --- окружение ---
    "bar": True,
    "tray": True,
    "terminal_colors": True,           # писать MD3-палитру терминала в Xresources
    "auto_apply": True,
    "backend": "egl",                  # egl | glx
    "launcher": "rofi",                # rofi | wofi | fuzzel | bemenu
    "terminal": "",                    # пусто = автоопределение
}

TERMINALS = [
    "alacritty", "kitty", "wezterm", "foot", "xterm", "urxvt", "st",
    "gnome-terminal", "konsole", "xfce4-terminal", "tilix", "terminator",
]


@dataclass
class Config:
    values: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))

    # -- доступ как к атрибутам --
    def __getattr__(self, name: str) -> Any:
        vals = object.__getattribute__(self, "__dict__").get("values", {})
        if name in vals:
            return vals[name]
        raise AttributeError(name)

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def set(self, name: str, value: Any) -> None:
        if name not in DEFAULTS:
            raise KeyError(f"unknown option: {name}")
        if isinstance(DEFAULTS[name], bool) and not isinstance(value, bool):
            value = str(value).strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(DEFAULTS[name], int) and not isinstance(value, bool):
            value = int(value)
        elif isinstance(DEFAULTS[name], float):
            value = float(value)
        self.values[name] = value

    # -- (де)сериализация --
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = Path(path or STATE_FILE)
        cfg = cls()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in (data.get("values") or data).items():
                    if k in DEFAULTS:
                        cfg.set(k, v)
            except Exception as exc:  # повреждённый state — не роняем WM
                print(f"[md3] warning: {path}: {exc}", file=sys.stderr)
        return cfg

    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path or STATE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "values": self.values}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    # -- производные значения --
    @property
    def shape_token(self) -> str:
        return SHAPE_NAMES.get(int(self.values["corner_radius"]), f"custom:{self.values['corner_radius']}dp")

    @property
    def terminal(self) -> str:
        t = str(self.values.get("terminal") or "").strip()
        if t:
            return t
        for cand in TERMINALS:
            if shutil.which(cand):
                return cand
        return os.environ.get("TERMINAL") or "xterm"

    def variant_key(self, dark: Optional[bool] = None) -> str:
        dark = self.values["dark"] if dark is None else dark
        scheme = self.values["scheme"]
        contrast = self.values["contrast"]
        return f"{scheme}|{contrast}|{'dark' if dark else 'light'}"


# --------------------------------------------------------------------------- #
# Датасет палитр
# --------------------------------------------------------------------------- #

_DATA_CACHE: Optional[Dict[str, Any]] = None


def load_palettes() -> Dict[str, Any]:
    """Вшитый датасет, сгенерированный material-color-utilities (см. md3-dump.mjs)."""
    global _DATA_CACHE
    if _DATA_CACHE is not None:
        return _DATA_CACHE
    raw = gzip.decompress(PALETTES_GZ.read_bytes()).decode("utf-8")
    _DATA_CACHE = json.loads(raw)
    return _DATA_CACHE


def available_seeds() -> List[str]:
    return list(load_palettes()["schemes"].keys())


def available_schemes() -> List[str]:
    return sorted({k.split("|")[0] for k in load_palettes()["schemes"][DEFAULT_SEED.upper()]})


def available_contrasts() -> List[str]:
    return sorted({k.split("|")[1] for k in load_palettes()["schemes"][DEFAULT_SEED.upper()]})


def _compute_with_node(seed: str, scheme: str, contrast: float, dark: bool) -> Optional[Dict[str, str]]:
    """
    Произвольный seed-цвет: дёргаем официальный MCU через node, если он есть.
    Возвращает None, если node/библиотека недоступны.
    """
    if not shutil.which("node"):
        return None
    script = r"""
const mcu = require('@material/material-color-utilities');
const [seed, schemeName, contrast, dark] = process.argv.slice(2);
const S = { 'tonal-spot': mcu.SchemeTonalSpot, 'content': mcu.SchemeContent,
            'monochrome': mcu.SchemeMonochrome }[schemeName];
if (!S) { console.error('unknown scheme'); process.exit(2); }
const s = new S(mcu.Hct.fromInt(mcu.argbFromHex(seed)), dark === 'true', parseFloat(contrast));
const M = mcu.MaterialDynamicColors, out = {};
for (const k of Object.getOwnPropertyNames(M))
  if (M[k] && typeof M[k] === 'object' && typeof M[k].getArgb === 'function'
      && !k.endsWith('PaletteKeyColor'))
    out[k] = mcu.hexFromArgb(M[k].getArgb(s));
process.stdout.write(JSON.stringify(out));
"""
    for base in (ROOT_DIR, ROOT_DIR / "tools", Path.cwd()):
        nm = base / "node_modules" / "@material" / "material-color-utilities"
        if nm.exists():
            env = dict(os.environ, NODE_PATH=str(base / "node_modules"))
            try:
                res = subprocess.run(
                    ["node", "-e", script, seed, scheme, str(contrast), "true" if dark else "false"],
                    cwd=str(base), env=env, capture_output=True, text=True, timeout=30,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return json.loads(res.stdout)
            except Exception:
                return None
    return None


CONTRAST_LEVEL = {"standard": 0.0, "medium": 0.5, "high": 1.0}


# --------------------------------------------------------------------------- #
# Тема
# --------------------------------------------------------------------------- #


class Theme:
    """Роли md.sys.color + производные значения (elevation, тени, палитры)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.seed = str(cfg.values["seed"]).strip()
        if not self.seed.startswith("#"):
            self.seed = "#" + self.seed
        self.seed = self.seed.upper()
        self.dark = bool(cfg.values["dark"])
        self.scheme = cfg.values["scheme"]
        self.contrast = cfg.values["contrast"]
        self.source: str = "dataset"

        self.roles: Dict[str, str] = self._resolve_roles()
        self.other: Dict[str, Dict[str, str]] = {
            "dark": self._resolve_roles(dark=True),
            "light": self._resolve_roles(dark=False),
        }
        self.palettes = self._resolve_palettes()
        self._derive()

    # -- роли ------------------------------------------------------------- #
    def _resolve_roles(self, dark: Optional[bool] = None) -> Dict[str, str]:
        dark = self.dark if dark is None else dark
        data = load_palettes()
        key = f"{self.scheme}|{self.contrast}|{'dark' if dark else 'light'}"
        per_seed = data["schemes"].get(self.seed)
        if per_seed and key in per_seed:
            return dict(per_seed[key])
        # произвольный seed — считаем официальным MCU через node
        computed = _compute_with_node(
            self.seed, self.scheme, CONTRAST_LEVEL.get(self.contrast, 0.0), dark
        )
        if computed:
            self.source = "material-color-utilities (node)"
            return computed
        # fallback: ближайший сид по HCT-оттенку
        fallback = self._nearest_seed()
        per_seed = data["schemes"][fallback]
        self.source = f"dataset (nearest seed {fallback})"
        return dict(per_seed.get(key) or next(iter(per_seed.values())))

    def _nearest_seed(self) -> str:
        data = load_palettes()
        target = hex_to_rgb(self.seed)
        best, best_d = DEFAULT_SEED.upper(), 1e9
        for s in data["schemes"]:
            d = sum((a - b) ** 2 for a, b in zip(target, hex_to_rgb(s)))
            if d < best_d:
                best, best_d = s, d
        return best

    def _resolve_palettes(self) -> Dict[str, Dict[str, str]]:
        data = load_palettes()
        pal = data["palettes"].get(self.seed)
        if pal:
            return {k: dict(v) for k, v in pal.items()}
        fb = self._nearest_seed()
        return {k: dict(v) for k, v in data["palettes"][fb].items()}

    # -- производные ------------------------------------------------------ #
    def _derive(self) -> None:
        r = self.roles
        self.surface_tint = r["surfaceTint"]
        self.shadow_color = r["shadow"] if self.cfg.values["tinted_shadows"] else "#000000"

        # Elevation: surface + overlay(surfaceTint, opacity) — spec M3 Elevation
        self.elevation: Dict[int, str] = {
            lvl: blend_over(self.surface_tint, r["surface"], op)
            for lvl, op in ELEVATION.items()
        }

        # Тени для picom: blur/offset по уровню elevation + альфа из уровня
        lvl = max(1, min(5, int(self.cfg.values["shadow_elevation"])))
        self.elevation_level = lvl
        blur = {1: 12, 2: 16, 3: 22, 4: 28, 5: 36}[lvl]
        dy = {1: 2, 2: 4, 3: 6, 4: 8, 5: 12}[lvl]
        alpha = {1: 0.28, 2: 0.32, 3: 0.36, 4: 0.40, 5: 0.46}[lvl]
        if not self.dark:                      # на светлой схеме тени заметнее
            alpha = min(0.55, alpha + 0.08)
        self.shadow = {"blur": blur, "offset_y": dy, "offset_x": 0, "alpha": alpha}

        # Терминал
        self.terminal_colors = {
            name: self.palettes[pal][str(tone)] for name, pal, tone in TERMINAL_MAP
        }

        # Контрастность ключевых пар
        self.contrast_report = [
            {
                "fg": fg, "bg": bg,
                "fg_hex": r.get(fg, "#000000"), "bg_hex": r.get(bg, "#000000"),
                "ratio": round(contrast_ratio(r.get(fg, "#000"), r.get(bg, "#fff")), 2),
            }
            for fg, bg in CONTRAST_PAIRS
        ]

    # -- экспорт ---------------------------------------------------------- #
    def role(self, name: str, default: str = "#000000") -> str:
        return self.roles.get(name, default)

    def all_vars(self) -> Dict[str, str]:
        """Плоский словарь MD3_* -> значение (для theme.conf / окружения)."""
        out: Dict[str, str] = {}
        for role, value in self.roles.items():
            out[f"MD3_{snake(role)}"] = value
        for lvl, value in self.elevation.items():
            out[f"MD3_ELEVATION_LEVEL{lvl}"] = value
        out["MD3_SCHEME"] = self.scheme
        out["MD3_CONTRAST"] = self.contrast
        out["MD3_MODE"] = "dark" if self.dark else "light"
        out["MD3_SOURCE_COLOR"] = self.seed
        out["MD3_SHADOW_COLOR"] = self.shadow_color
        out["MD3_SHADOW_COLOR_ALPHA"] = with_alpha(self.shadow_color, self.shadow["alpha"])
        out["MD3_SHADOW_BLUR"] = str(self.shadow["blur"])
        out["MD3_SHADOW_OFFSET_Y"] = str(self.shadow["offset_y"])
        out["MD3_CORNER_RADIUS"] = str(self.cfg.values["corner_radius"])
        out["MD3_CORNER_RADIUS_TOKEN"] = str(self.cfg.shape_token)
        out["MD3_GAP"] = str(self.cfg.values["gap"])
        out["MD3_PADDING"] = str(self.cfg.values["padding"])
        out["MD3_BORDER_WIDTH"] = str(self.cfg.values["border_width"])
        out["MD3_INACTIVE_OPACITY"] = f"{float(self.cfg.values['inactive_opacity']):.2f}"
        out["MD3_ACTIVE_OPACITY"] = f"{float(self.cfg.values['active_opacity']):.2f}"
        out["MD3_FRAME_OPACITY"] = f"{float(self.cfg.values['frame_opacity']):.2f}"
        out["MD3_BLUR_STRENGTH"] = str(self.cfg.values["blur_strength"])
        out["MD3_ANIMATION_SCALE"] = f"{float(self.cfg.values['animation_scale']):.2f}"
        for tok, ms in DURATION.items():
            out[f"MD3_DURATION_{snake(tok)}"] = str(ms)
        for tok, pts in EASING.items():
            out[f"MD3_EASING_{snake(tok)}"] = cubic_bezier(*pts)
        for tok, val in CHECKBOX.items():
            out[f"MD3_CHECKBOX_{snake(str(tok))}"] = str(val)
        for tok, val in SWITCH.items():
            out[f"MD3_SWITCH_{snake(str(tok))}"] = str(val)
        for tok, val in STATE_LAYER.items():
            out[f"MD3_STATE_LAYER_{snake(tok)}"] = f"{val:.2f}"
        for pal, tones in self.palettes.items():
            for tone, hexv in tones.items():
                out[f"MD3_TONE_{snake(pal).upper()}_{tone}"] = hexv
        for name, hexv in self.terminal_colors.items():
            out[f"MD3_TERM_{name.upper()}"] = hexv
        return out

    def to_json(self) -> Dict[str, Any]:
        return {
            "meta": {
                "generator": "md3_theme.py",
                "rolesSource": load_palettes()["meta"]["generator"],
                "resolvedVia": self.source,
                "spec": "material-web tokens v0_192 / m3.material.io",
            },
            "config": self.cfg.values,
            "seed": self.seed,
            "seedHct": load_palettes().get("seedHct", {}).get(self.seed),
            "scheme": self.scheme,
            "contrast": self.contrast,
            "dark": self.dark,
            "roles": self.roles,
            "rolesOtherMode": self.other,
            "elevation": {str(k): v for k, v in self.elevation.items()},
            "shadow": self.shadow,
            "shape": {
                "cornerRadius": self.cfg.values["corner_radius"],
                "token": self.cfg.shape_token,
                "scale": SHAPE_SCALE,
            },
            "motion": {"duration": DURATION, "easing": {k: list(v) for k, v in EASING.items()}},
            "stateLayer": STATE_LAYER,
            "checkbox": CHECKBOX,
            "switch": SWITCH,
            "palettes": self.palettes,
            "terminal": self.terminal_colors,
            "contrastReport": self.contrast_report,
        }

    def to_shell(self) -> str:
        lines = [
            "#!/usr/bin/env bash",
            "# ---------------------------------------------------------------------------",
            "# СГЕНЕРИРОВАНО АВТОМАТИЧЕСКИ — tools/md3_theme.py",
            "# Не редактировать вручную: правьте generated/theme-state.json",
            "# (или запустите tools/md3-theme-gui.py).",
            "#",
            f"# source color : {self.seed}",
            f"# scheme       : {self.scheme} / contrast {self.contrast} / "
            f"{'dark' if self.dark else 'light'}",
            f"# роли         : md.sys.color.* ({load_palettes()['meta']['generator']})",
            "# ---------------------------------------------------------------------------",
            "",
        ]
        vars_ = self.all_vars()
        group = ""
        for key in sorted(vars_):
            g = key.split("_")[1]
            if g != group:
                group = g
                lines.append("")
                lines.append(f"# --- {group} ---")
            lines.append(f"{key}='{vars_[key]}'")
        lines.append("")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Рендер конфигов из шаблонов
# --------------------------------------------------------------------------- #

TEMPLATES = ROOT_DIR / "tools" / "templates"


def _apply_conditionals(text: str, flags: Dict[str, bool]) -> str:
    """
    Раскрывает блоки вида:

        #?if SHADOWS
        ...строки...
        #?endif

    Блок попадает в вывод только если соответствующий флаг включён.
    Это нужно, чтобы сгенерированный конфиг был ВАЛИДЕН для своей программы
    (например, picom без поддержки `animations` не должен видеть этот синтаксис).
    """
    import re

    pattern = re.compile(r"^[ \t]*#\?if +([A-Z0-9_]+)[ \t]*\n(.*?)^[ \t]*#\?endif[ \t]*\n",
                         re.MULTILINE | re.DOTALL)

    def repl(m: "re.Match[str]") -> str:
        return m.group(2) if flags.get(m.group(1), False) else ""

    prev = None
    while prev != text:          # поддержка вложенных блоков
        prev = text
        text = pattern.sub(repl, text)
    return text


def render_template(name: str, theme: Theme, cfg: Config) -> str:
    import re

    text = (TEMPLATES / name).read_text(encoding="utf-8")
    mapping = dict(theme.all_vars())
    # булевы флаги -> "true"/"false" (для picom/libconfig) и 1/0
    flags = [
        "shadows", "round_dialogs", "tinted_shadows", "inactive_dim", "blur",
        "animations", "fade", "bar", "tray", "terminal_colors", "auto_apply",
        "dark", "single_desktop_mode",
    ]
    for f in flags:
        v = bool(cfg.values[f])
        mapping[f"FLAG_{f.upper()}"] = "true" if v else "false"
        mapping[f"NUM_{f.upper()}"] = "1" if v else "0"
    flag_map = {f.upper(): bool(cfg.values[f]) for f in flags}
    # флаг для скругления диалогов зависит и от общего corner-radius
    flag_map["ROUND_DIALOGS"] = flag_map["ROUND_DIALOGS"] and int(cfg.values["corner_radius"]) > 0
    flag_map["EGL"] = str(cfg.values["backend"]).lower() == "egl"
    flag_map["GLX"] = str(cfg.values["backend"]).lower() == "glx"
    flag_map["TRAY"] = bool(cfg.values["tray"]) and bool(cfg.values["bar"])
    # инверсии — для блоков «когда выключено»
    for name in list(flag_map):
        flag_map[f"NO_{name}"] = not flag_map[name]

    # --- метрики, которые нужны шаблонам, но не входят в all_vars() ---
    mapping["MD3_SHADOW_ALPHA"] = f"{theme.shadow['alpha']:.2f}"
    mapping["MD3_SHADOW_RADIUS"] = str(max(1, theme.shadow["blur"] // 2))
    mapping["MD3_SHADOW_OFFSET_X"] = str(theme.shadow["offset_x"])
    mapping["MD3_ELEVATION_LEVEL"] = str(theme.elevation_level)
    mapping["MD3_ELEVATION_COLOR"] = theme.elevation[max(1, min(5, theme.elevation_level))]
    mapping["TERMINAL"] = cfg.terminal
    mapping["LAUNCHER"] = str(cfg.values["launcher"])
    mapping["FOCUS_STYLE"] = str(cfg.values["focus_style"])
    mapping["BACKEND"] = str(cfg.values["backend"])
    # семантические цвета рамок bspwm
    focus_map = {
        "primary": theme.role("primary"),
        "primary-container": theme.role("primaryContainer"),
        "tertiary": theme.role("tertiary"),
    }
    mapping["BSPWM_FOCUSED"] = focus_map.get(mapping["FOCUS_STYLE"], theme.role("primary"))
    mapping["BSPWM_FOCUSED_OCCUPIED"] = theme.role("secondary")
    mapping["BSPWM_NORMAL"] = theme.role("outlineVariant")
    mapping["BSPWM_ACTIVE"] = theme.role("surfaceContainerHighest")
    mapping["BSPWM_URGENT"] = theme.role("error")
    mapping["BSPWM_PRESPLIT"] = theme.role("tertiary")
    mapping["MD3_ANIMATION_DURATION_S"] = f"{DURATION['medium3'] / 1000:.3f}"
    mapping["MD3_FADE_STEP"] = "0.06"
    # полибар: готовые строки #AARRGGBB
    for role, hexv in theme.roles.items():
        mapping[f"PB_{snake(role)}"] = polybar_color(hexv)
    for lvl, hexv in theme.elevation.items():
        mapping[f"PB_ELEVATION_LEVEL{lvl}"] = polybar_color(hexv)
    mapping["PB_SHADOW"] = polybar_color(theme.shadow_color, theme.shadow["alpha"])
    mapping["PB_TRANSPARENT"] = "#00000000"

    # rofi: #RRGGBBAA + state layer'ы (md.sys.state)
    for role, hexv in theme.roles.items():
        mapping[f"ROFI_{snake(role)}"] = with_alpha(hexv, 1.0)
    state_fg = theme.role("onSurface")
    mapping["ROFI_HOVER_LAYER"] = with_alpha(state_fg, STATE_LAYER["hover"])
    mapping["ROFI_PRESS_LAYER"] = with_alpha(state_fg, STATE_LAYER["press"])

    # шаблоны rofi/Xresources тоже входят в рендер

    # шаблоны используют {{TOKEN}}, чтобы не конфликтовать с ${...} в shell
    def sub(m):
        return mapping.get(m.group(1), m.group(0))

    text = re.sub(r"\{\{([A-Z0-9_]+)\}\}", sub, text)
    return _apply_conditionals(text, flag_map)


def write_outputs(theme: Theme, cfg: Config, targets: Optional[Dict[str, Path]] = None) -> Dict[str, Path]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    targets = targets or {
        "theme.conf": THEME_CONF,
        "theme.json": THEME_JSON,
    }
    written: Dict[str, Path] = {}

    # 1) theme.conf / theme.json
    THEME_CONF.write_text(theme.to_shell(), encoding="utf-8")
    THEME_CONF.chmod(0o644)
    THEME_JSON.write_text(json.dumps(theme.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written["theme.conf"] = THEME_CONF
    written["theme.json"] = THEME_JSON

    # 2) конфиги из шаблонов
    tpl_map = {
        "picom.conf.template": ROOT_DIR / "picom.conf",
        "polybar-colors.ini.template": ROOT_DIR / "polybar" / "colors.ini",
        "polybar-config.ini.template": ROOT_DIR / "polybar" / "config.ini",
        "Xresources.template": ROOT_DIR / "generated" / "Xresources.md3",
        "rofi-md3.rasi.template": ROOT_DIR / "rofi" / "md3.rasi",
    }
    for tpl, dest in tpl_map.items():
        if not (TEMPLATES / tpl).exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render_template(tpl, theme, cfg), encoding="utf-8")
        written[tpl.replace(".template", "")] = dest

    # 3) права на bspwmrc
    rc = ROOT_DIR / "bspwmrc"
    if rc.exists():
        rc.chmod(0o755)
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="md3_theme.py", description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("show", help="текущая тема и состояние")
    sub.add_parser("generate", help="пересобрать theme.conf/theme.json/конфиги")
    sub.add_parser("list-seeds")
    sub.add_parser("list-schemes")

    p = sub.add_parser("set", help="изменить опции и пересобрать тему")
    p.add_argument("pairs", nargs="*", help="key=value ...")
    for flag in ("--dark", "--light"):
        p.add_argument(flag, dest="mode", action="store_const", const=(flag == "--dark"))
    p.add_argument("--seed")
    p.add_argument("--scheme", choices=["tonal-spot", "content", "monochrome"])
    p.add_argument("--contrast", choices=["standard", "medium", "high"])
    p.add_argument("--corner-radius", type=int)
    p.add_argument("--gap", type=int)
    p.add_argument("--no-apply", action="store_true")

    e = sub.add_parser("export", help="дамп ролей")
    e.add_argument("fmt", nargs="?", default="shell", choices=["shell", "json", "roles"])

    args = ap.parse_args(argv)
    cfg = Config.load()

    if args.cmd in (None, "show"):
        theme = Theme(cfg)
        print(f"seed        : {theme.seed}  (HCT "
              f"{json.dumps(load_palettes().get('seedHct', {}).get(theme.seed))})")
        print(f"scheme      : {theme.scheme} / {theme.contrast} / {'dark' if theme.dark else 'light'}")
        print(f"resolved via: {theme.source}")
        print(f"shape       : corner-radius {cfg.values['corner_radius']}dp "
              f"(md.sys.shape.{cfg.shape_token.replace('-', '_')})")
        print(f"elevation   : level {theme.elevation_level}, shadow "
              f"{theme.shadow_color} @ {theme.shadow['alpha']:.2f}, "
              f"blur {theme.shadow['blur']}px")
        print("\nroles:")
        for role in ("primary", "onPrimary", "primaryContainer", "onPrimaryContainer",
                     "secondaryContainer", "tertiary", "error", "surface",
                     "surfaceContainer", "surfaceContainerHigh", "onSurface",
                     "onSurfaceVariant", "outline", "outlineVariant"):
            print(f"  {role:24} {theme.role(role)}")
        print("\ncontrast (WCAG):")
        for row in theme.contrast_report:
            mark = "ok " if row["ratio"] >= 4.5 else ("~  " if row["ratio"] >= 3 else "LOW")
            print(f"  [{mark}] {row['fg']:22} on {row['bg']:22} {row['ratio']:5.2f}:1")
        return 0

    if args.cmd == "list-seeds":
        for s in available_seeds():
            h = load_palettes().get("seedHct", {}).get(s, {})
            print(f"{s}  H={h.get('hue')}  C={h.get('chroma')}  T={h.get('tone')}")
        return 0

    if args.cmd == "list-schemes":
        print("schemes  :", " ".join(available_schemes()))
        print("contrasts:", " ".join(available_contrasts()))
        return 0

    if args.cmd == "set":
        if args.mode is not None:
            cfg.set("dark", args.mode)
        for key, val in (("seed", args.seed), ("scheme", args.scheme),
                         ("contrast", args.contrast)):
            if val:
                cfg.set(key, val)
        if args.corner_radius is not None:
            cfg.set("corner_radius", args.corner_radius)
        if args.gap is not None:
            cfg.set("gap", args.gap)
        for pair in args.pairs:
            if "=" not in pair:
                print(f"[md3] skip '{pair}' (нужно key=value)", file=sys.stderr)
                continue
            k, v = pair.split("=", 1)
            try:
                cfg.set(k.strip(), v.strip())
            except KeyError as exc:
                print(f"[md3] {exc}", file=sys.stderr)
        cfg.save()
        theme = Theme(cfg)
        written = write_outputs(theme, cfg)
        print(f"[md3] saved {cfg.save()}")
        for name, path in written.items():
            print(f"[md3] wrote {name:16} -> {path}")
        if cfg.values["auto_apply"] and not args.no_apply:
            apply_script = TOOLS_DIR / "md3-apply"
            if apply_script.exists():
                subprocess.run(["bash", str(apply_script)], check=False)
        return 0

    if args.cmd in ("generate", "export"):
        theme = Theme(cfg)
        if args.cmd == "generate":
            for name, path in write_outputs(theme, cfg).items():
                print(f"[md3] wrote {name:16} -> {path}")
            return 0
        if args.fmt == "json":
            json.dump(theme.to_json(), sys.stdout, indent=2, ensure_ascii=False)
            print()
        elif args.fmt == "roles":
            for k, v in theme.roles.items():
                print(f"{k}={v}")
        else:
            sys.stdout.write(theme.to_shell())
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
