"""State and storage of synthesized lines. The Ogg Opus file in the content repository is the single source of the voice:
there are no intermediate WAV copies, `voice` encodes straight into content/uk/audio/<bundle path>.ogg.

The state is content/uk/voice_state.csv (name,sig): the signature of the inputs a line was synthesized from (text, voice, pitch, speed and the
length of the original). It lives in the content repository next to the voices it describes, so any maintainer sees what is up to date and
what is stale compared to the text, and does not depend on somebody's local folder."""
import csv
import hashlib
import os

import numpy as np

from d4loc import oggenc

FILE = "voice_state.csv"


def sha(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(path):
    """{line name: signature}; an empty dict if the file does not exist yet."""
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["name"]: r["sig"] for r in csv.DictReader(f)}


def save_state(path, state):
    """Sorted by name with LF line endings: a pull request shows only the lines that were synthesized again."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["name", "sig"])
        for name in sorted(state):
            w.writerow([name, state[name]])


def decide(dst, prev_sig, sig, force=False, recorded=False):
    """'make' (synthesize and write), 'same' (up to date, skip) or 'community' (a person's recording: leave it alone).
    A recording is recognized by the status `recorded` in uk/status.csv, which travels with the pull request."""
    if not os.path.isfile(dst) or force:
        return "make"
    if recorded:
        return "community"
    return "same" if prev_sig == sig else "make"


def write_clip(dst, audio, rate, bitrate=oggenc.DEFAULT_BITRATE):
    """float32 mono in [-1, 1] -> Ogg Opus at dst. Returns the SHA-1 of the written file."""
    data = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    oggenc.write_opus(dst, data, rate, bitrate)
    return sha(dst)
