#!/usr/bin/env bash
#=============================================================================
#  vm/bootstrap.sh — подготовка ВМ к запуску bspwm-material3
#
#  Использование (внутри ВМ, из смонтированной шары или скопированной папки):
#      bash /mnt/host/bspwm-material3/vm/bootstrap.sh
#
#  Делает:
#    1. ставит X11 + bspwm-стек через pacman / apt / dnf / xbps;
#    2. проверяет версию picom (анимации требуют ≥11) и при необходимости
#       отключает их в теме;
#    3. запускает install.sh (копия + симлинки + генерация темы);
#    4. прописывает exec bspwm в ~/.xinitrc и автозапуск startx с tty1;
#    5. напоминает про шрифт и polkit.
#
#  Рекомендую Arch (picom 12 из репозитория). На Debian/Ubuntu picom старый —
#  скрипт сам предупредит и уберёт анимации/правила, остальное заработает.
#=============================================================================
set -uo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUDO=""
[[ $EUID -eq 0 ]] || SUDO="sudo"

say() { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m!\033[0m %s\n' "$*"; }

#------------------------------------------------------------------------------
say "1/4 пакеты"
if command -v pacman >/dev/null; then
    $SUDO pacman -Sy --noconfirm
    $SUDO pacman -S --needed --noconfirm \
        xorg xorg-xinit xorg-xrdb xset \
        bspwm sxhkd picom polybar rofi feh dunst alacritty \
        python3 tk ttf-jetbrains-mono-nerd \
        polkit-gnome numlockx xclip maim \
        || warn "часть пакетов не поставилась — смотри вывод выше"
elif command -v apt-get >/dev/null; then
    $SUDO apt-get update
    $SUDO apt-get install -y \
        xorg xinit x11-xserver-utils \
        bspwm sxhkd picom polybar rofi feh dunst alacritty \
        python3 python3-tk fonts-jetbrains-mono \
        policykit-1-gnome numlockx xclip maim \
        || warn "часть пакетов не поставилась — смотри вывод выше"
    warn "Debian/Ubuntu: picom старый (<11) — анимации будут отключены ниже; JetBrainsMono не Nerd-вариант — иконки polybar могут отсутствовать"
elif command -v dnf >/dev/null; then
    $SUDO dnf install -y xorg-x11-server-Xorg xinit xorg-x11-xset \
        bspwm sxhkd picom polybar rofi feh dunst alacritty \
        python3 python3-tkinter jetbrains-mono-fonts \
        polkit-gnome numlockx xclip maim || warn "dnf: часть пакетов не нашлась"
elif command -v xbps-install >/dev/null; then
    $SUDO xbps-install -S xorg bspwm sxhkd picom polybar rofi feh dunst \
        alacritty python3 python3-tkinter ttf-jetbrains-mono || warn "xbps: что-то не нашлось"
else
    echo "неизвестный пакетный менеджер — поставь вручную: xorg xinit bspwm sxhkd picom polybar rofi feh dunst alacritty python3" >&2
fi
ok "пакеты обработаны"

#------------------------------------------------------------------------------
say "2/4 версия picom"
if command -v picom >/dev/null; then
    PV="$(picom --version 2>/dev/null | grep -oE 'v?[0-9]+(\.[0-9]+)?' | head -1 | tr -d 'v.')"
    MAJOR="${PV%%.*}"
    if [[ -n "$MAJOR" && "$MAJOR" -lt 11 ]]; then
        warn "picom $PV: анимации и WINDOW RULES из v12 не поддержатся — отключаю анимации в теме"
        python3 "$SRC_DIR/tools/md3_theme.py" set animations=false >/dev/null 2>&1 || true
    else
        ok "picom ${PV:-?}: анимации остаются включёнными"
    fi
else
    warn "picom нет вообще — сессия будет без композитора (без скруглений/теней)"
fi

#------------------------------------------------------------------------------
say "3/4 установка конфига"
bash "$SRC_DIR/install.sh" || { echo "install.sh упал" >&2; exit 1; }

#------------------------------------------------------------------------------
say "4/4 xinitrc и автозапуск"
touch "$HOME/.xinitrc"
grep -q 'exec bspwm' "$HOME/.xinitrc" 2>/dev/null || echo 'exec bspwm' >> "$HOME/.xinitrc"
# автозапуск startx при логине на tty1 (удобно в ВМ без display-менеджера)
PROFILE="$HOME/.bash_profile"
touch "$PROFILE"
if ! grep -q 'startx' "$PROFILE" 2>/dev/null; then
    cat >> "$PROFILE" <<'EOF'
# bspwm-material3: автостарт X с tty1
if [[ -z "$DISPLAY" && "$XDG_VTNR" == "1" ]]; then
    exec startx
fi
EOF
    ok ".bash_profile: startx с tty1 автоматически"
fi
ok "готово: перезалогинься (или `startx`) — поехали"
cat <<'EOF'

  Если в ВМ нет 3D-ускорения и picom падает на egl/glx:
      python3 ~/.config/bspwm-material3/tools/md3_theme.py set backend=xrender
      bin/md3-reload picom     # или super+F5 после рестарта
EOF
