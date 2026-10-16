#!/usr/bin/env bash
# wifi-radar.sh — звуковой искатель Wi-Fi по силе сигнала.
#
# Как пользоваться на слух:
#   • Чем ЧАЩЕ писк — тем СИЛЬНЕЕ сигнал.
#   • Два быстрых писка подряд = новый рекорд, лучшее место из пройденных.
#   • Ходи по квартире / поднимай ноут вверх. Идёшь туда, где писк учащается.
#   • Выход: Ctrl+C.

set -u

# --- найти Wi-Fi интерфейс ---
IFACE="$(nmcli -t -f DEVICE,TYPE device status 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')"
if [ -z "${IFACE:-}" ]; then
  IFACE="$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')"
fi
if [ -z "${IFACE:-}" ] && [ -r /proc/net/wireless ]; then
  IFACE="$(awk -F: 'NR>2{gsub(/ /,"",$1); print $1; exit}' /proc/net/wireless)"
fi
if [ -z "${IFACE:-}" ]; then
  echo "Не нашёл Wi-Fi интерфейс. Включён ли Wi-Fi?"
  exit 1
fi

# --- звук для писка ---
SND=""
for f in /usr/share/sounds/freedesktop/stereo/message.oga \
         /usr/share/sounds/freedesktop/stereo/bell.oga \
         /usr/share/sounds/freedesktop/stereo/dialog-information.oga \
         /usr/share/sounds/freedesktop/stereo/complete.oga; do
  [ -f "$f" ] && SND="$f" && break
done

PLAYER=""
for p in paplay pw-play aplay; do
  command -v "$p" >/dev/null 2>&1 && PLAYER="$p" && break
done

beep() {
  if [ -n "$SND" ] && [ -n "$PLAYER" ]; then
    "$PLAYER" "$SND" >/dev/null 2>&1 &
  else
    printf '\a'   # системный звонок терминала (если включён в настройках)
  fi
}

# --- измерение сигнала ---
# Ставит SIG_DBM (может быть пустым) и SIG_Q (0..100). Возвращает 1, если связи нет.
measure() {
  SIG_DBM=""; SIG_Q=""
  local out lvl p

  # 1) напрямую из ядра — работает всегда, без зависимостей и без локали
  if [ -r /proc/net/wireless ]; then
    out="$(awk -v ifc="$IFACE:" '$1==ifc{l=$4; sub(/\.$/,"",l); print l; exit}' /proc/net/wireless)"
    if [ -n "$out" ] && [ "$out" != "0" ]; then
      SIG_DBM="$out"
      SIG_Q=$(( (out + 90) * 100 / 60 ))
      return 0
    fi
  fi

  # 2) iw — точный dBm
  if command -v iw >/dev/null 2>&1; then
    lvl="$(iw dev "$IFACE" link 2>/dev/null | awk '/signal:/{print $2; exit}')"
    if [ -n "$lvl" ]; then
      SIG_DBM="$lvl"
      SIG_Q=$(( (lvl + 90) * 100 / 60 ))
      return 0
    fi
  fi

  # 3) nmcli — проценты активной точки (IN-USE помечен *, от языка не зависит)
  if command -v nmcli >/dev/null 2>&1; then
    p="$(nmcli -t -f IN-USE,SIGNAL dev wifi 2>/dev/null | awk -F: '$1=="*"{print $2; exit}')"
    if [ -n "$p" ]; then
      SIG_Q="$p"
      return 0
    fi
  fi

  return 1
}

cleanup() { printf '\n\e[?25h'; echo "Готово."; exit 0; }
trap cleanup INT TERM

printf '\e[?25l'   # спрятать курсор
echo "Интерфейс: $IFACE   (Ctrl+C — выход)"
echo "Ходи по комнате / поднимай ноут. Чаще писк = сильнее сигнал."
echo

best=-1
prev=-1
while true; do
  if ! measure; then
    printf '\r\e[K[нет связи с точкой — подключись к Wi-Fi]   '
    sleep 1.5
    continue
  fi

  q="$SIG_Q"
  [ "$q" -lt 0 ]   && q=0
  [ "$q" -gt 100 ] && q=100

  # метка
  if   [ "$q" -ge 80 ]; then lbl="отлично"
  elif [ "$q" -ge 60 ]; then lbl="хорошо"
  elif [ "$q" -ge 40 ]; then lbl="нормально"
  elif [ "$q" -ge 20 ]; then lbl="слабо"
  else                       lbl="очень слабо"
  fi

  # полоска
  barlen=$(( q / 5 ))
  bar="$(printf '%*s' "$barlen" '' | tr ' ' '#')"

  # тренд
  if   [ "$q" -gt "$prev" ]; then trend="^ теплее"
  elif [ "$q" -lt "$prev" ]; then trend="v холоднее"
  else                            trend="= ровно"
  fi

  # новый рекорд?
  newbest=""
  if [ "$q" -gt "$best" ]; then
    best="$q"
    newbest="  *** ЛУЧШЕЕ МЕСТО ***"
    beep; sleep 0.08; beep        # двойной писк
  else
    beep
  fi

  if [ -n "$SIG_DBM" ]; then disp="${SIG_DBM} dBm"; else disp="${q}%"; fi
  printf '\r\e[K%-9s %3s%%  [%-20s] %-11s %-11s%s' \
         "$disp" "$q" "$bar" "$lbl" "$trend" "$newbest"

  prev="$q"

  # пауза между писками: сильнее сигнал — короче пауза (120мс..1500мс)
  ms=$(( 1500 - 1350 * q / 100 ))
  [ "$ms" -lt 120 ] && ms=120
  printf -v delay '%d.%03d' $((ms/1000)) $((ms%1000))
  sleep "$delay"
done
