#!/usr/bin/env python3
"""
Fischen-Bot - spielt die Angel-Minispiele automatisch.

Ablauf
  1. "You are currently fishing ..."            -> warten.
  2. "You got a bite. Press SPACE ..."          -> LEERTASTE.
  3. Balken-Spiel ("Press SPACE before the bar fluctuates 3 times")
       Die weiße Markierung (▼) ist die Grenze: links davon rot = verloren. Der blaue Balken
       läuft darüber hinaus bis 100 % und wieder zurück. Der Bot drückt LEERTASTE, sobald der
       Balken (vorausberechnet) sicher im blauen Bereich hinter der Markierung ist.
  4. Buchstaben-Spiel ("Press the keys displayed within the given time")
       Die Kästchen werden von links nach rechts gelesen und die Tasten W/A/S/D gedrückt.
       Erkannt wird über die Pfeile (▲=W ◄=A ▼=S ►=D), daher ist die Farbe egal;
       die Buchstaben selbst dienen als Gegenprobe.
  5. Gewonnen -> R (Fisch aufheben) -> LEERTASTE (neu auswerfen) -> wieder bei 1.

Hotkeys:  F9 = Pause/Weiter   F10 = Beenden

Start:    python fischen_bot.py            (danach ins Spielfenster klicken)
Probe:    python fischen_bot.py --dry      (erkennt alles, drückt aber keine Tasten)
Test:     python fischen_bot.py --test bild.png   (Erkennung an einem Screenshot prüfen)
Debug:    python fischen_bot.py --debug    (speichert Bilder in ./debug_fischen)

Benötigt: pip install mss numpy opencv-python pynput
"""

import argparse
import ctypes
import json
import os
import sys
import time

import cv2
import mss
import numpy as np
from pynput import keyboard

# ============================================================================
# Einstellungen
# ============================================================================
MONITOR = 1                                  # 1 = Hauptmonitor
TOP_AREA = (0.15, 0.00, 0.85, 0.14)          # Bereich der Meldung oben (links, oben, rechts, unten)
GAME_AREA = (0.15, 0.25, 0.85, 0.95)         # Bereich für Balken und Buchstaben

# Meldung oben: gelbes Wort "SPACE" im weißen Text
YELLOW_HUE = (15, 35)
BITE_MIN_REL = 0.30      # "SPACE" liegt beim Biss mittig im Text (~0,5), beim Balken vorne (~0,15)

# Balken: weiße Markierung = Grenze (steht still), links davon rot = verloren,
# rechts davon läuft der blaue Balken bis 100 % und wieder zurück
BLUE_HUE = (92, 114)
BLUE_MIN_SAT, BLUE_MIN_VAL = 100, 140
WHITE_MAX_SAT, WHITE_MIN_VAL = 45, 225
BAR_PRESS_FROM = 0.30    # drücken zwischen Markierung + 30 % des blauen Bereichs ...
BAR_PRESS_END = 0.10     # ... und 10 % vor 100 % - bevorzugt, während der Balken wächst
PRESS_LATENCY = 0.045    # Sekunden von "Taste drücken" bis das Spiel sie verarbeitet (Vorhalt)
BAR_TIMEOUT = 12.0       # länger dauert das Balken-Spiel nie

# Buchstaben-Kästchen: dunkelgrau, hochkant, in einer Reihe
CELL_MAX_SAT, CELL_VAL = 70, (35, 72)
CELL_ASPECT = (1.2, 2.3)                     # Höhe / Breite
CELL_MIN_W = 14
QTE_KEY_HOLD = 0.05
QTE_GAP = 0.10           # Pause zwischen zwei Buchstaben

AFTER_QTE = 2.5          # nach dem Buchstaben-Spiel so lange warten, dann R
R_PRESSES = 2            # so oft R drücken (Fisch aufheben) ...
R_GAP = 1.0              # ... mit so viel Abstand dazwischen
R_HOLD = 0.12            # so lange wird R gehalten (Sekunden)
AFTER_R = 1.0            # nach dem letzten R so lange warten, dann LEERTASTE (neu auswerfen)
BITE_COOLDOWN = 2.5      # nach dem Biss-Druck so lange keinen weiteren Biss-Druck
AUTO_RECAST = True       # neu auswerfen, wenn länger nichts zu sehen ist (z. B. Fisch verloren)
RECAST_AFTER = 10.0      # ... nach so vielen Sekunden ohne Meldung oben

