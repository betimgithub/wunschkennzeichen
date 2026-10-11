#!/usr/bin/env python3
"""
Bergbau-Bot - löst das Bergbau-Minispiel (Felsen mit roten Schwachpunkten) automatisch.

Ablauf pro Runde
  1. Die Spitzhacke (orangefarbener Stiel) und die roten Punkte werden per Farbe gefunden.
     Alle Größen werden relativ zur Stiel-Länge gerechnet, die Auflösung ist also egal.
  2. Der Bot fährt die Spitzhacke mit W/A/S/D zum nächstgelegenen roten Punkt
     (geregelt: drücken, nachmessen, nachkorrigieren).
  3. LEERTASTE:
       - Punkt verschwindet  -> falscher Punkt, weiter zum nächstgelegenen.
       - Punkt bleibt + Riss  -> richtiger Punkt: noch 6x LEERTASTE (insgesamt 7).
       - nichts passiert      -> knapp daneben, leicht versetzt nochmal versuchen.
  4. Fels bricht -> gewonnen. Der Bot wartet auf die nächste Runde.

Wo die Hacke "trifft" (Trefferpunkt relativ zum Stiel), wird bei jedem erfolgreichen Schlag
nachgelernt. Falls es trotzdem nicht klappt: Hacke von Hand genau auf einen Punkt stellen und
F8 drücken - der Versatz wird in bergbau_kalibrierung.json gespeichert.

Hotkeys:  F8 = Kalibrieren   F9 = Pause/Weiter   F10 = Beenden

Start:    python bergbau_bot.py            (danach ins Spielfenster klicken)
Probe:    python bergbau_bot.py --dry      (erkennt alles, drückt aber keine Tasten)
Test:     python bergbau_bot.py --test screenshot.png   (Erkennung an einem Bild prüfen)
Debug:    python bergbau_bot.py --debug    (speichert Bilder in ./debug)

Benötigt: pip install mss numpy opencv-python pynput
"""

import argparse
import ctypes
import json
import math
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
MONITOR = 1                      # 1 = Hauptmonitor
SEARCH_AREA = (0.10, 0.05, 0.90, 0.95)   # Suchbereich (links, oben, rechts, unten), relativ

# Stiel der Spitzhacke: orange (OpenCV-Farbton 0-180), lang und schräg (~60 Grad nach unten rechts)
HANDLE_HUE = (7, 20)
HANDLE_MIN_SAT, HANDLE_MIN_VAL = 110, 80
HANDLE_MIN_PIXELS = 80
HANDLE_MIN_RATIO = 15.0          # länglich: Verhältnis Länge²/Breite²
HANDLE_ANGLE = (35.0, 85.0)      # Neigung des Stiels in Grad (gemessen: 60)

# Rote Punkte: knallrot, rund, Durchmesser ca. 0,2 Stiel-Längen
DOT_MIN_SAT, DOT_MIN_VAL = 140, 100
DOT_AREA = (0.008, 0.08)         # Fläche relativ zu Stiel-Länge²  (gemessen: 0,027)
DOT_MIN_FILL = 0.55              # Anteil der Bounding-Box, der rot sein muss (rund)

# Trefferpunkt relativ zum oberen Stiel-Ende, in Stiel-Längen (aus dem Screenshot mit Riss)
HIT_OFFSET = (-0.54, 0.31)
AIM_TOL = 0.07                   # so nah (in Stiel-Längen) muss der Trefferpunkt am Punkt sein
NUDGE = 0.12                     # Versatz für Ausweich-Versuche, wenn ein Schlag nichts bewirkt
NUDGES = [(0, 0)] + [(NUDGE * dx, NUDGE * dy) for dx, dy in
                     ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))]

HITS_TO_WIN = 7                  # richtiger Punkt: so oft schlagen, dann bricht der Fels
MAX_EXTRA_HITS = 3               # falls der Fels danach noch nicht gebrochen ist
CRACK_DARK_VAL = 55              # Riss = sehr dunkle Pixel
CRACK_MIN_GAIN = 0.04            # so viel mehr dunkle Fläche um den Punkt = Riss entstanden
CRACK_CHANGE = 0.08              # oder: so viel Fläche um den Punkt hat sich deutlich verändert

