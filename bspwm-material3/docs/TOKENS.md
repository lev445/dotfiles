# MD3-токены в bspwm-material3

Справочник: какие роли `md.sys.color` и величины `md.sys.*` где используются,
и как их менять. Всё ниже — производное от `generated/theme-state.json`
(seed, scheme, contrast, dark + параметры формы/теней); править руками нужно
именно state (GUI / `md3-menu` / `md3_theme.py set`), а не сгенерированные файлы.

## 1. Поток значений

| Артефакт | Формат цвета | Кто пишет |
|---|---|---|
| `generated/theme.conf` | `#RRGGBB`, snake_case имена (`MD3_ON_SURFACE_VARIANT`) | `md3_theme.py` |
| `generated/theme.json` | JSON: роли, палитры, elevation, WCAG-отчёт | то же |
| `generated/Xresources.md3` | `#RRGGBB`, `*.color0..15` (ANSI16 из тональных палитр) | то же |
| `picom.conf` | `#RRGGBB` + `shadow-opacity` | шаблон `picom.conf.template` |
| `polybar/colors.ini` | `#AARRGGBB` (`PB_*`) | шаблон `polybar-colors.ini.template` |
| `rofi/md3.rasi` | `#RRGGBBAA` (`ROFI_*`) | шаблон `rofi-md3.rasi.template` |
| `wallpapers/md3-*.{svg,png}` | RGB-растр / SVG | `tools/md3-wall.py` |

> Form-factor форматов — не прихоть: polybar исторически берёт альфу **первым**
> байтом (`#AARRGGBB`), rofi — **последним** (`#RRGGBBAA`), picom/X11 — без альфы.
> Конвертацию делает движок, в шаблоны попадают уже готовые `PB_*`/`ROFI_*`.

## 2. Роли цвета → привязки

### bspwm (`bspc config` из bspwmrc)

| Настройка bspwm | Роль MD3 | Смысл |
|---|---|---|
| `focused_border_color` | `primary` | активное окно = главный акцент |
| `normal_border_color` | `outlineVariant` | неактивные — тихая линия сетки |
| `active_border_color` | `secondaryContainer` | фокус на другом мониторе |
| `urgent_border_color` | `error` | срочность = семантика ошибки |
| `presel_feedback_color` | `tertiary` | подсветка преселектора |
| `border_width` | — | 2 dp (spec: outline 2 dp) |
| `window_gap` / `*_padding` | — | из state: `gap`, `padding` (12/16) |

### picom (`picom.conf`)

| Опция | Источник | Примечание |
|---|---|---|
| `corner-radius` | state `corner_radius` (12) | MD3 shape: M=12 |
| `shadow-color` | роль `shadow` (md.sys.color.shadow) | берётся из схемы, не хардкодом |
| `shadow-opacity`, `shadow-radius`, offset | уровень elevation из state (`shadow_elevation`) | альфа/blur/dy растут с уровнем |
| `active-opacity` / `inactive-opacity` | state `inactive_opacity` (0.94) | |
| `blur: { method, strength }` | state `blur_strength` (14), dual_kawase | |
| `animations` / кривые | state `animations`, `animation_scale` | cubic-bezier из MD3 Motion; требуют picom ≥11 |
| WINDOW RULES | классы терминалов/фуллскрина | rules отключают legacy-опции — всё только через них |

### polybar (`polybar/colors.ini`, `config.ini`)

| Элемент бара | Роль |
|---|---|
| фон бара | `surfaceContainer` (elevation 2) |
| текст/иконки | `onSurface` |
| второстепенный текст | `onSurfaceVariant` |
| активный workspace | `primary` на `primaryContainer`, текст `onPrimaryContainer` |
| неактивный workspace | `onSurfaceVariant` на `surfaceContainerHigh` |
| разделители/линии | `outlineVariant` |
| предупреждения (громкость 0, сеть off) | `error` / `onError` |
| модуль темы (индикатор seed) | `primary` |

### rofi (`rofi/md3.rasi`)

| Часть | Роль | Форма |
|---|---|---|
| окно | `surfaceContainerHigh` | radius 28 (XL) |
| поле ввода | `surfaceContainerHighest` | radius 8 (S) |
| выбранная строка | `secondaryContainer` + `onSecondaryContainer` | radius 16 (L, full-shape state layer) |
| курсор/акцент | `primary` | |
| placeholder/подписи | `onSurfaceVariant` | |

### Xresources (`*.color0…15`)

ANSI16 собирается из тональных палитр MCU: normal — tones 20/40/40/40/40/40/80/90
по палитрам neutral/primary/secondary/tertiary/error, bright — те же hue при
tones 60/80. Терминал наследует тему без своей палитры.

## 3. Не-цветовые токены

| Токен | Значения | Где живёт |
|---|---|---|
| `md.sys.shape` | XS4 S8 M12 L16 L+20 XL28 XL+32 XXL48 full | radius’ы picom/rofi/preview |
| `md.sys.motion` | short1…4 (50–200), medium1…4 (250–400), long1…4 (450–600) | GUI-анимации, picom animations |
| easing | emphasized-decel `(0.05,0.7,0.1,1)`, emphasized-accel `(0.3,0,0.8,0.15)`, standard `(0.2,0,0,1)`, standard-decel `(0,0,0,1)`, standard-accel `(0.3,0,1,1)` | солвер в GUI + picom `cubic-bezier(...)` |
| state layers | hover .08, focus .12, pressed .12, dragged .16 | виджеты GUI (blend поверх elevation-поверхности) |
| elevation tint | 0/5/8/11/12/14 % surfaceTint | `theme.elevation[0..5]`, фон бара/карточек |

## 4. Контраст и схемы

* `scheme`: `tonal-spot` (дефолт Android), `content`, `monochrome`.
  Предвычисленный датасет покрывает 10 seed-пресетов для tonal-spot и базовый
  seed для content/monochrome; для произвольного seed роли досчитываются
  официальным MCU через node (`tools/md3-dump.mjs`-рантайм), а без node —
  берутся от ближайшего пресета по HCT-оттенку (`theme.source` покажет что
  сработало).
* `contrast`: `-1.0 | 0.0 | +1.0` (medium/high в меню = 0.5/1.0).
* WCAG-отчёт (`theme.json → contrast_report`) проверяет пары
  primary/onPrimary, surface/onSurface, container/onContainer… и помечает
  пары ниже 4.5:1 — GUI показывает их в карточке «Tokens».

## 5. Быстрые команды

```bash
# сменить seed и режим
python3 tools/md3_theme.py set --seed '#B3261E' --light --scheme content
bin/md3-apply                       # всё: файлы + xrdb + bspc + сервисы
bin/md3-reload theme                # только перечитать тему (USR1 → bspwmrc)

# форма и эффекты
python3 tools/md3_theme.py set corner_radius=20 shadow_elevation=3 \
        inactive_opacity=0.90 blur_strength=18 animations=true

# дамп всех ролей текущей темы / сводка состояния
python3 tools/md3_theme.py export roles | less
python3 tools/md3_theme.py show
```

Любое изменение state автоматически перегенерирует **все** производные файлы —
включая обои (`md3-wall.py` вызывается из `md3-apply`, если есть конвертер,
иначе PNG перерисовывается встроенным растеризатором).
