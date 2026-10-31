# bspwm-material3

bspwm + picom + polybar + rofi, оформленные по **Material Design 3 (Material You)**.
Цвет не «подбирался»: вся палитра вычисляется из одного **source color** библиотекой
**Material Color Utilities (MCU)** — теми же алгоритмами, что генерируют тему Android.
Единственный источник истины о цвете — `generated/theme.conf`; всё остальное
(picom, polybar, rofi, Xresources, рамки bspwm) — производные от него.

```
 source color (#6750A4)
        │  Material Color Utilities (HCT → tonal palettes → scheme)
        ▼
 generated/theme-state.json   ← что выбрано в GUI / CLI (seed, dark, contrast…)
        │  tools/md3_theme.py
        ▼
 generated/theme.conf         ← 740 shell-переменных MD3_* (роли + палитры)
        │  source
        ▼
 bspwmrc                      ← bspc config: рамки,-gap’ы, правила
        │  bin/md3-apply
        ▼
 picom.conf · polybar/* · rofi/md3.rasi · Xresources · wallpapers/*
```

---

## Быстрый старт

```bash
./install.sh                      # → ~/.config/bspwm-material3 + симлинки bspwm/sxhkd
echo 'exec bspwm' >> ~/.xinitrc   # если ещё нет
startx
```

Опции установщика: `--prefix DIR`, `--no-link` (не трогать `~/.config/bspwm`).
Установщик делает бэкап предыдущей установки (`*.bak-<timestamp>`).

**Зависимости.** Обязательные: `bspwm`, `sxhkd`, `python3` (≥3.8, без сторонних
модулей). Рекомендуемые: `picom` (≥11 — анимации), `polybar`, `rofi`, `feh`,
`dunst`/`mako`, `python3-tk` (GUI), `JetBrainsMono Nerd Font`. Без любого из
рекомендуемых конфиг деградирует мягко: каждый запуск обёрнут в `have …`.

---

## Горячие клавиши (sxhkd/sxhkdrc, 73 биндинга)

| Клавиши | Действие | | Клавиши | Действие |
|---|---|---|---|---|
| `super+Return` | терминал | | `super+d` | лаунчер (rofi → fuzzel → …) |
| `super+x` | MD3-меню (тема/сервисы/питание) | | `super+shift+t` | **GUI-редактор темы** |
| `super+grave` | scratch-терминал | | `super+e/w/c` | файлы / браузер / редактор |
| `super+h/j/k/l` | фокус | | `super+shift+h/j/k/l` | переместить |
| `super+alt+h/j/k/l` | преселектор | | `super+ctrl+стрелки` | resize |
| `super+t/y/s/f` | tiled/pseudo/floating/fullscreen | | `super+g/i/l/m` | флаги on/off |
| `super+1..9,0` | рабочие столы | | `super+shift+1..9,0` | отправить окно |
| `super+plus/minus` | gap ± | | `super+F5` | применить тему (USR1) |
| `super+shift+F5` | рестарт WM | | `super+shift+r` | перезагрузить конфиг |
| `XF86Audio*`, `XF86Mon*` | громкость/яркость | | `Print` | скриншот |
| `super+button1/2/3` | переместить / resize / фокус мышью | | | |

Полный список — в `sxhkd/sxhkdrc` (с комментариями).

---

## Тема: три способа править

### 1. GUI (`tools/md3-theme-gui.py`, Tk)

Окно из MD3-компонентов собственной сборки (canvas-виджеты, не ttk-темы):
**чекбоксы** (18 dp контейнер, 2 dp outline, state-layer 40 dp, иконка scale
0.6→1 за 350 мс emphasized-decelerate / выход 150 мс emphasized-accelerate —
по спеке material-web `md.comp.checkbox`), **свитчи** (track 52×32, handle
16→24→28), **слайдеры**, **кнопки** filled/tonal/outlined/text, **сегментные
кнопки** (scheme/contrast), живое **превью рабочего стола** (bar, окна, рамки
bspwm, dock) и **тональная шкала** HCT 0…100.

Всё анимируется кривыми из спеки MD3 Motion: `emphasized-decelerate
(0.05,0.7,0.1,1)`, `emphasized-accelerate (0.3,0,0.8,0.15)`, `standard
(0.2,0,0,1)` — солвер кубических кривых написан вручную (Ньютон + бисекция,
точность ≤ 5.5e-6).

Кнопки низа: **Apply** (tonal) — перегенерировать всё без рестарта;
**Save & restart** (filled) — сохранить state и `md3-apply --restart`.

Скриншоты: `screenshot.png` (рабочий стол) и `docs/gui-screenshot.png` (окно редактора).
Названия карточек — простые («Стили», «Форма и тени», «Анимации»…); все md.sys-детали
остались в коде и `docs/TOKENS.md`, интерфейс ими не перегружен.

Без Tk работает CLI-режим того же файла:
`md3-theme-gui.py --cli --list | --set key=value … | --apply | --print`.

### 2. Меню в сессии (`bin/md3-menu`)