KEY_HOLD_MIN, KEY_HOLD_MAX = 0.03, 0.35   # Tastendruck-Dauer beim Bewegen (Sekunden)
START_SPEED = 300.0              # anfängliche Schätzung: Pixel pro Sekunde Tastendruck
MOVE_SETTLE = 0.08               # Pause nach dem Loslassen, bevor nachgemessen wird
MOVE_MAX_STEPS = 60              # Sicherheitsgrenze pro Anfahrt
HIT_WAIT = 0.6                   # so lange nach LEERTASTE warten (Schlag-Animation)
HIT_DELAY = 0.25                 # zusätzliche Pause zwischen Schlägen auf den richtigen Punkt
WIN_WAIT = 3.0                   # so lange wird nach dem letzten Schlag auf das Brechen gewartet
NEW_ROUND_GAP = 1.0              # so lange müssen Hacke/Punkte weg sein, bevor eine neue Runde zählt

USE_SCANCODES = True             # Scancodes senden (für DirectX-Spiele meist nötig)
FOCUS_CHECK = True               # keine Tasten senden, wenn Konsole/Editor im Vordergrund ist
GAME_WINDOW_TITLE = ""           # optional: Teil des Spiel-Fenstertitels, dann wird darauf geprüft

KEYS = {"w": (0x57, 0x11), "a": (0x41, 0x1E), "s": (0x53, 0x1F), "d": (0x44, 0x20),
        "space": (0x20, 0x39)}
NOT_GAME_EXES = {"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe",
                 "openconsole.exe", "code.exe", "python.exe", "pythonw.exe", "py.exe",
                 "explorer.exe", "claude.exe", "pycharm64.exe", "notepad.exe", "notepad++.exe"}

HERE = os.path.dirname(os.path.abspath(__file__))
CALIB_FILE = os.path.join(HERE, "bergbau_kalibrierung.json")

if sys.platform == "win32":
    try:  # echte Pixel-Koordinaten auch bei Windows-Skalierung (125 %, 150 % ...)
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


class RoundError(Exception):
    """Runde kann nicht sicher fortgesetzt werden."""


class Unreachable(Exception):
    """Die Hacke bewegt sich nicht weiter in diese Richtung (z. B. am Rand)."""


# ============================================================================
# Bildschirm, Tasten, Hotkeys
# ============================================================================
class Screen:
    def __init__(self):
        self.sct = mss.mss()
        mons = self.sct.monitors
        self.monitor = mons[MONITOR] if MONITOR < len(mons) else mons[1]
        l, t, r, b = SEARCH_AREA
        m = self.monitor
        self.left = m["left"] + int(m["width"] * l)
        self.top = m["top"] + int(m["height"] * t)
        self.width = int(m["width"] * (r - l))
        self.height = int(m["height"] * (b - t))

    def grab(self):
        shot = self.sct.grab({"left": self.left, "top": self.top,
                              "width": self.width, "height": self.height})
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3])  # BGRA -> BGR


class Control:
    """F8 = Kalibrieren, F9 = Pause/Weiter, F10 = Beenden."""

    def __init__(self):
        self.paused = False
        self.quit = False
        self.calibrate = False
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.daemon = True
        self.listener.start()

    def _on_press(self, key):
        if key == keyboard.Key.f8:
            self.calibrate = True
        elif key == keyboard.Key.f9:
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
            time.sleep(min(0.01, left))