USE_SCANCODES = True
FOCUS_CHECK = True
GAME_WINDOW_TITLE = ""   # optional: Teil des Spiel-Fenstertitels

KEYS = {"w": (0x57, 0x11), "a": (0x41, 0x1E), "s": (0x53, 0x1F), "d": (0x44, 0x20),
        "r": (0x52, 0x13), "space": (0x20, 0x39)}
NOT_GAME_EXES = {"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe",
                 "openconsole.exe", "code.exe", "python.exe", "pythonw.exe", "py.exe",
                 "explorer.exe", "claude.exe", "pycharm64.exe", "notepad.exe", "notepad++.exe"}

HERE = os.path.dirname(os.path.abspath(__file__))
CALIB_FILE = os.path.join(HERE, "fischen_kalibrierung.json")

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Abort(Exception):
    """F9/F10 gedrückt."""


class NoFocus(Exception):
    """Spielfenster nicht im Vordergrund."""


# ============================================================================
# Bildschirm, Tasten, Hotkeys
# ============================================================================
class Screen:
    def __init__(self):
        self.sct = mss.mss()
        mons = self.sct.monitors
        self.mon = mons[MONITOR] if MONITOR < len(mons) else mons[1]

    def rect(self, area):
        l, t, r, b = area
        m = self.mon
        return (m["left"] + int(m["width"] * l), m["top"] + int(m["height"] * t),
                int(m["width"] * (r - l)), int(m["height"] * (b - t)))

    def grab(self, rect):
        x, y, w, h = rect
        shot = self.sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])


class Control:
    def __init__(self):
        self.paused = False
        self.quit = False
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.daemon = True
        self.listener.start()

    def _on_press(self, key):
        if key == keyboard.Key.f9:
            self.paused = not self.paused
            log("PAUSE - F9 zum Fortsetzen" if self.paused else "Weiter.")
        elif key == keyboard.Key.f10:
            self.quit = True
            log("F10 - beende ...")
            return False
        return None

    def check(self):
        if self.quit or self.paused:
            raise Abort()

    def sleep(self, seconds):
        end = time.time() + seconds
        while True:
            self.check()
            left = end - time.time()
            if left <= 0:
                return
            time.sleep(min(0.005, left))


def foreground_window():
    if sys.platform != "win32":
        return "", ""
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32.OpenProcess.restype = wintypes.HANDLE
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    n = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, title, n + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if handle:
        size = wintypes.DWORD(1024)
        path = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            exe = os.path.basename(path.value)
        kernel32.CloseHandle(handle)
    return title.value, exe.lower()


def focus_ok():
    if not FOCUS_CHECK:
        return True, ""
    title, exe = foreground_window()
    info = f"'{title}' ({exe})"
    if GAME_WINDOW_TITLE:
        return GAME_WINDOW_TITLE.lower() in title.lower(), info
    return exe not in NOT_GAME_EXES, info


class Keys:
    def __init__(self, ctl, dry=False):
        self.ctl = ctl
        self.dry = dry
        self.kb = keyboard.Controller()
        self.codes = {}
        for name, (vk, scan) in KEYS.items():
            if USE_SCANCODES and sys.platform == "win32":
                self.codes[name] = keyboard.KeyCode.from_vk(vk, _scan=scan, _flags=0x0008)
            elif name == "space":
                self.codes[name] = keyboard.Key.space
            else:
                self.codes[name] = keyboard.KeyCode.from_char(name)

    def tap(self, name, hold=0.05):
        self.ctl.check()
        ok, info = focus_ok()
        if not ok:
            raise NoFocus(info)
        if self.dry:
            return
        code = self.codes[name]
        self.kb.press(code)
        time.sleep(hold)
        self.kb.release(code)


