"""Game audio bundles: unpacking, cloning for a new language, replacing clips, mixing with the original."""
import hashlib
import os
import re
import shutil
import struct

import numpy as np
from .i18n import _

FSB_PCM16 = 2
FREQ_INDEX = {8000: 1, 11000: 2, 11025: 3, 16000: 4, 22050: 5, 24000: 6, 32000: 7, 44100: 8, 48000: 9}
UNITY_PCM = 0
TARGET_DB = -17.5
SYSTEM_FILES = ("audiodef.txt", "audioindex.txt")


# ---------- helpers ----------
def _unitypy():
    import UnityPy
    return UnityPy


def build_fsb5_pcm16(pcm, channels, frequency):
    """A minimal FSB5 with a single PCM16 subsound."""
    if frequency not in FREQ_INDEX:
        raise ValueError(_("непідтримувана частота {0}").format(frequency))
    frames = len(pcm) // (2 * channels)
    mode = (FREQ_INDEX[frequency] << 1) | ((channels - 1) << 5) | (frames << 34)
    sample_header = struct.pack("<Q", mode)
    header = struct.pack("<4s6I", b"FSB5", 1, 1, len(sample_header), 0, len(pcm), FSB_PCM16)
    header += struct.pack("<Q", 1) + bytes(16) + bytes(8)
    return header + sample_header + pcm, frames


def parse_audiodef(text):
    """{file_name_lowercase: (file_id, alias)}"""
    result, current = {}, None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            current = line.strip()
        elif current and line.strip().startswith("alias:"):
            result[current.lower()] = (current, line.split(":", 1)[1].strip())
    return result


def asset_text(data):
    raw = getattr(data, "m_Script", None) or getattr(data, "script", None)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return raw


def clip_aliases(env):
    """{container_path: alias} for every AudioClip in the bundle (the alias comes from audiodef.txt)."""
    ids = {}
    for path, obj in env.container.items():
        if obj.type.name == "TextAsset" and os.path.basename(path).lower() == "audiodef.txt":
            ids = parse_audiodef(asset_text(obj.read()) or "")
    out = {}
    for path, obj in env.container.items():
        if obj.type.name == "AudioClip":
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            out[path] = ids.get(stem, (stem, ""))[1]
    return out


def decode_clip(obj):
    """AudioClip -> (float32 mono, sample rate). None on failure."""
    import io
    import wave
    clip = obj.read()
    samples = getattr(clip, "samples", None) or {}
    data = next(iter(samples.values()), None)
    if not data:
        return None
    with wave.open(io.BytesIO(data)) as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() > 1:
            raw = raw.reshape(-1, w.getnchannels()).mean(axis=1)
        return raw, w.getframerate()


# ---------- DSP ----------
def active_rms(a, sr):
    fr = int(0.05 * sr)
    n = len(a) // fr
    if n == 0:
        return float(np.sqrt(np.mean(a ** 2))) if len(a) else 0.0
    blocks = a[:n * fr].reshape(n, fr)
    e = np.sqrt((blocks ** 2).mean(axis=1) + 1e-12)
    act = e > 0.02 * e.max()
    return float(np.sqrt((blocks[act] ** 2).mean())) if act.any() else float(np.sqrt(np.mean(a ** 2)))


def limit(a, sr, ceiling=0.9):
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    g = np.minimum(1.0, ceiling / np.maximum(np.abs(a), 1e-9))
    w = max(1, int(0.005 * sr))
    g = uniform_filter1d(minimum_filter1d(g, size=2 * w + 1, mode="nearest"), size=2 * w + 1, mode="nearest")
    return a * g


def mix_original(voice, orig, rate, db):
    """Voice-over mix: the original sits quietly under the voice, and is ducked a further 6 dB during speech."""
    from scipy.ndimage import uniform_filter1d
    o = np.pad(orig[:len(voice)].astype(np.float32), (0, max(0, len(voice) - len(orig))))
    o = o * (10 ** (TARGET_DB / 20) / max(active_rms(o, rate), 1e-6)) * (10 ** (db / 20))
    env = uniform_filter1d(np.abs(voice), size=max(1, int(0.12 * rate)))
    speech = uniform_filter1d((env > 0.02 * max(env.max(), 1e-9)).astype(np.float32), size=max(1, int(0.15 * rate)))
    return limit(voice + o * (1.0 - 0.5 * speech), rate)