def foreground_window():
    """(Fenstertitel, exe-Name) des Fensters im Vordergrund."""
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
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
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
                # KEYEVENTF_SCANCODE (0x0008): das Spiel bekommt den Hardware-Scancode
                self.codes[name] = keyboard.KeyCode.from_vk(vk, _scan=scan, _flags=0x0008)
            elif name == "space":
                self.codes[name] = keyboard.Key.space
            else:
                self.codes[name] = keyboard.KeyCode.from_char(name)

    def _focus(self):
        ok, info = focus_ok()
        if not ok:
            raise RoundError(f"Spielfenster hat nicht den Fokus {info} - keine Tasten gesendet")

    def tap(self, name, hold=0.06):
        self.hold({name: hold})

    def hold(self, durations):
        """Mehrere Tasten gleichzeitig drücken, jede so lange wie angegeben (z. B. schräg fahren)."""
        self.ctl.check()
        self._focus()
        if self.dry:
            return
        items = sorted(durations.items(), key=lambda kv: kv[1])
        for name, _ in items:
            self.kb.press(self.codes[name])
        t0 = time.time()
        try:
            for name, dur in items:
                wait = dur - (time.time() - t0)
                if wait > 0:
                    time.sleep(wait)
                self.kb.release(self.codes[name])
        finally:
            for name, _ in items:   # bei Fehlern nie eine Taste hängen lassen
                try:
                    self.kb.release(self.codes[name])
                except Exception:
                    pass


# ============================================================================
# Bilderkennung
# ============================================================================
class Pick:
    """Gefundene Spitzhacke: oberes Stiel-Ende (Anker), Stiel-Länge, Richtung."""

    def __init__(self, top, length, axis):
        self.top = np.array(top, float)
        self.length = float(length)
        self.axis = np.array(axis, float)

    def hit_point(self, offset):
        return self.top + np.array(offset, float) * self.length