# ============================================================================
# Erkennung: Meldung oben
# ============================================================================
def top_text(hsv):
    """('biss' | 'balken' | 'text' | 'leer'). Biss = gelbes SPACE mitten im weißen Text."""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    white = (s <= 40) & (v >= 200)
    yellow = (h >= YELLOW_HUE[0]) & (h <= YELLOW_HUE[1]) & (s >= 90) & (v >= 170)
    if white.sum() < 0.002 * white.size:
        return "leer", None
    # gelbes Wort = breite, flache Fläche (keine einzelnen Symbole wie das ▲ im Fenster)
    closed = cv2.morphologyEx(yellow.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 9), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(closed)
    words = [st[i] for i in range(1, n) if st[i, 2] >= 2.5 * st[i, 3] and st[i, 3] >= 6
             and st[i, 4] >= 40]
    if not words:
        return "text", None
    x, y, w, hh, _ = max(words, key=lambda c: c[4])
    rows = white[max(0, y - hh):y + 2 * hh]                  # weißer Text in derselben Zeile
    cols = np.nonzero(rows.any(axis=0))[0]
    if len(cols) < 2:
        return "text", None
    rel = (x + w / 2 - cols.min()) / max(1, cols.max() - cols.min())
    return ("biss" if rel >= BITE_MIN_REL else "balken"), rel


# ============================================================================
# Erkennung: Balken
# ============================================================================
def blue_mask(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (h >= BLUE_HUE[0]) & (h <= BLUE_HUE[1]) & (s >= BLUE_MIN_SAT) & (v >= BLUE_MIN_VAL)


def white_mask(hsv):
    return (hsv[..., 1] <= WHITE_MAX_SAT) & (hsv[..., 2] >= WHITE_MIN_VAL)


def red_mask(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h <= 10) | (h >= 160)) & (s >= 40) & (v >= 110)


def dark_bar_mask(hsv):
    """Leerer (noch nicht gefüllter) Teil des Balkens: dunkelgrau."""
    return (hsv[..., 1] <= 80) & (hsv[..., 2] >= 30) & (hsv[..., 2] <= 95)


def find_bar(hsv):
    """Sucht den Balken: flache rote (Gefahrenbereich) oder blaue (Balken) Fläche mit der weißen
    Grenz-Markierung in derselben Höhe. Ergebnis: (y1, y2, x1, x2) - oder None."""
    mask = (red_mask(hsv) | blue_mask(hsv)).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(mask)
    best = None
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if h < 6 or w < 2 * h or area < 0.45 * w * h:     # flaches, gefülltes Rechteck
            continue
        y1, y2 = y + int(0.15 * h), y + h - int(0.15 * h)
        x1, x2 = max(0, x - 25 * h), min(hsv.shape[1], x + w + 25 * h)
        band = hsv[y1:y2, x1:x2]
        if not (white_mask(band).mean(axis=0) > 0.6).any():
            continue
        if best is None or area > best[0]:
            best = (area, (y1, y2, x1, x2))
    return best[1] if best else None


def red_zone_mask(hsv):
    """Roter Bereich links der Markierung (rot oder rosa schraffiert)."""
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h <= 12) | (h >= 120)) & (s >= 15) & (v >= 90)


def read_bar(band_hsv):
    """(Markierung, Balkenende, 100 %-Ende, 0 %-Anfang) im Balken-Ausschnitt, jeweils x oder None.
    Markierung = weiße Grenzlinie (steht still), Balkenende = rechtes Ende der blauen Füllung
    hinter der Markierung, 100 %-Ende = Ende des grauen Leer-Bereichs, 0 %-Anfang = linkes Ende
    des roten Bereichs."""
    white = white_mask(band_hsv).mean(axis=0) > 0.6
    if not white.any():
        return None, None, None, None
    cols = np.nonzero(white)[0]
    # mehrere weiße Spalten: die zusammenhängende Gruppe mit den meisten Spalten
    groups = np.split(cols, np.nonzero(np.diff(cols) > 2)[0] + 1)
    grp = max(groups, key=len)
    marker = float(grp.mean())
    blue = blue_mask(band_hsv).mean(axis=0) > 0.5
    dark = dark_bar_mask(band_hsv).mean(axis=0) > 0.6
    # vom Marker nach rechts laufen, solange Balken (blau, grau oder weiß) - Lücken bis 3 px
    x, last_blue, last_bar, gap = int(grp.max()) + 1, None, None, 0
    while x < band_hsv.shape[1] and gap <= 3:
        if blue[x]:
            last_blue = last_bar = x
            gap = 0
        elif dark[x] or white[x]:
            last_bar = x
            gap = 0
        else:
            gap += 1
        x += 1
    fill = float(last_blue) if last_blue is not None else None
    red = red_zone_mask(band_hsv).mean(axis=0) > 0.5
    x, first, gap = int(grp.min()) - 1, None, 0
    while x >= 0 and gap <= 3:
        if red[x]:
            first, gap = x, 0
        else:
            gap += 1
        x -= 1
    return (marker, fill, (float(last_bar) if last_bar is not None else None),
            (float(first) if first is not None else None))