`super+x` → раздел «Тема»: dark/light, contrast (standard/medium/high),
scheme (tonal-spot/content/monochrome/…), seed из пресетов, corner radius,
тени, blur, анимации — каждый пункт сразу вызывает `md3_theme.py set` +
`md3-apply --restart`. Работает через rofi → dmenu → zenity → нумерованный
терминал (что найдётся).

### 3. CLI

```bash
python3 tools/md3_theme.py set --seed '#006A6A' --dark --contrast high
python3 tools/md3_theme.py set corner_radius=16 shadow_elevation=3
bin/md3-apply                # generate → env(xrdb+обои) → wm(bspc) → services
bin/md3-reload theme         # SIGUSR1 bspwmrc: перечитать тему без рестарта
```

`md3-apply` стадийный: `--stage=generate|env|wm|services|all`; WM-стадия
трогает только `bspc config …` (без `bspc wm -r`, чтобы не мигать окнами).

---

## Как устроены файлы

```
bspwmrc                 MD3-токены → bspc config; трапы TERM/HUP/USR1/USR2;
                        супервизия picom/polybar/sxhkd (pid-файлы, релаунч)
sxhkd/sxhkdrc           73 биндинга; USR1 для reload темы, -s socket для USR1 sxhkd
picom.conf              corner-radius из темы, тени по elevation, blur, анимации
                        (v12 WINDOW RULES: правила матчат классы, fullscreen/redir)
polybar/config.ini      bar: workspace’ы, часы, MD3-индикаторы; colors из colors.ini
polybar/colors.ini      #AARRGGBB из ролей темы
rofi/md3.rasi           #RRGGBBAA из ролей темы, radius 12/16/28 по MD3 shape scale
bin/md3-apply           генерация + применение (xrdb, обои, bspc, сервисы)
bin/md3-reload          theme|config|wm|picom|polybar|sxhkd|all (по pid-файлам)
bin/md3-launcher        rofi → fuzzel → bemenu → wofi → dmenu (+zenity fallback)
bin/md3-menu            MD3-меню: тема / сервисы / питание
bin/md3-media           громкость/яркость/плеер/скриншот (wpctl→pactl→amixer…)
bin/autostart           polkit, dunst/mako, keyring, numlock, локер простоя
tools/md3_theme.py      движок темы: MCU-палитры → роли → шаблоны → конфиги
tools/md3-theme-gui.py  GUI/CLI-редактор (MD3-виджеты на canvas)
tools/md3-wall.py       обои SVG+PNG из тональных палитр (PNG — чистый Python)
tools/md3-dump.mjs      дамп палитр MCU → md3_palettes.json.gz (Node, MCU 0.3.0)
tools/templates/        шаблоны picom/polybar/rofi/Xresources/theme.conf
wallpapers/             md3-{dark,light}.{svg,png} текущей темы
docs/TOKENS.md          справочник ролей и их привязки к конфигам
```

**Состояние** живёт в `generated/theme-state.json`; **pid-файлы и логи** —
в `~/.local/state/bspwm-md3/{pid,log}`. Ничего не пишется в `/etc`.

**Сигналы bspwmrc:** `TERM/INT/QUIT` — мягко остановить сервисы и выйти;
`HUP` — exec самого себя (перечитать конфиг); `USR1` — перечитать тему;
`USR2` — включить супервизию сервисов.

---

## Обои

`tools/md3-wall.py` рисует обои из тональных палитр текущей темы (формы —
organic blobs из primary/secondary/tertiary container + elevation, внизу —
шкала тонов `md.ref.palette.primary`). SVG генерируется всегда; PNG — внешним
конвертером, если он есть (rsvg-convert/inkscape/convert/magick/cairosvg),
а если нет — собственным растеризатором на чистом Python (scanline + zlib,
без зависимостей). `md3-apply --stage=env` ставит их через feh/nitrogen/xwallpaper.

```bash
python3 tools/md3-wall.py --size 3840x2160 --png
```

---

## Тесты

```bash
python3 tools/tests/test_widgets_headless.py   # 48 проверок MD3-виджетов без X11
bash -n bspwmrc bin/*                          # синтаксис shell-части
python3 -m py_compile tools/*.py               # синтаксис Python-части
```

Headless-харнес подменяет tkinter фейковым модулем: канвас записывает
`create_*`, `after` складывает колбэки в очередь, `.step(n)` прокручивает
кадры анимаций — так проверяются геометрия чекбоксов, тайминги кривых,
state-layers и цвета превью без дисплея.

---

## Зачем читать спеку, а не «подобрать цвета»

MD3 — не палитра, а система: роли (`primary`, `onPrimaryContainer`,
`surfaceVariant`, `outlineVariant`…) связаны правилами контраста и смысла
(«container = заливка, on-* = содержимое, variant = ниже акцент»). Поэтому
рамка фокуса = `primary`, срочное окно = `error`, неактивная рамка =
`outlineVariant`, поверхности тонируются `surfaceTint` по уровням elevation
(0/5/8/11/12/14 %), а альфа/blur тени picom выводятся из того же уровня —
и при смене seed color или dark/light вся схема остаётся семантически верной. Подробности и таблица привязок — `docs/TOKENS.md`.
