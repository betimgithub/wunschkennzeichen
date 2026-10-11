#!/usr/bin/env python3
"""
Fischen-Bot - spielt die Angel-Minispiele automatisch.

Ablauf
  1. "You are currently fishing ..."            -> warten.
  2. "You got a bite. Press SPACE ..."          -> LEERTASTE.
  3. Balken-Spiel ("Press SPACE before the bar fluctuates 3 times")
       Die Markierung läuft über den Balken hin und her. Der Bot merkt sich die blaue Zone
       und drückt LEERTASTE, sobald die Markierung (vorausberechnet) in der blauen Zone ist.
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

# Balken: blaue Zielzone, weiße Markierung
BLUE_HUE = (92, 114)
BLUE_MIN_SAT, BLUE_MIN_VAL = 100, 140
WHITE_MAX_SAT, WHITE_MIN_VAL = 45, 225
ZONE_MARGIN = 0.15       # so viel (Anteil der Zonenbreite) wird an beiden Rändern weggelassen
PRESS_LATENCY = 0.045    # Sekunden von "Taste drücken" bis das Spiel sie verarbeitet (Vorhalt)
BAR_TIMEOUT = 12.0       # länger dauert das Balken-Spiel nie

# Buchstaben-Kästchen: dunkelgrau, hochkant, in einer Reihe
CELL_MAX_SAT, CELL_VAL = 70, (35, 72)
CELL_ASPECT = (1.2, 2.3)                     # Höhe / Breite
CELL_MIN_W = 14
QTE_KEY_HOLD = 0.05
QTE_GAP = 0.10           # Pause zwischen zwei Buchstaben

AFTER_QTE = 1.5          # nach dem Buchstaben-Spiel so lange warten, dann R
AFTER_R = 1.0            # nach R so lange warten, dann LEERTASTE (neu auswerfen)
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


def find_bar(hsv):
    """Sucht die blaue Zone mit rotem Balkenteil bzw. weißer Markierung daneben.
    Ergebnis: (y1, y2, x1, x2) = Zeilen des Balkens und Suchbereich in x - oder None."""
    blue = blue_mask(hsv).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(blue)
    best = None
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if h < 6 or w < 0.8 * h or area < 0.6 * w * h:      # flaches, gefülltes Rechteck
            continue
        y1, y2 = y + int(0.15 * h), y + h - int(0.15 * h)
        x1, x2 = max(0, x - 20 * h), min(hsv.shape[1], x + w + 20 * h)
        band = hsv[y1:y2, x1:x2]
        red = red_mask(band).mean(axis=0) > 0.5
        marker = (white_mask(band).mean(axis=0) > 0.6).any()
        if red.sum() < 2 * h and not marker:
            continue
        if best is None or area > best[0]:
            best = (area, (y1, y2, x1, x2))
    return best[1] if best else None


def read_bar(band_hsv):
    """Blaue Spalten (Zone) und Position der weißen Markierung im Balken-Ausschnitt."""
    blue_cols = np.nonzero(blue_mask(band_hsv).mean(axis=0) > 0.5)[0]
    white = white_mask(band_hsv).mean(axis=0)
    marker = None
    if white.max() > 0.6:
        cols = np.nonzero(white > 0.6)[0]
        marker = float(cols.mean())
    zone = (int(blue_cols.min()), int(blue_cols.max())) if len(blue_cols) else None
    return zone, marker


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
        y1, y2, x1, x2 = bar
        gx, gy = self.game_rect[:2]
        rect = (gx + x1, gy + y1, x2 - x1, y2 - y1)
        log("Balken-Spiel erkannt - warte auf die blaue Zone.")
        self.save_debug("balken_start", game_img)
        zone = None
        last = None                     # (Zeit, Markierung)
        vel, samples = 0.0, 0
        dt = 0.02                       # gemessene Zeit pro Bild
        t0 = time.time()
        missing = 0
        while time.time() - t0 < BAR_TIMEOUT:
            self.ctl.check()
            ta = time.time()
            band = cv2.cvtColor(self.screen.grab(rect), cv2.COLOR_BGR2HSV)
            now = (ta + time.time()) / 2   # Aufnahmezeitpunkt ~ Mitte des Abgreifens
            z, marker = read_bar(band)
            if z is None and marker is None:
                missing += 1
                if missing >= 15:
                    log("Balken verschwunden.")
                    return
                continue
            missing = 0
            if z is not None:           # Zone über alle Bilder vereinen (Markierung kann sie verdecken)
                zone = z if zone is None else (min(zone[0], z[0]), max(zone[1], z[1]))
            if marker is None or zone is None:
                continue
            if last is not None and now > last[0]:
                dt = 0.7 * dt + 0.3 * (now - last[0])
                v = (marker - last[1]) / (now - last[0])
                # Richtungswechsel (Umkehr am Balkenende): alte Geschwindigkeit verwerfen
                vel = v if samples == 0 or v * vel <= 0 else 0.5 * vel + 0.5 * v
                samples += 1
            last = (now, marker)
            width = zone[1] - zone[0]
            lo, hi = zone[0] + ZONE_MARGIN * width, zone[1] - ZONE_MARGIN * width
            # wo ist die Markierung, wenn das Spiel den Tastendruck verarbeitet?
            ahead = marker + vel * (time.time() - now + self.latency)
            # Ziel = Zonenmitte: drücken im Bild, das ihr am nächsten kommt (nächstes Bild wäre zu spät)
            to_center = ((zone[0] + zone[1]) / 2 - ahead) * (1 if vel >= 0 else -1)
            if samples >= 2 and lo <= ahead <= hi and to_center <= abs(vel) * dt / 2:
                self.keys.tap("space", hold=0.03)
                log("  LEERTASTE bei der blauen Zone.")
                self.last_activity = time.time()
                self.learn_latency(rect, ahead, vel, zone)
                self.save_debug("balken_gedrueckt", self.screen.grab(self.game_rect))
                return
        log("Balken-Spiel: Zeit abgelaufen.")

    def learn_latency(self, rect, ahead, vel, zone):
        """Wo ist der Balken stehen geblieben? Daraus die Reaktionszeit des Spiels nachlernen."""
        stops = []
        for _ in range(3):
            self.ctl.sleep(0.12)
            _, m = read_bar(cv2.cvtColor(self.screen.grab(rect), cv2.COLOR_BGR2HSV))
            stops.append(m)
        if None in stops or max(stops) - min(stops) > 2 or abs(vel) < 50:
            return                                  # Balken weg oder läuft weiter -> nichts lernen
        stop = stops[-1]
        inside = zone[0] <= stop <= zone[1]
        pct = (stop - zone[0]) / max(1, zone[1] - zone[0]) * 100
        log(f"  Balken steht bei {pct:.0f} % der blauen Zone " + ("- TREFFER" if inside else "- daneben"))
        err = (stop - ahead) / vel                   # > 0: Spiel reagiert später als gedacht
        new = float(np.clip(self.latency + 0.6 * err, 0.0, 0.25))
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
        self.keys.tap("r")
        log("  R gedrückt (Fisch aufheben).")
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
        zone, marker = read_bar(hsv[y1:y2, x1:x2])
        print(f"Balken: Zeilen {y1}-{y2}, blaue Zone x={zone[0] + x1}-{zone[1] + x1}" if zone else "Balken: keine Zone",
              f", Markierung x={marker + x1:.0f}" if marker is not None else ", keine Markierung")
        if zone:
            cv2.rectangle(out, (x1 + zone[0], y1), (x1 + zone[1], y2), (255, 255, 0), 2)
        if marker is not None:
            cv2.line(out, (int(x1 + marker), y1 - 6), (int(x1 + marker), y2 + 6), (0, 0, 255), 2)
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