# ============================================================================
# Erkennung: Buchstaben-Kästchen
# ============================================================================
LETTER_OF_ARROW = {"up": "w", "left": "a", "down": "s", "right": "d"}
_letter_templates = {}


def letter_templates(size):
    if size not in _letter_templates:
        w, h = size
        out = {}
        for ch in "WASD":
            img = np.zeros((80, 80), np.uint8)
            cv2.putText(img, ch, (8, 68), cv2.FONT_HERSHEY_SIMPLEX, 2.4, 255, 6, cv2.LINE_AA)
            ys, xs = np.nonzero(img > 100)
            crop = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            out[ch.lower()] = cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA) > 100
        _letter_templates[size] = out
    return _letter_templates[size]


def find_cells(hsv):
    """Reihe gleich großer, dunkelgrauer Kästchen. Liste von (x, y, w, h), links nach rechts."""
    s, v = hsv[..., 1], hsv[..., 2]
    dark = ((s <= CELL_MAX_SAT) & (v >= CELL_VAL[0]) & (v <= CELL_VAL[1])).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(dark, connectivity=4)
    cand = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if w < CELL_MIN_W or not CELL_ASPECT[0] <= h / w <= CELL_ASPECT[1]:
            continue
        if area < 0.6 * w * h:
            continue
        cand.append((x, y, w, h))
    best = []
    for x, y, w, h in cand:                                # Reihe um jedes Kästchen sammeln
        row = sorted(c for c in cand if abs(c[1] - y) <= 0.15 * h and abs(c[3] - h) <= 0.15 * h
                     and abs(c[2] - w) <= 0.2 * w)
        chain = [row[0]] if row else []
        for c in row[1:]:
            gap = c[0] - (chain[-1][0] + chain[-1][2])
            if -2 <= gap <= 0.4 * w:
                chain.append(c)
            elif len(chain) < 4:
                chain = [c]
            else:
                break
        if len(chain) > len(best):
            best = chain
    return best if len(best) >= 4 else []


