"""A minimal audio player on Windows MCI (no extra libraries): playback, pause, seeking, position."""
import ctypes
import sys

ALIAS = "d4loc_clip"


class Player:
    def __init__(self):
        self.ok = sys.platform == "win32"
        self.path = ""
        self._open = False
        if self.ok:
            self._mci = ctypes.windll.winmm.mciSendStringW

    def _cmd(self, text, want=False):
        if not self.ok:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        err = self._mci(text, buf, 255, 0)
        if err:
            return ""
        return buf.value if want else "ok"

    def load(self, path):
        """Opens a WAV; returns True on success."""
        self.close()
        if not self.ok or not path:
            return False
        if self._cmd(f'open "{path}" type waveaudio alias {ALIAS}') != "ok":
            return False
        self._cmd(f"set {ALIAS} time format milliseconds")
        self._open, self.path = True, path
        return True

    def close(self):
        if self._open:
            self._cmd(f"stop {ALIAS}")
            self._cmd(f"close {ALIAS}")
        self._open, self.path = False, ""

    def play(self, from_ms=None):
        if not self._open:
            return
        if from_ms is None:
            self._cmd(f"play {ALIAS}")
        else:
            self._cmd(f"play {ALIAS} from {int(from_ms)}")

    def pause(self):
        if self._open:
            self._cmd(f"pause {ALIAS}")

    def resume(self):
        if self._open:
            self._cmd(f"resume {ALIAS}")

    def stop(self):
        if self._open:
            self._cmd(f"stop {ALIAS}")
            self._cmd(f"seek {ALIAS} to start")

    def seek(self, ms, keep_playing=False):
        if not self._open:
            return
        mode = self.mode()
        self._cmd(f"seek {ALIAS} to {int(ms)}")
        if keep_playing or mode == "playing":
            self._cmd(f"play {ALIAS}")

    def mode(self):
        """'playing' | 'paused' | 'stopped' | 'closed'"""
        if not self._open:
            return "closed"
        return self._cmd(f"status {ALIAS} mode", True) or "closed"

    def position(self):
        v = self._cmd(f"status {ALIAS} position", True) if self._open else ""
        return int(v) if v.isdigit() else 0

    def length(self):
        v = self._cmd(f"status {ALIAS} length", True) if self._open else ""
        return int(v) if v.isdigit() else 0