def find_pick(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((h >= HANDLE_HUE[0]) & (h <= HANDLE_HUE[1]) & (s >= HANDLE_MIN_SAT)
            & (v >= HANDLE_MIN_VAL)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best = None
    for i in np.argsort(-st[1:, 4])[:6] + 1:          # die größten orangen Flächen prüfen
        if st[i, 4] < HANDLE_MIN_PIXELS:
            break
        x, y, w, hh = st[i, :4]
        ys, xs = np.nonzero(lab[y:y + hh, x:x + w] == i)
        pts = np.stack([xs + x, ys + y], 1).astype(np.float64)
        c = pts.mean(0)
        ev, evec = np.linalg.eigh(np.cov((pts - c).T))
        if ev[0] <= 1e-6 or ev[1] / ev[0] < HANDLE_MIN_RATIO:
            continue
        ax = evec[:, 1]
        if ax[1] < 0:                                   # Achse zeigt nach unten
            ax = -ax
        ang = math.degrees(math.atan2(ax[1], ax[0]))
        if not HANDLE_ANGLE[0] <= ang <= HANDLE_ANGLE[1]:
            continue
        proj = (pts - c) @ ax
        length = proj.max() - proj.min()
        cand = Pick(c + ax * proj.min(), length, ax)
        if best is None or length > best.length:
            best = cand
    return best


def red_mask(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h <= 6) | (h >= 172)) & (s >= DOT_MIN_SAT) & (v >= DOT_MIN_VAL)


def find_dots(hsv, pick):
    """Mittelpunkte der roten Punkte (Größe passend zur Stiel-Länge)."""
    if pick is None:
        return []
    mask = red_mask(hsv).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, st, cen = cv2.connectedComponentsWithStats(mask, connectivity=8)
    L2 = pick.length ** 2
    dots = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if not DOT_AREA[0] * L2 <= area <= DOT_AREA[1] * L2:
            continue
        if area / float(w * h) < DOT_MIN_FILL or max(w, h) > 2.2 * min(w, h):
            continue
        dots.append(np.array(cen[i], float))   # (die kleine rote Kappe am Stiel ist zu klein)
    return dots


def dot_radius(pick):
    return math.sqrt(0.027 / math.pi) * pick.length     # gemessen: Fläche 0,027 L²


def red_fraction(hsv, center, radius):
    """Anteil roter Pixel im Kreis um center."""
    return _disk_mean(red_mask(hsv), center, radius)


def dark_fraction(hsv, center, radius):
    """Anteil sehr dunkler Pixel im Ring um den Punkt (der Punkt selbst zählt nicht mit)."""
    return _disk_mean(hsv[..., 2] < CRACK_DARK_VAL, center, 2.5 * radius, inner=1.2 * radius)


def _disk_mean(mask, center, radius, inner=0.0):
    cx, cy = center
    r = max(2, int(math.ceil(radius)))
    x1, y1 = max(0, int(cx) - r), max(0, int(cy) - r)
    x2, y2 = min(mask.shape[1], int(cx) + r + 1), min(mask.shape[0], int(cy) + r + 1)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    yy, xx = np.mgrid[y1:y2, x1:x2]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    disk = (d2 <= radius ** 2) & (d2 >= inner ** 2)
    return float(mask[y1:y2, x1:x2][disk].mean()) if disk.any() else 0.0


def annotate(img, pick, dots, offset, target=None):
    out = img.copy()
    if pick is not None:
        top = tuple(int(v) for v in pick.top)
        end = tuple(int(v) for v in pick.top + pick.axis * pick.length)
        cv2.line(out, top, end, (255, 255, 0), 2)
        hp = tuple(int(v) for v in pick.hit_point(offset))
        cv2.drawMarker(out, hp, (0, 255, 0), cv2.MARKER_CROSS, 18, 2)
        r = int(dot_radius(pick)) + 3
        for d in dots:
            col = (255, 0, 255) if target is not None and np.allclose(d, target) else (0, 255, 255)
            cv2.circle(out, (int(d[0]), int(d[1])), r, col, 2)
    return out


# ============================================================================
# Kalibrierung (Trefferpunkt relativ zum Stiel)
# ============================================================================
def load_offset():
    try:
        with open(CALIB_FILE, encoding="utf-8") as f:
            data = json.load(f)
        off = (float(data["offset"][0]), float(data["offset"][1]))
        log(f"Kalibrierung geladen: Trefferpunkt {off[0]:+.2f} / {off[1]:+.2f} Stiel-Längen")
        return off
    except FileNotFoundError:
        return HIT_OFFSET
    except Exception as e:
        log(f"Kalibrierung nicht lesbar ({e}) - nehme Standardwert.")
        return HIT_OFFSET


def save_offset(off):
    try:
        with open(CALIB_FILE, "w", encoding="utf-8") as f:
            json.dump({"offset": [round(off[0], 4), round(off[1], 4)]}, f)
    except Exception as e:
        log(f"Kalibrierung konnte nicht gespeichert werden: {e}")


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
        self.offset = load_offset()
        self.speed = {"x": START_SPEED, "y": START_SPEED}   # Pixel pro Sekunde Tastendruck
        self.frame = None
        self.hsv = None

    # ---------------------------------------------------------------- helpers
    def look(self):
        self.frame = self.screen.grab()
        self.hsv = cv2.cvtColor(self.frame, cv2.COLOR_BGR2HSV)
        pick = find_pick(self.hsv)
        return pick, find_dots(self.hsv, pick)

    def save_debug(self, name, pick=None, dots=(), target=None):
        if not self.debug_on or self.frame is None:
            return
        folder = os.path.join(HERE, "debug")
        os.makedirs(folder, exist_ok=True)
        cv2.imwrite(os.path.join(folder, f"{time.strftime('%H%M%S')}_{name}.png"),
                    annotate(self.frame, pick, dots, self.offset, target))

    def learn_offset(self, pick, dot):
        """Ein versetzter Schlag hat getroffen: diesen Versatz ab jetzt verwenden."""
        self.offset = tuple(float(v) for v in (dot - pick.top) / pick.length)
        save_offset(self.offset)
        log(f"  Trefferpunkt nachgelernt: {self.offset[0]:+.2f} / {self.offset[1]:+.2f} Stiel-Längen")

    def handle_calibration(self):
        if not self.ctl.calibrate:
            return
        self.ctl.calibrate = False
        pick, dots = self.look()
        if pick is None or not dots:
            log("F8: Spitzhacke oder roter Punkt nicht gefunden - nicht kalibriert.")
            return
        hp = pick.hit_point(self.offset)
        dot = min(dots, key=lambda d: np.linalg.norm(d - hp))
        self.offset = tuple(float(v) for v in (dot - pick.top) / pick.length)
        save_offset(self.offset)
        log(f"F8: kalibriert - Trefferpunkt {self.offset[0]:+.2f} / {self.offset[1]:+.2f} Stiel-Längen "
            f"(gespeichert in {os.path.basename(CALIB_FILE)}).")

    # --------------------------------------------------------------- movement
    def move_to(self, target, nudge=(0.0, 0.0)):
        """Fährt den Trefferpunkt auf target (geregelt, schräg mit 2 Tasten gleichzeitig)."""
        flips = {"x": 0, "y": 0}
        frozen = 0
        last_sign = {"x": 0, "y": 0}
        last_step = {"x": 0.0, "y": 0.0}
        for _ in range(MOVE_MAX_STEPS):
            pick, _ = self.look()
            if pick is None:
                self.ctl.sleep(0.1)
                pick, _ = self.look()
                if pick is None:
                    raise RoundError("Spitzhacke nicht mehr zu sehen")
            hp = pick.hit_point((self.offset[0] + nudge[0], self.offset[1] + nudge[1]))
            err = np.array(target, float) - hp
            tol = AIM_TOL * pick.length
            done = {}
            for i, axis in enumerate(("x", "y")):
                e = err[i]
                # pendelt die Hacke um das Ziel (feste Schrittweite), gilt der kleinste Rest als ok
                ok = abs(e) <= tol or (flips[axis] >= 2 and abs(e) <= 0.6 * max(last_step[axis], tol))
                done[axis] = ok
            if all(done.values()):
                return pick
            press = {}
            for i, axis in enumerate(("x", "y")):
                if done[axis]:
                    continue
                e = err[i]
                key = ("d" if e > 0 else "a") if axis == "x" else ("s" if e > 0 else "w")
                sign = 1 if e > 0 else -1
                if last_sign[axis] and sign != last_sign[axis]:
                    flips[axis] += 1
                last_sign[axis] = sign
                dur = abs(e) / self.speed[axis] * 0.8
                if flips[axis]:
                    dur *= 0.5 ** flips[axis]
                press[key] = float(np.clip(dur, KEY_HOLD_MIN, KEY_HOLD_MAX))
            before = hp
            self.keys.hold(press)
            self.ctl.sleep(MOVE_SETTLE)
            pick2, _ = self.look()
            if pick2 is None:
                continue
            moved = pick2.hit_point((self.offset[0] + nudge[0], self.offset[1] + nudge[1])) - before
            frozen = frozen + 1 if np.abs(moved).max() < 1.0 else 0
            if frozen >= 4:
                raise Unreachable()
            # Geschwindigkeit pro Achse nachlernen (für den nächsten Tastendruck)
            for i, axis in enumerate(("x", "y")):
                key = [k for k in press if (k in "ad") == (axis == "x")]
                if not key:
                    continue
                d = abs(moved[i])
                last_step[axis] = d
                if d > 1.0:
                    measured = d / press[key[0]]
                    self.speed[axis] = float(np.clip(0.5 * self.speed[axis] + 0.5 * measured, 20, 5000))
        raise RoundError("Ziel nicht erreicht - kommen die W/A/S/D-Tasten im Spiel an?")

    # --------------------------------------------------------------- hitting
    def strike(self, target, pick):
        """Ein Schlag. Ergebnis: 'weg' (falscher Punkt), 'riss' (richtiger Punkt) oder 'nichts'."""
        r = dot_radius(pick)
        red0 = red_fraction(self.hsv, target, r)
        dark0 = dark_fraction(self.hsv, target, r)
        v0 = self.hsv[..., 2].astype(np.int16)
        self.keys.tap("space")
        self.ctl.sleep(HIT_WAIT)
        # warten, bis die Hacke wieder ruhig steht (Schlag-Animation vorbei)
        prev = p = None
        for _ in range(15):
            p, _ = self.look()
            if p is not None and prev is not None and np.linalg.norm(p.top - prev.top) < 0.02 * p.length:
                break
            prev = p
            self.ctl.sleep(0.05)
        if p is None:
            return "gebrochen"                       # Hacke weg = Fels gebrochen / Spiel vorbei
        red1 = red_fraction(self.hsv, target, r)
        dark1 = dark_fraction(self.hsv, target, r)
        # Riss: neben dem Punkt wird es dunkler - oder (auf dunklem Untergrund) sichtbar anders
        changed = np.abs(self.hsv[..., 2].astype(np.int16) - v0) > 40
        moved = _disk_mean(changed, target, 2.5 * r, inner=1.2 * r)
        if dark1 - dark0 >= CRACK_MIN_GAIN or (moved >= CRACK_CHANGE and red1 >= 0.5 * red0):
            return "riss"
        if red1 < 0.35 * max(red0, 0.05):
            return "weg"
        return "nichts"

    # ------------------------------------------------------------------ round
    def play_round(self, pick, dots):
        log(f"Runde erkannt: {len(dots)} rote Punkte, Stiel {pick.length:.0f}px.")
        self.save_debug("1_start", pick, dots)
        if self.dry:
            hp = pick.hit_point(self.offset)
            order = sorted(dots, key=lambda d: np.linalg.norm(d - hp))
            log("[Probe] nächster Punkt: " + ", ".join(f"({d[0]:.0f},{d[1]:.0f})" for d in order[:3]))
            log("[Probe] Es werden keine Tasten gedrückt.")
            return
        ok, info = focus_ok()
        if not ok:
            raise RoundError(f"Spielfenster ist nicht im Vordergrund {info} - ins Spiel klicken.")

        known = list(dots)     # alle Punkte merken - die Hacke kann einzelne kurz verdecken
        gone = []              # Punkte, die beim Schlag verschwunden sind (falsch)
        while True:
            pick, seen = self.look()
            if pick is None:
                raise RoundError("Spitzhacke nicht mehr zu sehen")
            near = 0.15 * pick.length
            for d in seen:
                match = [i for i, k in enumerate(known) if np.linalg.norm(d - k) <= near]
                if match:
                    known[match[0]] = d          # Lage auffrischen
                else:
                    known.append(d)
            dots = [d for d in known if all(np.linalg.norm(d - g) > near for g in gone)]
            if not dots:
                raise RoundError("keine roten Punkte mehr übrig, aber der Fels ist nicht gebrochen")
            hp = pick.hit_point(self.offset)
            target = min(dots, key=lambda d: np.linalg.norm(d - hp))
            log(f"Fahre zum nächsten Punkt ({target[0]:.0f},{target[1]:.0f}) - noch {len(dots)} übrig.")

            result = "nichts"
            try:
                for nudge in NUDGES:
                    pick = self.move_to(target, nudge)
                    result = self.strike(target, pick)
                    if result != "nichts":
                        if nudge != (0, 0):          # versetzt hat geklappt -> Versatz merken
                            self.learn_offset(pick, target)
                        break
                    log("  Schlag hat nichts bewirkt - versuche leicht versetzt.")
            except Unreachable:
                log("  Hacke bewegt sich nicht weiter (Rand?) - überspringe diesen Punkt.")
                gone.append(target)
                continue
            if result == "nichts":
                self.save_debug("fehlschlag", pick, dots, target)
                raise RoundError("Punkt lässt sich nicht treffen - bitte mit F8 kalibrieren "
                                 "(Hacke von Hand auf einen Punkt stellen, dann F8).")
            if result == "gebrochen":
                log("Fels gebrochen - GEWONNEN!")
                return
            if result == "weg":
                log("  Punkt verschwunden - falscher Punkt, weiter zum nächstgelegenen.")
                gone.append(target)
                continue

            log("  Riss! Richtiger Punkt gefunden (1/7).")
            self.finish_rock(target)
            return

    def finish_rock(self, target):
        """Richtigen Punkt weiter schlagen, bis der Fels bricht (insgesamt 7 Schläge)."""
        hits = 1
        while hits < HITS_TO_WIN + MAX_EXTRA_HITS:
            self.ctl.sleep(HIT_DELAY)
            pick, _ = self.look()
            if pick is None:
                log("Spitzhacke verschwunden - Fels vermutlich gebrochen.")
                return
            if np.linalg.norm(pick.hit_point(self.offset) - target) > 1.5 * AIM_TOL * pick.length:
                self.move_to(target)                    # Hacke ist verrutscht
            self.keys.tap("space")
            hits += 1
            log(f"  Schlag {hits}/{HITS_TO_WIN}")
            self.ctl.sleep(HIT_WAIT)
            if hits >= HITS_TO_WIN:
                if self.wait_broken(WIN_WAIT if hits == HITS_TO_WIN else 1.0):
                    log("Fels gebrochen - GEWONNEN!")
                    self.save_debug("2_gewonnen")
                    return
                log("  Fels noch nicht gebrochen - schlage weiter.")
        log("Fertig geschlagen, Fels aber nicht als gebrochen erkannt.")

    def wait_broken(self, seconds):
        """Fels gebrochen = Spitzhacke oder alle roten Punkte sind verschwunden."""
        t0 = time.time()
        while time.time() - t0 < seconds:
            pick, dots = self.look()
            if pick is None or not dots:
                return True
            self.ctl.sleep(0.1)
        return False

    # ------------------------------------------------------------------- loop
    def run(self):
        log("Bergbau-Bot gestartet.  F8 = Kalibrieren, F9 = Pause/Weiter, F10 = Beenden.")
        if self.dry:
            log("PROBE-MODUS: es werden keine Tasten gedrückt.")
        log("Klicke jetzt ins Spielfenster und starte das Minispiel.")
        armed, absent_since, searching_logged = True, None, False
        seen_since = None
        while not self.ctl.quit:
            if self.ctl.paused:
                time.sleep(0.2)
                continue
            try:
                self.handle_calibration()
                pick, dots = self.look()
                if pick is None or not dots:
                    seen_since = None
                    absent_since = absent_since or time.time()
                    if not armed and time.time() - absent_since >= NEW_ROUND_GAP:
                        armed = True
                        log("Warte auf die nächste Runde ...")
                    if armed and not searching_logged:
                        log("Suche Spitzhacke und rote Punkte ...")
                        searching_logged = True
                    time.sleep(0.15)
                    continue
                absent_since = None
                if not armed:
                    time.sleep(0.15)
                    continue
                seen_since = seen_since or time.time()
                if time.time() - seen_since < 0.4:          # kurz stabil sichtbar
                    time.sleep(0.05)
                    continue
                searching_logged = False
                try:
                    self.play_round(pick, dots)
                except RoundError as e:
                    log(f"Runde abgebrochen: {e}")
                    self.save_debug("fehler", *self.look())
                armed = False
                seen_since = None
            except Abort:
                if self.ctl.quit:
                    break
                log("Runde abgebrochen (Pause).")
        log("Beendet.")


# ============================================================================
# Testmodus
# ============================================================================
def run_test(path):
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"Bild nicht lesbar: {path}")
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    pick = find_pick(hsv)
    if pick is None:
        print("Keine Spitzhacke gefunden.")
        return
    dots = find_dots(hsv, pick)
    offset = load_offset()
    hp = pick.hit_point(offset)
    print(f"Spitzhacke: oberes Stiel-Ende ({pick.top[0]:.0f},{pick.top[1]:.0f}), Länge {pick.length:.0f}px")
    print(f"Trefferpunkt: ({hp[0]:.0f},{hp[1]:.0f})")
    print(f"Rote Punkte: {len(dots)}")
    for d in sorted(dots, key=lambda d: np.linalg.norm(d - hp)):
        print(f"  ({d[0]:.0f},{d[1]:.0f})  Abstand {np.linalg.norm(d - hp) / pick.length:.2f} Stiel-Längen")
    out_path = os.path.join(HERE, "bergbau_test.png")
    cv2.imwrite(out_path, annotate(img, pick, dots, offset))
    print("Markiertes Bild gespeichert:", out_path)


def main():
    ap = argparse.ArgumentParser(description="Bergbau-Minispiel-Bot")
    ap.add_argument("--dry", action="store_true", help="nur erkennen, keine Tasten drücken")
    ap.add_argument("--debug", action="store_true", help="Bilder in ./debug speichern")
    ap.add_argument("--test", metavar="BILD", help="Erkennung an einem Screenshot testen")
    args = ap.parse_args()
    if args.test:
        run_test(args.test)
    else:
        Bot(debug=args.debug, dry=args.dry).run()


if __name__ == "__main__":
    main()