def read_cell(cell_hsv):
    """Buchstabe eines Kästchens: 'w'/'a'/'s'/'d', '' = leer, '?' = unklar. Plus Details."""
    h, w = cell_hsv.shape[:2]
    mx, my = max(2, int(0.12 * w)), max(2, int(0.06 * h))
    inner = cell_hsv[my:h - my, mx:w - mx]
    s, v = inner[..., 1], inner[..., 2]
    bg = float(np.median(v))
    fg = (((s >= 80) & (v >= 90)) | (v >= bg + 45) | (v <= bg - 35)).astype(np.uint8)
    if fg.sum() < 0.02 * fg.size:
        return "", "leer"
    n, _, st, cen = cv2.connectedComponentsWithStats(fg)
    blobs = [(st[i], cen[i]) for i in range(1, n) if st[i, 4] >= 0.004 * fg.size]
    if not blobs:
        return "", "leer"
    ih = inner.shape[0]
    # Pfeil = unterster kompakter Fleck, Buchstabe = alles darüber
    arrow = max(blobs, key=lambda b: b[1][1])
    arrow_key, arrow_score = None, 0.0
    if arrow[1][1] > 0.45 * ih:
        x, y, bw, bh, _ = arrow[0]
        dx = (arrow[1][0] - (x + (bw - 1) / 2)) / max(1, bw)
        dy = (arrow[1][1] - (y + (bh - 1) / 2)) / max(1, bh)
        if abs(dy) >= abs(dx):
            arrow_key = "w" if dy > 0 else "s"          # ▲ Spitze oben: Schwerpunkt unten
        else:
            arrow_key = "a" if dx > 0 else "d"          # ◄ Spitze links: Schwerpunkt rechts
        arrow_score = max(abs(dx), abs(dy))
    letter_key = None
    letter_px = [b for b in blobs if b is not arrow or arrow_key is None]
    if letter_px:
        x1 = min(b[0][0] for b in letter_px)
        y1 = min(b[0][1] for b in letter_px)
        x2 = max(b[0][0] + b[0][2] for b in letter_px)
        y2 = max(b[0][1] + b[0][3] for b in letter_px)
        if x2 - x1 >= 3 and y2 - y1 >= 5:
            glyph = fg[y1:y2, x1:x2] > 0
            tpl = letter_templates((x2 - x1, y2 - y1))
            scores = {k: (glyph & t).sum() / max(1, (glyph | t).sum()) for k, t in tpl.items()}
            letter_key = max(scores, key=scores.get)
    if arrow_key and arrow_score >= 0.06:
        return arrow_key, f"Pfeil {arrow_key.upper()}" + (f", Buchstabe {letter_key.upper()}"
                                                           if letter_key else "")
    if letter_key:
        return letter_key, f"Buchstabe {letter_key.upper()} (Pfeil unklar)"
    return "?", "unklar"


def read_qte(hsv):
    """Liste der Tasten (von links), None wenn keine Kästchenreihe zu sehen ist."""
    cells = find_cells(hsv)
    if not cells:
        return None, []
    keys, info = [], []
    for x, y, w, h in cells:
        k, why = read_cell(hsv[y:y + h, x:x + w])
        info.append(why)
        if k == "":
            break
        keys.append(k)
    return keys, cells


