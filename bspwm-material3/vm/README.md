# Запуск в QEMU

Коротко: поднимаешь ВМ с Arch (рекомендую), кидаешь туда тарболл конфига,
запускаешь `vm/bootstrap.sh`, логишься — попадаешь в сессию.

## 0. Тарболл

Рядом с проектом лежит готовый `bspwm-material3.tar.gz` (без node_modules).
Пересоздать:

```bash
tar -C .. -czf bspwm-material3.tar.gz \
    --exclude=bspwm-material3/node_modules \
    --exclude=bspwm-material3/.mcu_nm \
    --exclude='bspwm-material3/*/__pycache__' \
    bspwm-material3
```

## 1. Создать ВМ и поставить Arch

```bash
qemu-img create -f qcow2 md3-arch.qcow2 24G
qemu-system-x86_64 -enable-kvm -m 4G -smp 4 -cpu host \
    -drive file=md3-arch.qcow2,if=virtio \
    -cdrom archlinux-<date>-x86_64.iso -boot d \
    -device virtio-net-pci,netdev=n0 -netdev user,id=n0,hostfwd=tcp::2222-:22 \
    -vga virtio
```

Ставь как обычно (`archinstall` тоже подойдёт). В `archinstall`:
desktop = **none** (или minimal), bootloader = grub/systemd-boot,
пользователя создай с sudo.

## 2. Два способа закинуть конфиг

**а) scp (проще всего):** после установки в ВМ включи ssh (`systemctl enable --now sshd`),
затем с хоста:

```bash
scp -P 2222 bspwm-material3.tar.gz user@localhost:
ssh -p 2222 user@localhost 'tar xzf bspwm-material3.tar.gz'
```

**б) 9p-шара без сети:** добавь к qemu

```
-virtfs local,path=/путь/к/проекту,mount_tag=md3,security_model=mapped
```

в ВМ: `sudo mount -t 9p -o trans=virtio md3 /mnt`

## 3. Бутстрап и старт

```bash
bash ~/bspwm-material3/vm/bootstrap.sh    # или bash /mnt/vm/bootstrap.sh
reboot                                   # .bash_profile сам поднимет startx с tty1
```

После ребута попадаешь сразу в MD3-сессию: панель, обои, htop-терминал по
`super+Return`, GUI темы по `super+shift+t`.

## 4. Грабли QEMU ↔ picom

| Симптом | Причина / лечение |
|---|---|
| picom падает / чёрные окна | нет 3D: `md3_theme.py set backend=xrender`, затем `super+F5` |
| всё тормозит при blur | слабый virtio-gpu: уменьши `blur_strength=8` или выключи blur |
| хочу hardware GL | запускай с `-device virtio-gpu-gl-pci -display gtk,gl=on` (virgl) — тогда backend egl работает |
| мышь «в липком» окне | это не конфиг :): `ctrl+alt+g` отпустить захват |
| нет иконок в баре | не Nerd-шрифт (Debian): поставь `ttf-jetbrains-mono-nerd` / скачай Nerd-вариант |

Проверка, что тема живая: поменяй seed в GUI (`super+shift+t`) → `Apply` —
панель, рамки, обои и терминал перекрасятся без рестарта сессии.

## 5. Без KVM (macOS/без виртуализации)

Убери `-enable-kvm -cpu host`, добавь `-m 3G`; работать будет, но blur+анимации
лучше приглушить: `md3_theme.py set animations=false blur_strength=8`.
