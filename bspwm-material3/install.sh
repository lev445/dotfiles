#!/usr/bin/env bash
#=============================================================================
#  install.sh — установка bspwm-material3
#
#    ./install.sh                 # в ~/.config/bspwm-material3
#    ./install.sh --prefix DIR    # свой каталог
#    ./install.sh --no-link       # не трогать ~/.config/bspwm и ~/.config/sxhkd
#
#  Что делает:
#    1. проверяет зависимости (жёсткие — останавливают, мягкие — предупреждают);
#    2. копирует проект в префикс (без node_modules/__pycache__/.git);
#    3. делает резервные копии старых bspwmrc/sxhkdrc и линкует наши;
#    4. генерирует тему под новый путь (generated/*, picom, polybar, rofi);
#    5. печатает шпаргалку по запуску и горячим клавишам.
#=============================================================================
set -uo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.config/bspwm-material3"
DO_LINK=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)   PREFIX="${2:?--prefix требует путь}"; shift 2 ;;
        --no-link)  DO_LINK=0; shift ;;
        -h|--help)  grep '^#' "$0" | sed 's/^# \{0,2\}//'; exit 0 ;;
        *) echo "неизвестный аргумент: $1" >&2; exit 2 ;;
    esac
done

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m✘\033[0m %s\n' "$*" >&2; exit 1; }

#------------------------------------------------------------------------------
say "1/5 зависимости"
MISSING=()
for req in bash python3 bspwm sxhkd; do
    have "$req" || MISSING+=("$req")
done
[[ ${#MISSING[@]} -eq 0 ]] || die "не хватает обязательного: ${MISSING[*]} (пакеты: bspwm, sxhkd, python3)"
ok "обязательное на месте: bash, python3, bspwm, sxhkd"

SOFT=(picom polybar rofi feh dunst python3-tk)
ABSENT=()
for s in "${SOFT[@]}"; do
    case "$s" in
        python3-tk) python3 -c 'import tkinter' 2>/dev/null || ABSENT+=("python3-tk (GUI-редактор темы)") ;;
        *) have "$s" || ABSENT+=("$s") ;;
    esac
done
if [[ ${#ABSENT[@]} -gt 0 ]]; then
    warn "нет (не критично, функционал деградирует): ${ABSENT[*]}"
else
    ok "рекомендуемое на месте: picom, polybar, rofi, feh, dunst, tkinter"
fi

if have fc-list; then
    fc-list 2>/dev/null | grep -qi "JetBrainsMono.*Nerd\|JetBrains Mono Nerd" \
        && ok "шрифт JetBrainsMono Nerd Font найден" \
        || warn "нет JetBrainsMono Nerd Font — polybar/rofi откатятся на fallback-шрифт"
fi

#------------------------------------------------------------------------------
say "2/5 копирование в $PREFIX"
mkdir -p "$PREFIX" || die "не могу создать $PREFIX"
TS="$(date +%Y%m%d-%H%M%S)"
if [[ -d "$PREFIX" && -n "$(ls -A "$PREFIX" 2>/dev/null)" ]]; then
    cp -a "$PREFIX" "$PREFIX.bak-$TS" && warn "старая установка сохранена в $PREFIX.bak-$TS"
fi
# копируем всё, кроме служебного; rsync не гарантирован — tar+exclude
tar -C "$SRC_DIR" \
    --exclude=./node_modules --exclude=./.mcu_nm --exclude=./__pycache__ --exclude='./.git' \
    --exclude='*/__pycache__' --exclude='./.arena' \
    -cf - . | tar -C "$PREFIX" -xf - || die "копирование не удалось"
chmod +x "$PREFIX"/bin/* "$PREFIX"/tools/*.py "$PREFIX"/tools/tests/*.py 2>/dev/null
ok "файлы на месте"

#------------------------------------------------------------------------------
say "3/5 подключение к bspwm и sxhkd"
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ $DO_LINK -eq 1 ]]; then
    mkdir -p "$XDG_CONFIG_HOME/bspwm" "$XDG_CONFIG_HOME/sxhkd"
    for pair in "bspwm/bspwmrc:$PREFIX/bspwmrc" "sxhkd/sxhkdrc:$PREFIX/sxhkd/sxhkdrc"; do
        dst="$XDG_CONFIG_HOME/${pair%%:*}"
        src="${pair#*:}"
        if [[ -L "$dst" ]]; then
            ln -sfn "$src" "$dst"
        elif [[ -e "$dst" ]]; then
            mv "$dst" "$dst.bak-$TS"
            warn "существующий $dst → $dst.bak-$TS"
            ln -s "$src" "$dst"
        else
            ln -s "$src" "$dst"
        fi
        ok "$dst → $src"
    done
else
    warn "--no-link: запускайте вручную: bspwm -c $PREFIX/bspwmrc"
fi

#------------------------------------------------------------------------------
say "4/5 генерация темы под новый путь"
if BSPWM_MD3_DIR="$PREFIX" "$PREFIX/bin/md3-apply" --stage=generate --quiet; then
    ok "generated/*, picom.conf, polybar, rofi, Xresources — перегенерированы"
else
    warn "md3-apply --stage=generate вернул ненулевой код (см. вывод выше)"
fi
if have fc-cache; then :; fi

#------------------------------------------------------------------------------
say "5/5 готово"
cat <<EOF

  Запуск (X11):
      echo 'exec bspwm' >> ~/.xinitrc        # если ещё нет
      startx                                  # или из display-менеджера

  Горячие клавиши (основные):
      super+Return   терминал          super+d      лаунчер (rofi)
      super+x        MD3-меню          super+shift+t  GUI-редактор темы
      super+F5       применить тему    super+shift+F5 рестарт WM
      super+grave    scratch-терминал  super+1..9,0   рабочие столы

  Тема:
      $PREFIX/tools/md3-theme-gui.py          # GUI (Tk, MD3-виджеты)
      $PREFIX/bin/md3-menu                    # меню: тема/сервисы/питание
      python3 $PREFIX/tools/md3_theme.py set --seed '#006A6A' --dark true

  Логи: ~/.local/state/bspwm-md3/log/
EOF
ok "установка завершена"