def to_pcm16(a):
    return (np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()


# ---------- unpacking ----------
def extract_bundle(path, out_dir, texts=None, log=print, progress=None):
    """Unpacks the bundle's WAVs and service files, preserving paths. Returns the metadata rows."""
    UnityPy = _unitypy()
    texts = texts or {}
    env = UnityPy.load(path)
    bundle = os.path.basename(path)
    ids = {}
    for p, obj in env.container.items():
        if obj.type.name == "TextAsset" and os.path.basename(p).lower() in SYSTEM_FILES:
            content = asset_text(obj.read())
            if content is None:
                continue
            dst = os.path.join(out_dir, p)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            if os.path.basename(p).lower() == "audiodef.txt":
                ids = parse_audiodef(content)
    rows = []
    total = sum(1 for _, o in env.container.items() if o.type.name == "AudioClip")
    seen = 0
    for p, obj in env.container.items():
        if obj.type.name != "AudioClip":
            continue
        seen += 1
        if progress and seen % 25 == 0:
            progress(seen, total)
        clip = obj.read()
        samples = getattr(clip, "samples", None) or {}
        audio = next(iter(samples.values()), None) or getattr(clip, "m_AudioData", None)
        if not audio:
            log(_("  ! немає даних: {0}").format(p))
            continue
        dst = os.path.join(out_dir, p)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(audio)
        stem = os.path.splitext(os.path.basename(p))[0]
        file_id, alias = ids.get(stem.lower(), (stem, ""))
        rows.append({"bundle": bundle, "name": alias, "wording": texts.get(alias, ""), "file_id": file_id,
                     "file_path": os.path.abspath(dst), "container_path": p, "path_id": obj.path_id,
                     "md5": hashlib.md5(audio).hexdigest()})
    log(_("{0}: розпаковано {1} кліпів").format(bundle, len(rows)))
    return rows


# ---------- cloning a bundle for a language + replacing clips ----------
def lang_path(path, src_lang, dst_lang):
    return re.sub(rf"^(assets/audio/){re.escape(src_lang)}(?=[/.])", rf"\g<1>{dst_lang}", path)


def build_language_bundle(src_path, dst_path, dst_lang, replace=None, src_lang="en", log=print):
    """Clone of the English bundle for the language dst_lang. replace: {alias: (pcm_bytes, channels, freq)} or a function (alias, obj) -> (pcm, ch, freq) | None."""
    UnityPy = _unitypy()
    from UnityPy.streams import EndianBinaryReader
    replace = replace or {}
    env = UnityPy.load(src_path)
    bf = env.file
    dst_name = os.path.basename(dst_path)
    old_cab = next(n for n in bf.files if not n.endswith(".resource"))
    res_name = next(n for n in bf.files if n.endswith(".resource"))
    new_cab = "CAB-" + hashlib.md5(dst_name.encode()).hexdigest()
    new_src = f"archive:/{new_cab}/{new_cab}.resource"
    old_res = memoryview(bf.files[res_name].bytes)
    alias_by_pid = {}
    for path, alias in clip_aliases(env).items():
        obj = env.container[path]
        alias_by_pid[obj.path_id] = alias
    new_res = bytearray()
    done = kept = 0
    for obj in env.objects:
        t = obj.type.name
        if t == "AssetBundle":
            tt = obj.read_typetree()
            tt["m_Name"] = dst_name
            tt["m_AssetBundleName"] = dst_name
            tt["m_Container"] = [(lang_path(p, src_lang, dst_lang), info) for p, info in tt["m_Container"]]
            obj.save_typetree(tt)
        elif t == "AudioClip":
            tt = obj.read_typetree()
            alias = alias_by_pid.get(obj.path_id, "")
            rep = replace(alias, obj) if callable(replace) else replace.get(alias)
            if rep:
                pcm, channels, freq = rep
                blob, frames = build_fsb5_pcm16(pcm, channels, freq)
                tt["m_CompressionFormat"] = UNITY_PCM
                tt["m_Channels"], tt["m_Frequency"], tt["m_BitsPerSample"] = channels, freq, 16
                tt["m_Length"] = frames / freq
                done += 1
            else:
                r = tt["m_Resource"]
                blob = bytes(old_res[r["m_Offset"]:r["m_Offset"] + r["m_Size"]])
                kept += 1
            tt["m_Resource"]["m_Source"] = new_src
            tt["m_Resource"]["m_Offset"] = len(new_res)
            tt["m_Resource"]["m_Size"] = len(blob)
            new_res += blob
            new_res += bytes(-len(new_res) % 32)
            obj.save_typetree(tt)
    reader = EndianBinaryReader(bytes(new_res))
    reader.flags = bf.files[res_name].flags
    bf.files[res_name] = reader
    bf.files = {n.replace(old_cab, new_cab): f for n, f in bf.files.items()}
    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
    with open(dst_path, "wb") as f:
        f.write(bf.save(packer="original"))
    sidecar = src_path[:-len(".unity3d")] + ".csv"
    if os.path.isfile(sidecar):
        shutil.copy2(sidecar, dst_path[:-len(".unity3d")] + ".csv")
    log(_("{0}: замінено {1}, без змін {2}, {3:.0f} МБ").format(dst_name, done, kept, os.path.getsize(dst_path) / 2**20))
    return done, kept