# ============================================================================
# Bot
# ============================================================================
class Bot:
    def __init__(self, debug=False, dry=False):
        self.debug_on = debug
        self.dry = dry
        self.ctl = Control()
        self.screen = Screen()
        self.keys = Keys(self.ctl, dry=dry)
        self.top_rect = self.screen.rect(TOP_AREA)
        self.game_rect = self.screen.rect(GAME_AREA)
        self.last_bite = 0.0
        self.last_activity = time.time()
        self.qte_done_at = 0.0
        self.latency = PRESS_LATENCY
        try:
            with open(CALIB_FILE, encoding="utf-8") as f:
                self.latency = float(json.load(f)["latency"])
            log(f"Gelernte Reaktionszeit geladen: {self.latency * 1000:.0f} ms")
        except Exception:
            pass

    def save_debug(self, name, img):
        if not self.debug_on or img is None:
            return
        folder = os.path.join(HERE, "debug_fischen")
        os.makedirs(folder, exist_ok=True)
        cv2.imwrite(os.path.join(folder, f"{time.strftime('%H%M%S')}_{name}.png"), img)

    # ------------------------------------------------------------------ bar
    def play_bar(self, game_img, bar):
        """Weiße Markierung = Grenze (steht still). Blauer Balken läuft darüber hinaus bis 100 %
        und wieder zurück. LEERTASTE, wenn der Balken (vorausberechnet) gut im blauen Bereich ist."""
        y1, y2, x1, x2 = bar
        gx, gy = self.game_rect[:2]
        rect = (gx + x1, gy + y1, x2 - x1, y2 - y1)
        log("Balken-Spiel erkannt - warte, bis der Balken über die Markierung läuft.")
        self.save_debug("balken_start", game_img)
        marker, end = None, None
        last, vel, dt = None, 0.0, 0.02
        speed = None                    # gemerkte Balken-Geschwindigkeit (px/s)
        turns = 0                       # wie oft der Balken schon bei 100 % umgedreht hat
        start, span = None, None        # 0 %-Ende links, Breite des blauen Bereichs
        t_press = None                  # vorausberechneter Druckzeitpunkt (sehr schneller Balken)
        t0 = time.time()
        t_log = 0.0
        missing = 0
        while time.time() - t0 < BAR_TIMEOUT:
            self.ctl.check()
            ta = time.time()
            band = cv2.cvtColor(self.screen.grab(rect), cv2.COLOR_BGR2HSV)
            now = (ta + time.time()) / 2   # Aufnahmezeitpunkt ~ Mitte des Abgreifens
            m, fill, bar_end, bar_start = read_bar(band)
            if m is None:
                missing += 1
                if missing >= 15:
                    log("Balken verschwunden.")
                    return
                continue
            missing = 0
            marker = m if marker is None else 0.8 * marker + 0.2 * m
            if bar_end is not None:
                end = bar_end if end is None else max(end, bar_end)
            if bar_start is not None:
                start = bar_start if start is None else min(start, bar_start)
            if self.debug_on and now - t_log > 0.25:
                t_log = now
                log(f"  [Balken] Markierung x={marker:.0f}  Balken bis "
                    f"{'-' if fill is None else f'{fill:.0f}'}  100 % bei {'-' if end is None else f'{end:.0f}'}")
            if fill is None or end is None or end - marker < 5:
                # Balken im roten Bereich. Ist er gerade dort hinein zurückgelaufen und ist er
                # zu schnell zum Nachschauen, wird der nächste Durchgang vorausberechnet:
                # bis 0 % und zurück zur Markierung, dann bis zur Mitte des blauen Bereichs.
                if last is not None and vel < 0 and speed and start is not None and span:
                    t_exit = last[0] + (last[1] - marker) / speed
                    fast = (1 - BAR_PRESS_FROM - BAR_PRESS_END) * span / speed < 3 * dt
                    if fast:
                        t_press = (t_exit + 2 * (marker - start) / speed
                                   + 0.5 * span / speed - self.latency)
                last, vel = None, 0.0
                if t_press is not None and time.time() >= t_press - dt / 2:
                    wait = t_press - time.time()
                    if wait > 0:
                        time.sleep(wait)
                    self.keys.tap("space", hold=0.03)
                    log("  LEERTASTE vorausberechnet (sehr schneller Balken).")
                    self.last_activity = time.time()
                    self.learn_latency(rect, marker + 0.5 * span, speed, marker, span)
                    self.save_debug("balken_gedrueckt", self.screen.grab(self.game_rect))
                    return
                continue
            t_press = None
            if last is None:
                # Balken kommt gerade aus dem roten Bereich -> er wächst
                vel = speed or 0.0
            elif now > last[0]:
                dt = 0.7 * dt + 0.3 * (now - last[0])
                v = (fill - last[1]) / (now - last[0])
                if abs(v) > 1:
                    turned = v * vel < 0
                    if turned and vel > 0:
                        turns += 1             # Umkehr bei 100 %
                    if not turned:             # über eine Umkehr gemessen wäre das Tempo zu klein
                        speed = abs(v) if speed is None else 0.7 * speed + 0.3 * abs(v)
                    # Richtung aus der Messung, Tempo aus dem Mittel (stabiler)
                    vel = float(np.copysign(speed if speed else abs(v), v))
            last = (now, fill)
            if vel == 0:
                continue
            span = end - marker
            if speed and (1 - BAR_PRESS_FROM - BAR_PRESS_END) * span / speed < 3 * dt and start is not None:
                continue                       # zu schnell zum Nachschauen -> vorausberechnen (s. o.)
            lo = marker + BAR_PRESS_FROM * span
            hi = end - BAR_PRESS_END * span
            # wo ist der Balken, wenn das Spiel den Tastendruck verarbeitet?
            ahead = fill + vel * (time.time() - now + self.latency)
            # beim Wachsen drücken; erst nach 2 Umkehrungen (Zeit wird knapp) auch beim Zurücklaufen
            if lo <= ahead <= hi and (vel > 0 or turns >= 2):
                self.keys.tap("space", hold=0.03)
                log(f"  LEERTASTE - Balken bei {(ahead - marker) / span * 100:.0f} % des blauen Bereichs.")
                self.last_activity = time.time()
                self.learn_latency(rect, ahead, vel, marker, span)
                self.save_debug("balken_gedrueckt", self.screen.grab(self.game_rect))
                return
        log("Balken-Spiel: Zeit abgelaufen.")

    def learn_latency(self, rect, ahead, vel, marker, span):
        """Wo ist der Balken stehen geblieben? Daraus die Reaktionszeit des Spiels nachlernen."""
        stops = []
        for _ in range(3):
            self.ctl.sleep(0.12)
            m, f, _, _ = read_bar(cv2.cvtColor(self.screen.grab(rect), cv2.COLOR_BGR2HSV))
            if m is None:
                return                              # Balken weg -> nichts zu lernen
            stops.append(marker - 0.5 * span if f is None else f)   # kein Blau = im Roten
        if max(stops) - min(stops) > 2:
            return                                  # Balken läuft weiter -> nichts lernen
        stop = stops[-1]
        pct = (stop - marker) / span * 100
        log(f"  Balken steht bei {pct:.0f} % des blauen Bereichs" + (" - TREFFER" if pct > 0 else " - im Roten!"))
        if abs(vel) < 50:
            return
        if stop < marker:
            step = 0.02                              # schon umgedreht und im Roten -> Spiel reagiert später
        else:
            err = (stop - ahead) / vel               # > 0: Spiel reagiert später als gedacht
            step = float(np.clip(0.6 * err, -0.02, 0.02))  # pro Runde höchstens 20 ms nachstellen
        new = float(np.clip(self.latency + step, 0.0, 0.25))
        if abs(new - self.latency) >= 0.003:
            self.latency = new
            log(f"  Reaktionszeit nachgelernt: {self.latency * 1000:.0f} ms")
            try:
                with open(CALIB_FILE, "w", encoding="utf-8") as f:
                    json.dump({"latency": round(self.latency, 4)}, f)
            except Exception:
                pass

    # ------------------------------------------------------------------ qte
    def play_qte(self, game_img):
        # Reihe zweimal gleich lesen, bevor getippt wird
        seq, prev = None, None
        for _ in range(6):
            hsv = cv2.cvtColor(self.screen.grab(self.game_rect), cv2.COLOR_BGR2HSV)
            keys, _ = read_qte(hsv)
            if keys and keys == prev:
                seq = keys
                break
            prev = keys
            self.ctl.sleep(0.04)
        if not seq:
            return False
        if "?" in seq:
            log("  Achtung: nicht alle Buchstaben sicher erkannt: " + " ".join(k.upper() for k in seq))
            self.save_debug("buchstaben_unklar", game_img)
            seq = [k for k in seq if k != "?"]
        log("Buchstaben-Spiel: " + " ".join(k.upper() for k in seq))
        self.save_debug("buchstaben", game_img)
        for k in seq:
            self.keys.tap(k, hold=QTE_KEY_HOLD)
            self.ctl.sleep(QTE_GAP)
        self.qte_done_at = time.time()
        self.last_activity = time.time()
        self.ctl.sleep(AFTER_QTE)
        for i in range(R_PRESSES):                  # R (pynput) - mehrmals, falls einer verschluckt wird
            if i:
                self.ctl.sleep(R_GAP)
            self.keys.tap("r", hold=R_HOLD)
            log(f"  R gedrückt (Fisch aufheben) {i + 1}/{R_PRESSES}.")
        self.ctl.sleep(AFTER_R)
        self.keys.tap("space")
        log("  LEERTASTE - neu ausgeworfen.")
        self.last_activity = time.time()
        return True

    # ------------------------------------------------------------------ loop
    def run(self):
        log("Fischen-Bot gestartet.  F9 = Pause/Weiter, F10 = Beenden.")
        if self.dry:
            log("PROBE-MODUS: es werden keine Tasten gedrückt.")
        log("Klicke jetzt ins Spielfenster und wirf die Angel aus.")
        last_state = None
        bite_frames = 0
        while not self.ctl.quit:
            if self.ctl.paused:
                time.sleep(0.2)
                continue
            try:
                game = self.screen.grab(self.game_rect)
                ghsv = cv2.cvtColor(game, cv2.COLOR_BGR2HSV)

                keys, _ = read_qte(ghsv)
                if keys and time.time() - self.qte_done_at > 3.0:
                    if self.play_qte(game):
                        last_state = None
                        continue

                bar = find_bar(ghsv)
                if bar is not None:
                    self.play_bar(game, bar)
                    last_state = None
                    continue

                top = cv2.cvtColor(self.screen.grab(self.top_rect), cv2.COLOR_BGR2HSV)
                state, _ = top_text(top)
                if state != last_state:
                    if state == "text":
                        log("Warte auf einen Biss ...")
                    last_state = state
                if state != "leer":
                    self.last_activity = time.time()

                # Biss: dreimal hintereinander erkannt und kein Balken -> LEERTASTE
                bite_frames = bite_frames + 1 if state == "biss" else 0
                if bite_frames >= 3 and time.time() - self.last_bite > BITE_COOLDOWN:
                    log("Biss! LEERTASTE.")
                    self.keys.tap("space")
                    self.last_bite = time.time()
                    bite_frames = 0
                    continue

                if (AUTO_RECAST and state == "leer"
                        and time.time() - self.last_activity > RECAST_AFTER):
                    log(f"Seit {RECAST_AFTER:.0f} s keine Meldung - werfe neu aus (LEERTASTE).")
                    self.keys.tap("space")
                    self.last_activity = time.time()
                time.sleep(0.03)
            except NoFocus as e:
                log(f"Spielfenster nicht im Vordergrund {e} - keine Tasten gesendet. Warte ...")
                time.sleep(2.0)
            except Abort:
                if self.ctl.quit:
                    break
        log("Beendet.")


