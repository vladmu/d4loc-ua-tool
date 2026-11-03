"""Synthesizing lines with Holos TTS according to the approved casting (voice_cast.json) with the roles' effects.

Run (the holos_env environment, from the repository root): holos_env/Scripts/python.exe dev/run.py voice --prefix dlg_main01

The result is encoded straight into the content repository (content/uk/audio/<bundle path>.ogg, Ogg Opus): that file is the single
source of the voice, no intermediate WAV copies are kept. The English original is not mixed in here, the installer does that.
"""
import re
import argparse, csv, hashlib, json, math, os, time, wave
import numpy as np
from scipy.signal import resample_poly

from d4loc import oggenc, status
from d4loc.audio import TARGET_DB, active_rms, limit
from tools import paths
from tools.game import index
from tools.voice import fx, store
from tools.voice import pipeline as hp
from holos_onnx import HolosTTS



def read_wav(path):
    with wave.open(path, "rb") as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, rate


PITCH_GAIN = 1.4
ROLE_FX = {"": "overlord", "thalya": "thalya", "thalya_good": "thalya", "story_brother": "brother",
           "story_dwarfqueen": "queen", "tanos": "tanos", "story_angel": "angel"}


ACTIONS = [(r"зітха|зітх", "Ох"), (r"каш|гарк|прочищ|кхм", "Кхм"), (r"задих|ахн", "Ах"), (r"відрижк", "Ик"), (r"хік", "Ік"),
           (r"хрк|хр-р", "Хр-р"), (r"мурч", "Мр-р"), (r"нюха", "Шмиг"), (r"тру-у", "Ту-у-у")]


