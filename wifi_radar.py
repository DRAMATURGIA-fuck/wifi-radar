#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wi-Fi Radar — графический искатель Wi-Fi по силе сигнала.

Чем ближе/выше сигнал — тем чаще писк и зеленее шкала. Ходи по комнате
или поднимай ноутбук туда, где показатель растёт. Два быстрых писка —
новый рекорд (лучшая точка из пройденных).

Кроссплатформенно: Linux и Windows (macOS — по возможности).
Зависимостей, кроме стандартной библиотеки Python, нет.

Запуск:  python3 wifi_radar.py
"""

import platform
import re
import subprocess
import threading
import time
from collections import deque

APP_NAME = "Wi-Fi Radar"

# ──────────────────────────────────────────────────────────────────────────
#  Чтение сигнала (по платформам)
# ──────────────────────────────────────────────────────────────────────────

def quality_from_dbm(dbm):
    """dBm (-90..-30) -> качество 0..100."""
    q = int((dbm + 90) * 100 / 60)
    return max(0, min(100, q))


def interval_ms(q):
    """Качество 0..100 -> пауза между писками, мс (сильнее = чаще)."""
    q = max(0, min(100, q))
    return max(120, int(1500 - 1350 * q / 100))


def _lerp(a, b, t):
    return int(round(a + (b - a) * t))


def color_for(q):
    """Качество 0..100 -> цвет от красного к жёлтому к зелёному (#rrggbb)."""
    q = max(0, min(100, q))
    stops = [(0, (0xE5, 0x48, 0x4D)), (50, (0xF5, 0xA5, 0x24)), (100, (0x30, 0xA4, 0x6C))]
    for i in range(len(stops) - 1):
        q0, c0 = stops[i]
        q1, c1 = stops[i + 1]
        if q <= q1:
            t = (q - q0) / (q1 - q0) if q1 > q0 else 0
            return "#%02x%02x%02x" % (
                _lerp(c0[0], c1[0], t),
                _lerp(c0[1], c1[1], t),
                _lerp(c0[2], c1[2], t),
            )
    return "#30a46c"


def label_for(q):
    if q >= 80:
        return "отлично"
    if q >= 60:
        return "хорошо"
    if q >= 40:
        return "нормально"
    if q >= 20:
        return "слабо"
    return "очень слабо"


def _run(cmd):
    """Запустить команду, вернуть stdout (пустую строку при любой ошибке)."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=4,
            errors="replace",
        )
        return out.stdout or ""
    except Exception:
        return ""


# --- Linux ---

def _parse_proc_wireless(text):
    """Вернуть (iface, dbm|None) из содержимого /proc/net/wireless."""
    lines = text.splitlines()
    for ln in lines[2:]:
        parts = ln.split()
        if len(parts) >= 4:
            iface = parts[0].rstrip(":")
            lvl = parts[3].rstrip(".")
            try:
                dbm = int(float(lvl))
            except ValueError:
                return (iface, None)
            return (iface, dbm if dbm != 0 else None)
    return (None, None)


def _linux_ssid():
    s = _run(["iwgetid", "-r"]).strip()
    if s:
        return s
    out = _run(["nmcli", "-t", "-f", "IN-USE,SSID", "dev", "wifi"])
    for ln in out.splitlines():
        if ln.startswith("*"):
            parts = ln.split(":", 1)
            if len(parts) == 2 and parts[1]:
                return parts[1]
    return None


def _iw_signal(iface):
    if not iface:
        dev = _run(["iw", "dev"])
        m = re.search(r"Interface\s+(\S+)", dev)
        iface = m.group(1) if m else None
    if not iface:
        return None
    out = _run(["iw", "dev", iface, "link"])
    m = re.search(r"signal:\s*(-?\d+)", out)
    return int(m.group(1)) if m else None


def _nmcli_pct():
    out = _run(["nmcli", "-t", "-f", "IN-USE,SIGNAL", "dev", "wifi"])
    for ln in out.splitlines():
        if ln.startswith("*"):
            parts = ln.split(":")
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


def _read_linux():
    res = {"q": None, "dbm": None, "ssid": None, "iface": None, "connected": False}
    try:
        with open("/proc/net/wireless", "r") as f:
            iface, dbm = _parse_proc_wireless(f.read())
        res["iface"] = iface
        if dbm is not None:
            res["dbm"] = dbm
            res["q"] = quality_from_dbm(dbm)
            res["connected"] = True
    except Exception:
        pass

    if not res["connected"]:
        dbm = _iw_signal(res["iface"])
        if dbm is not None:
            res["dbm"] = dbm
            res["q"] = quality_from_dbm(dbm)
            res["connected"] = True

    if not res["connected"]:
        p = _nmcli_pct()
        if p is not None:
            res["q"] = p
            res["connected"] = True

    if res["connected"]:
        res["ssid"] = _linux_ssid()
    return res


# --- Windows ---

def _parse_netsh(text):
    """Вернуть (q|None, ssid|None) из вывода `netsh wlan show interfaces`."""
    q = None
    m = re.search(r"(\d{1,3})\s*%", text)
    if m:
        q = max(0, min(100, int(m.group(1))))
    ssid = None
    for ln in text.splitlines():
        ls = ln.strip()
        if ls.startswith("SSID"):  # не BSSID — та начинается с 'B'
            m2 = re.match(r"SSID\s*[:：]\s*(.+)", ls)
            if m2:
                ssid = m2.group(1).strip()
                break
    return (q, ssid)


def _read_windows():
    res = {"q": None, "dbm": None, "ssid": None, "iface": "wlan", "connected": False}
    out = _run(["netsh", "wlan", "show", "interfaces"])
    q, ssid = _parse_netsh(out)
    if q is not None:
        res["q"] = q
        res["ssid"] = ssid
        res["connected"] = True
    return res


# --- macOS (по возможности) ---

def _read_macos():
    res = {"q": None, "dbm": None, "ssid": None, "iface": "en0", "connected": False}
    airport = ("/System/Library/PrivateFrameworks/Apple80211.framework/"
               "Versions/Current/Resources/airport")
    out = _run([airport, "-I"])
    m = re.search(r"agrCtlRSSI:\s*(-?\d+)", out)
    if m:
        dbm = int(m.group(1))
        res["dbm"] = dbm
        res["q"] = quality_from_dbm(dbm)
        res["connected"] = True
        s = re.search(r"\bSSID:\s*(.+)", out)
        if s:
            res["ssid"] = s.group(1).strip()
    return res


def read_signal():
    system = platform.system()
    if system == "Linux":
        return _read_linux()
    if system == "Windows":
        return _read_windows()
    if system == "Darwin":
        return _read_macos()
    return {"q": None, "dbm": None, "ssid": None, "iface": None, "connected": False}


# ──────────────────────────────────────────────────────────────────────────
#  Звук (писк, по платформам)
# ──────────────────────────────────────────────────────────────────────────

def make_beep():
    """Вернуть функцию beep(q), издающую короткий сигнал. Или no-op."""
    system = platform.system()

    if system == "Windows":
        try:
            import winsound

            def beep(q):
                freq = int(600 + 9 * max(0, min(100, q)))  # выше сигнал — выше тон
                try:
                    winsound.Beep(freq, 45)
                except Exception:
                    pass
            return beep
        except Exception:
            pass

    if system == "Darwin":
        snd = "/System/Library/Sounds/Tink.aiff"

        def beep(q):
            try:
                subprocess.Popen(["afplay", snd],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        return beep

    # Linux: проигрыватель + системный звук
    player = None
    for p in ("paplay", "pw-play", "aplay"):
        if _which(p):
            player = p
            break
    sound = None
    for s in (
        "/usr/share/sounds/freedesktop/stereo/message.oga",
        "/usr/share/sounds/freedesktop/stereo/bell.oga",
        "/usr/share/sounds/freedesktop/stereo/dialog-information.oga",
        "/usr/share/sounds/freedesktop/stereo/complete.oga",
    ):
        import os
        if os.path.isfile(s):
            sound = s
            break

    if player and sound:
        def beep(q):
            try:
                subprocess.Popen([player, sound],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        return beep

    def beep(q):
        pass
    return beep


def _which(name):
    from shutil import which
    return which(name) is not None


# ──────────────────────────────────────────────────────────────────────────
#  Фоновый «гейгер» (писк с интервалом по силе сигнала)
# ──────────────────────────────────────────────────────────────────────────

class Beeper(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.beep = make_beep()
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            if self.app.sound_on and self.app.connected:
                q = self.app.current_q
                self.beep(q)
                # два быстрых писка при новом рекорде
                if self.app.consume_record_flag():
                    time.sleep(0.09)
                    self.beep(q)
                time.sleep(interval_ms(q) / 1000.0)
            else:
                time.sleep(0.2)

    def stop(self):
        self._stop.set()


# ──────────────────────────────────────────────────────────────────────────
#  Графический интерфейс
# ──────────────────────────────────────────────────────────────────────────

# Цвета темы
BG = "#0d0f14"
CARD = "#141821"
FG = "#e6e8ec"
MUTED = "#8b93a1"
TRACK = "#242a36"


def _font_family():
    return "Segoe UI" if platform.system() == "Windows" else "DejaVu Sans"


class App:
    def __init__(self, root, tk, tkfont):
        self.tk = tk
        self.root = root
        fam = _font_family()

        self.current_q = 0
        self.connected = False
        self.best = -1
        self.prev = -1
        self.sound_on = True
        self._record_flag = False
        self._lock = threading.Lock()

        root.title(APP_NAME)
        root.configure(bg=BG)
        root.resizable(False, False)
        try:
            import os
            _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", "icon.png")
            if os.path.isfile(_icon):
                self._iconimg = tk.PhotoImage(file=_icon)
                root.iconphoto(True, self._iconimg)
        except Exception:
            pass
        try:
            root.geometry("440x708")
        except Exception:
            pass

        self.f_title = tkfont.Font(family=fam, size=15, weight="bold")
        self.f_big = tkfont.Font(family=fam, size=60, weight="bold")
        self.f_unit = tkfont.Font(family=fam, size=20, weight="bold")
        self.f_sub = tkfont.Font(family=fam, size=12)
        self.f_status = tkfont.Font(family=fam, size=22, weight="bold")
        self.f_small = tkfont.Font(family=fam, size=11)

        # Заголовок
        tk.Label(root, text="Wi-Fi Radar", font=self.f_title, bg=BG, fg=FG).pack(pady=(18, 2))
        tk.Label(root, text="чем сильнее сигнал — тем чаще писк",
                 font=self.f_small, bg=BG, fg=MUTED).pack(pady=(0, 6))

        # Шкала-дуга
        self.CW, self.CH = 400, 270
        self.cx, self.cy, self.r = 200, 205, 150
        self.canvas = tk.Canvas(root, width=self.CW, height=self.CH,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()

        bbox = (self.cx - self.r, self.cy - self.r, self.cx + self.r, self.cy + self.r)
        # фоновая дуга
        self.canvas.create_arc(*bbox, start=210, extent=-240, style="arc",
                               outline=TRACK, width=24)
        # дуга значения (обновляется)
        self.arc_val = self.canvas.create_arc(*bbox, start=210, extent=0, style="arc",
                                               outline="#30a46c", width=24)
        # маркер рекорда
        self.best_dot = self.canvas.create_oval(0, 0, 0, 0, outline="", fill="")
        # крупное число
        self.num_item = self.canvas.create_text(self.cx - 6, self.cy - 6, text="0",
                                                 font=self.f_big, fill=FG, anchor="e")
        self.unit_item = self.canvas.create_text(self.cx + 2, self.cy + 2, text="%",
                                                  font=self.f_unit, fill=MUTED, anchor="w")
        self.dbm_item = self.canvas.create_text(self.cx, self.cy + 48, text="",
                                                 font=self.f_sub, fill=MUTED)

        # Статус
        self.status_lbl = tk.Label(root, text="—", font=self.f_status, bg=BG, fg=MUTED)
        self.status_lbl.pack(pady=(4, 0))

        # Живой график силы сигнала (последние ~30 с)
        self.GW, self.GH = 400, 78
        self.history = deque(maxlen=90)
        tk.Label(root, text="сигнал за последние ~30 с", font=self.f_small,
                 bg=BG, fg=MUTED).pack(pady=(14, 3))
        self.graph = tk.Canvas(root, width=self.GW, height=self.GH, bg=CARD,
                               highlightthickness=0)
        self.graph.pack()

        # Инфо-строки
        info = tk.Frame(root, bg=BG)
        info.pack(pady=(8, 0))
        self.ssid_lbl = tk.Label(info, text="сеть: —", font=self.f_small, bg=BG, fg=MUTED)
        self.ssid_lbl.grid(row=0, column=0, padx=10)
        self.trend_lbl = tk.Label(info, text="", font=self.f_small, bg=BG, fg=MUTED)
        self.trend_lbl.grid(row=0, column=1, padx=10)
        self.best_lbl = tk.Label(info, text="рекорд: —", font=self.f_small, bg=BG, fg=MUTED)
        self.best_lbl.grid(row=0, column=2, padx=10)

        # Управление
        ctrl = tk.Frame(root, bg=BG)
        ctrl.pack(pady=(16, 0))
        self.sound_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(ctrl, text="Звук", variable=self.sound_var,
                             command=self._toggle_sound, font=self.f_small,
                             bg=BG, fg=FG, selectcolor=CARD, activebackground=BG,
                             activeforeground=FG, highlightthickness=0, bd=0)
        chk.grid(row=0, column=0, padx=8)
        btn = tk.Button(ctrl, text="Сбросить рекорд", command=self._reset_best,
                        font=self.f_small, bg=CARD, fg=FG, activebackground=TRACK,
                        activeforeground=FG, bd=0, padx=12, pady=6, highlightthickness=0)
        btn.grid(row=0, column=1, padx=8)

        tk.Label(root, text="Ходи по комнате или поднимай ноутбук туда, где растёт.",
                 font=self.f_small, bg=BG, fg=MUTED, wraplength=400).pack(side="bottom", pady=14)

        self.beeper = Beeper(self)
        self.beeper.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.tick()

    # --- действия ---
    def _toggle_sound(self):
        self.sound_on = bool(self.sound_var.get())

    def _reset_best(self):
        self.best = -1
        self.best_lbl.config(text="рекорд: —")

    def _on_close(self):
        try:
            self.beeper.stop()
        except Exception:
            pass
        self.root.destroy()

    def consume_record_flag(self):
        with self._lock:
            f = self._record_flag
            self._record_flag = False
            return f

    # --- геометрия маркера рекорда ---
    def _point_on_arc(self, q):
        import math
        ang = 210 - 240 * (max(0, min(100, q)) / 100.0)  # градусы, как в Tk
        rad = math.radians(ang)
        x = self.cx + self.r * math.cos(rad)
        y = self.cy - self.r * math.sin(rad)
        return x, y

    # --- отрисовка живого графика ---
    def draw_graph(self):
        g = self.graph
        g.delete("all")
        w, h, pad = self.GW, self.GH, 8
        inner = h - 2 * pad

        def yv(v):
            return pad + inner * (1 - max(0, min(100, v)) / 100.0)

        # ориентиры 0 / 50 / 100 %
        for lvl in (0, 50, 100):
            y = yv(lvl)
            g.create_line(pad, y, w - pad, y, fill=TRACK,
                          dash=(2, 4) if lvl == 50 else (1, 6))

        vals = list(self.history)
        n = len(vals)
        if n < 2:
            return
        step = (w - 2 * pad) / (self.history.maxlen - 1)
        x0 = w - pad - (n - 1) * step  # прижать свежие данные к правому краю
        pts = []
        for i, v in enumerate(vals):
            pts.extend((x0 + i * step, yv(v)))
        col = color_for(vals[-1])
        g.create_line(*pts, fill=col, width=2, smooth=True)
        g.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3, pts[-1] + 3,
                      fill=col, outline="")

    # --- основной цикл обновления ---
    def tick(self):
        try:
            data = read_signal()
        except Exception:
            data = {"connected": False, "q": None, "dbm": None, "ssid": None}

        self.connected = bool(data.get("connected"))
        c = self.tk

        if not self.connected:
            self.current_q = 0
            self.canvas.itemconfig(self.arc_val, extent=0)
            self.canvas.itemconfig(self.num_item, text="—")
            self.canvas.itemconfig(self.dbm_item, text="нет связи с точкой")
            self.status_lbl.config(text="не подключено", fg=MUTED)
            self.ssid_lbl.config(text="сеть: —")
            self.trend_lbl.config(text="")
            self.canvas.itemconfig(self.best_dot, outline="", fill="")
            self.history.append(0)
            self.draw_graph()
            self.root.after(500, self.tick)
            return

        q = int(data.get("q") or 0)
        q = max(0, min(100, q))
        self.current_q = q
        col = color_for(q)

        # дуга + число
        self.canvas.itemconfig(self.arc_val, extent=-240 * q / 100.0, outline=col)
        self.canvas.itemconfig(self.num_item, text=str(q), fill=FG)
        dbm = data.get("dbm")
        self.canvas.itemconfig(self.dbm_item,
                               text=("%d dBm" % dbm) if dbm is not None else "")
        self.status_lbl.config(text=label_for(q), fg=col)

        ssid = data.get("ssid")
        self.ssid_lbl.config(text="сеть: %s" % (ssid if ssid else "—"))

        # тренд
        if q > self.prev:
            self.trend_lbl.config(text="↑ теплее", fg="#30a46c")
        elif q < self.prev:
            self.trend_lbl.config(text="↓ холоднее", fg="#e5484d")
        else:
            self.trend_lbl.config(text="= ровно", fg=MUTED)

        # рекорд
        if q > self.best:
            self.best = q
            with self._lock:
                self._record_flag = True
            bx, by = self._point_on_arc(q)
            self.canvas.coords(self.best_dot, bx - 7, by - 7, bx + 7, by + 7)
            self.canvas.itemconfig(self.best_dot, outline="#ffffff", fill="")
        self.best_lbl.config(text="рекорд: %d%%" % self.best if self.best >= 0 else "рекорд: —")

        self.history.append(q)
        self.draw_graph()

        self.prev = q
        self.root.after(350, self.tick)


def main():
    try:
        import tkinter as tk
        from tkinter import font as tkfont
    except Exception:
        print("Не найден Tkinter. На Linux установите пакет python3-tk:\n"
              "    sudo apt install python3-tk\n"
              "На Windows Tkinter уже входит в установщик Python с python.org.")
        return
    root = tk.Tk()
    App(root, tk, tkfont)
    root.mainloop()


if __name__ == "__main__":
    main()
