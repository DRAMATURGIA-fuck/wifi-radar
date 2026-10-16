#!/usr/bin/env bash
# Устанавливает Wi-Fi Radar в меню приложений Linux (Mint/любой с XDG).
# Ничего не копирует в систему и не требует root — всё кладётся в ~/.local.
# Удаление:  ./install-linux.sh --uninstall

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
IC256="$HOME/.local/share/icons/hicolor/256x256/apps"
ICSVG="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP="$APPS/wifi-radar.desktop"

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$DESKTOP" "$IC256/wifi-radar.png" "$ICSVG/wifi-radar.svg"
  update-desktop-database "$APPS" 2>/dev/null || true
  gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
  echo "Wi-Fi Radar удалён из меню."
  exit 0
fi

mkdir -p "$APPS" "$IC256" "$ICSVG"
cp "$DIR/assets/icon.png" "$IC256/wifi-radar.png"
cp "$DIR/assets/icon.svg" "$ICSVG/wifi-radar.svg"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Wi-Fi Radar
Comment=Поиск лучшей точки Wi-Fi по силе сигнала
Exec=python3 "$DIR/wifi_radar.py"
Icon=wifi-radar
Terminal=false
Categories=Utility;Network;
Keywords=wifi;signal;radar;network;
EOF
chmod +x "$DESKTOP"

update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Готово! Ищи «Wi-Fi Radar» в меню приложений."
echo "(если иконка не появилась сразу — перелогинься или подожди минуту)"