def stage_directions(t):
    """Stage directions in asterisks (*sighs*, *cough*) are voiced as a sound, not as a word; descriptive ones (*thoughtfully*) are removed."""
    import re

    def fix(m):
        inner = m.group(1).strip().lower()
        for pat, sound in ACTIONS:
            if re.search(pat, inner):
                return " " + sound + ". "
        return ""
    t = re.sub(r"\*([^*]+)\*", fix, t)
    t = re.sub(r"\s*([.,!?…])(?:\s*[.,…])+", r"\1", t)
    t = re.sub(r"\s+([.,!?])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def fix_text(t):
    import re
    t = stage_directions(t)
    t = re.sub(r"(?<![А-Яа-яІіЇїЄєҐґ])[Хх]а-ха", lambda m: "А-ха-ха" if m.group(0)[0] == "Х" else "а-ха-ха", t)
    return t


def apply_fx(a, sr, tag):
    kind = ROLE_FX.get(tag)
    if kind == "angel":
        return fx.angel(a, sr)
    if kind:
        rt60, wet = fx.ROOM[kind]
        return fx.room(a, sr, rt60, wet)
    return a


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", required=True)
    p.add_argument("--texts", default=paths.TRANSLATIONS)
    p.add_argument("--state", default=os.path.join(paths.CONTENT_UK, store.FILE), help="стан синтезу: у репозиторії контенту поруч із голосами")
    p.add_argument("--report", default=os.path.join(paths.UK_AUDIO, "voice_report.csv"))
    p.add_argument("--force", action="store_true", help="перегенерувати все, навіть файли, змінені спільнотою")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--speed", type=float, default=1.12, help="базова швидкість мовлення (оригінальні актори говорять швидше за модель)")
    p.add_argument("--bitrate", type=int, default=oggenc.DEFAULT_BITRATE)
    p.add_argument("--limit", type=int, default=0)
    cfg = p.parse_args()
    from tools.text import public
    public.ensure_table(cfg.texts)         # a fresh work folder: rebuilt from content/uk

    cast = {k: v for k, v in json.load(open(paths.VOICE_CAST, encoding="utf-8")).items() if not k.startswith("_")}
    texts = {r["name"]: r for r in csv.DictReader(open(cfg.texts, encoding="utf-8-sig", newline=""))
             if r["uk"] and r["status"] in ("machine", "edited", "user", "recorded")}
    all_meta = index.uk_rows()          # the lines of the game, with the English originals unpacked in content/en/
    meta = [r for r in all_meta if r["name"].startswith(cfg.prefix)]
    if cfg.limit:
        meta = meta[:cfg.limit]
    state = store.load_state(cfg.state)

    m = HolosTTS("patriotyk/HolosTTS/onnx", providers=["CPUExecutionProvider" if cfg.cpu else "CUDAExecutionProvider"])
    voices = m.list_voices(); msr = m.sample_rate
    report = []; t0 = time.time()
    for i, r in enumerate(meta, 1):
        name = r["name"]; t = texts.get(name)
        if not t:
            report.append((name, "", "", "", "немає перекладу")); continue
        orig, rate = read_wav(r["en_wav"])     # the length of the English original is the length the Ukrainian line has to fit into
        target = len(orig) / rate
        tag = t["voice"]; vi = cast.get(tag, cast[""])
        text = fix_text(t["uk"])
        hp.HINTS.clear()
        hp.HINTS["source"] = t["source"]
        dst = os.path.join(paths.CONTENT_AUDIO, os.path.splitext(r["container_path"])[0] + ".ogg")
        sig = hashlib.sha1(f"{text}|{vi}|{PITCH_GAIN}|{len(orig)}|{rate}|{TARGET_DB}|h12|{cfg.speed}|None".encode()).hexdigest()   # same signature as before: existing state stays valid
        todo = store.decide(dst, state.get(name), sig, cfg.force, recorded=t["status"] == status.RECORDED)
        if todo != "make":
            report.append((name, vi, round(target, 2), "", "ok" if todo == "same" else "змінено спільнотою")); continue
        try:
            a = hp.synthesize(m, text, voices[vi - 1], cfg.speed, pitch_gain=PITCH_GAIN)
            d = len(a) / msr
            if d > target * 0.97:
                sp = min(1.6, cfg.speed * d / (target * 0.97))
                a = hp.synthesize(m, text, voices[vi - 1], sp, pitch_gain=PITCH_GAIN)
            a = apply_fx(a, msr, tag)
        except Exception as e:
            print(f"  ! {name}: {e}"); report.append((name, vi, round(target, 2), "", f"помилка: {e}")); continue
        g = math.gcd(msr, rate)
        a = resample_poly(a, rate // g, msr // g).astype(np.float32)
        n = len(orig)
        longer = len(a) > n
        cut_s = max(0, len(a) - n) / rate
        if longer:
            k = int(0.05 * rate); a = a[:n].copy(); a[-k:] *= np.linspace(1, 0, k)
        a = np.pad(a, (0, n - len(a)))
        a = limit(a * (10 ** (TARGET_DB / 20) / max(active_rms(a, rate), 1e-6)), rate)
        store.write_clip(dst, a, rate, cfg.bitrate)
        state[name] = sig
        report.append((name, vi, round(target, 2), round(d, 2), "обрізано" if longer else "ok", round(cut_s, 2)))
        if i % 10 == 0: print(f"  {i}/{len(meta)}, {time.time()-t0:.0f} с", flush=True)
        if i % 50 == 0: store.save_state(cfg.state, state)
    store.save_state(cfg.state, state)
    with open(cfg.report, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["name", "voice", "target_s", "natural_s", "status", "cut_s"]); w.writerows(report)
    print("Індекс і маніфест:", index.sync(all_meta))     # audio_metadata.csv, audiodef/audioindex and manifest.json in content/
    print("Готово:", len(report), "| обрізано:", sum(x[4] == "обрізано" for x in report), "| без перекладу:", sum(x[4] == "немає перекладу" for x in report),
          "| змінено спільнотою (не чіпали):", sum(x[4] == "змінено спільнотою" for x in report))


if __name__ == "__main__":
    main()