# ============================================================================
# Testmodus
# ============================================================================
def run_test(path):
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"Bild nicht lesbar: {path}")
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    top = hsv[:max(20, int(0.15 * hsv.shape[0]))]
    state, rel = top_text(top)
    print(f"Meldung oben: {state}" + (f"  (SPACE bei {rel:.2f} der Textbreite)" if rel is not None else ""))
    out = img.copy()
    bar = find_bar(hsv)
    if bar:
        y1, y2, x1, x2 = bar
        marker, fill, end, start = read_bar(hsv[y1:y2, x1:x2])
        fmt = lambda v: "-" if v is None else f"{v + x1:.0f}"
        print(f"Balken: Zeilen {y1}-{y2}, Markierung x={fmt(marker)}, blauer Balken bis x={fmt(fill)}, "
              f"100 % bei x={fmt(end)}, 0 % bei x={fmt(start)}")
        if marker is not None:
            cv2.line(out, (int(x1 + marker), y1 - 6), (int(x1 + marker), y2 + 6), (0, 0, 255), 2)
        if fill is not None:
            cv2.line(out, (int(x1 + fill), y1 - 6), (int(x1 + fill), y2 + 6), (255, 255, 0), 2)
        if end is not None:
            cv2.line(out, (int(x1 + end), y1 - 6), (int(x1 + end), y2 + 6), (0, 255, 0), 2)
    else:
        print("Balken: keiner")
    keys, cells = read_qte(hsv)
    if cells:
        print(f"Buchstaben-Kästchen: {len(cells)}")
        for i, (x, y, w, h) in enumerate(cells):
            k, why = read_cell(hsv[y:y + h, x:x + w])
            print(f"  {i + 1:2d}: {k.upper() or '-':2s} {why}")
            cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 1)
            cv2.putText(out, k.upper() or "-", (x + 3, y + h + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 0), 1, cv2.LINE_AA)
        print("Tasten:", " ".join(k.upper() for k in keys))
    else:
        print("Buchstaben-Kästchen: keine")
    p = os.path.join(HERE, "fischen_test.png")
    cv2.imwrite(p, out)
    print("Markiertes Bild gespeichert:", p)


def main():
    ap = argparse.ArgumentParser(description="Fischen-Bot")
    ap.add_argument("--dry", action="store_true", help="nur erkennen, keine Tasten drücken")
    ap.add_argument("--debug", action="store_true", help="Bilder in ./debug_fischen speichern")
    ap.add_argument("--test", metavar="BILD", help="Erkennung an einem Screenshot testen")
    args = ap.parse_args()
    if args.test:
        run_test(args.test)
    else:
        Bot(debug=args.debug, dry=args.dry).run()


if __name__ == "__main__":
    main()
