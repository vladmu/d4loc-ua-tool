"""The translator's project folder: unpacked languages and the queue of pending changes (pending).

The project folder is a fork of the content repository (see repo.py): uk is already there unpacked, the English is unpacked next to it (en/) and stays out of git.
Structure of the project folder:
  <project>/<lang>/loca_<lang>_texts.csv  texts in the game format (the game file without transformation)
  <project>/<lang>/audio/<bundle path>  voice files by bundle paths, together with audiodef.txt and audioindex.txt
  <project>/<lang>/audio_metadata.csv   mapping key -> bundle/path/file
  <project>/<lang>/pending/texts.json   text edits waiting for "Save" (not committed)
  <project>/<lang>/pending/audio/<key>.wav   new clips waiting for "Save" (not committed)
The game files are never changed here; the uk/ files change only in save().
"""
import csv
import json
import os
import shutil
import wave

from . import audio, game, repo, status, texts
from .i18n import _

META_FIELDS = ["bundle", "name", "wording", "file_id", "file_path", "container_path", "path_id", "md5"]


def lang_dir(project, lang):
    return os.path.join(project, lang)


def is_unpacked(project, lang):
    return os.path.isfile(os.path.join(lang_dir(project, lang), "audio_metadata.csv")) or \
        os.path.isfile(os.path.join(lang_dir(project, lang), f"loca_{lang}_texts.csv"))


def source_signature(info):
    """Signature of the language's source files in the game (size and modification time), used to notice that the unpacked copy is outdated."""
    files = ([info["texts"]] if info.get("texts") else []) + list(info.get("audio", []))
    return {os.path.basename(f): [os.path.getsize(f), int(os.path.getmtime(f))] for f in files if os.path.isfile(f)}


def is_stale(game_dir, lang, project):
    """True if the language is not unpacked yet or the game files changed after unpacking."""
    info = game.list_languages(game_dir).get(lang)
    sp = os.path.join(lang_dir(project, lang), "source.json")
    if not info or not os.path.isfile(sp):
        return bool(info)
    try:
        with open(sp, encoding="utf-8") as f:
            return json.load(f) != source_signature(info)
    except (OSError, ValueError):
        return True


def unpack_language(game_dir, lang, project, progress=None, log=print):
    """Unpacks the language's texts and audio into the project folder. Existing project files are not overwritten without need."""
    game.require_game_dir(game_dir)
    info = game.list_languages(game_dir).get(lang)
    if not info:
        raise RuntimeError(_("У грі немає мови {0}").format(lang))
    ld = lang_dir(project, lang)
    os.makedirs(ld, exist_ok=True)
    rows_t = texts.read_texts(info["texts"]) if info["texts"] else []
    dst = os.path.join(ld, f"loca_{lang}_texts.csv")
    texts.write_texts(dst, rows_t)
    wording = {r[0]: r[1] for r in rows_t}
    meta, bundles = [], info["audio"]
    for i, b in enumerate(bundles, 1):
        label = _("Мова {0}: {1}").format(lang, os.path.basename(b))
        meta += audio.extract_bundle(
            b, os.path.join(ld, "audio"), wording, log,
            (lambda k, n, i=i, label=label: progress((i - 1) + k / max(n, 1), len(bundles), label)) if progress else None)
    if bundles:
        with open(os.path.join(ld, "audio_metadata.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=META_FIELDS)
            w.writeheader()
            w.writerows(meta)
    if progress:
        progress(len(bundles), max(len(bundles), 1), _("Готово"))
    with open(os.path.join(ld, "source.json"), "w", encoding="utf-8") as f:
        json.dump(source_signature(info), f)
    if not info["texts"]:
        log(_("Мова {0}: текстів у грі нема.").format(lang))
    if not bundles:
        log(_("Мова {0}: озвучення в грі нема (лише тексти: {1}). Це нормально, працюватиме лише переклад.").format(lang, len(rows_t)))
    else:
        log(_("Мова {0}: готово, текстів {1}, кліпів {2}.").format(lang, len(rows_t), len(meta)))
    return len(rows_t), len(meta)


def ensure_language(game_dir, lang, project, progress=None, log=print, force=False):
    """The one place that unpacks a language from the game into a project folder: the translator tool and `python dev/run.py extract` both call it.
    Unpacks when the language is not in the project yet or the game files changed since; leaves an up-to-date copy alone (force: unpack again).
    Returns 'unpacked', 'updated', 'current', 'pending' (outdated, but there are unsaved changes: nothing is touched) or 'missing' (not in the game)."""
    info = game.list_languages(game_dir).get(lang)
    if not info or not info["texts"]:
        log(_("Мови {0} нема в грі.").format(lang))
        return "missing"
    unpacked = is_unpacked(project, lang)
    if unpacked and not force and not is_stale(game_dir, lang, project):
        log(_("Мова {0}: уже в проєкті, актуальна.").format(lang))
        return "current"
    if unpacked and (load_pending_texts(project, lang) or list_pending_audio(project, lang)):
        log(_("⚠ Файли гри для мови {0} змінились, але в проєкті є незбережені зміни. Збережіть або скасуйте їх, тоді проєкт можна буде оновити.").format(lang))
        return "pending"
    log(_("Мова {0}: файли гри змінились — оновлюю проєкт…").format(lang) if unpacked else _("Завантажую мову {0} із гри…").format(lang))
    unpack_language(game_dir, lang, project, progress, log)
    return "updated" if unpacked else "unpacked"


def load_rows(project, lang):
    """[{name, wording, voice, tags, wav, bundle}] for the table: the language's text + the path to the unpacked WAV (if any)."""
    ld = lang_dir(project, lang)
    meta = {}
    mp = os.path.join(ld, "audio_metadata.csv")
    if os.path.isfile(mp):
        with open(mp, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r["name"]:
                    meta[r["name"]] = r
    out = []
    for name, wording, voice, tags in texts.read_texts(os.path.join(ld, f"loca_{lang}_texts.csv")):
        m = meta.get(name)
        wav = ""
        if m:
            wav = m.get("file_path", "")
            if not wav or not os.path.isfile(wav):   # in the repository paths are not absolute: the file is looked up by container_path
                wav = repo.clip_path(ld, m.get("container_path", "")) if m.get("container_path") else ""
        out.append({"name": name, "wording": wording, "voice": voice, "tags": tags, "wav": wav, "bundle": m["bundle"] if m else ""})
    return out


# ---------- queue of changes ----------
def _pending_dir(project, lang):
    return os.path.join(lang_dir(project, lang), "pending")


def load_pending_texts(project, lang):
    p = os.path.join(_pending_dir(project, lang), "texts.json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_pending_texts(project, lang, d):
    os.makedirs(_pending_dir(project, lang), exist_ok=True)
    with open(os.path.join(_pending_dir(project, lang), "texts.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def pending_audio_path(project, lang, name):
    return os.path.join(_pending_dir(project, lang), "audio", name + ".wav")


def list_pending_audio(project, lang):
    d = os.path.join(_pending_dir(project, lang), "audio")
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".wav")) if os.path.isdir(d) else []


def stage_audio(project, lang, name, src_path):
    """Puts new audio into the queue (WAV 16-bit mono). Supports WAV/OGG/FLAC/MP3 (through soundfile). Returns (duration, rate)."""
    import soundfile as sf
    data, rate = sf.read(src_path, dtype="int16", always_2d=True)
    mono = data.mean(axis=1).astype("int16") if data.shape[1] > 1 else data[:, 0]
    dst = pending_audio_path(project, lang, name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(mono.tobytes())
    return len(mono) / rate, rate


def unstage_audio(project, lang, name):
    p = pending_audio_path(project, lang, name)
    if os.path.isfile(p):
        os.remove(p)


def discard_pending(project, lang):
    shutil.rmtree(_pending_dir(project, lang), ignore_errors=True)


def wav_duration(path):
    try:
        with wave.open(path) as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, OSError, EOFError):
        return 0.0


def summary(project, lang):
    t = load_pending_texts(project, lang)
    a = list_pending_audio(project, lang)
    return {"texts": len(t), "audio": len(a)}


# ---------- saving into the project ----------
def save(project, lang, log=print):
    """Saves the queue of changes into the project: text into <lang>/loca_<lang>_texts.csv, new recordings into uk/audio (Ogg Opus in place of the old file).
    Nothing is written to the game: installation happens only in the installer window (backups, warnings, the version check are there)."""
    if lang == "en":
        raise RuntimeError(_("Англійська — оригінал і не змінюється."))
    pend_t = load_pending_texts(project, lang)
    pend_a = list_pending_audio(project, lang)
    tpath = os.path.join(lang_dir(project, lang), f"loca_{lang}_texts.csv")
    rows = texts.read_texts(tpath)
    changed_texts = [n for n, w, _v, _t in rows if n in pend_t and pend_t[n] != w]
    texts.write_texts(tpath, [(n, pend_t.get(n, w), v, t) for n, w, v, t in rows])
    meta_path = os.path.join(lang_dir(project, lang), "audio_metadata.csv")
    meta = []
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8-sig", newline="") as f:
            meta = list(csv.DictReader(f))
    by_name = {m["name"]: m for m in meta}
    in_repo = lang == repo.LANG and repo.is_content_project(project)
    stored = 0
    recorded = []
    for name in pend_a:
        src = pending_audio_path(project, lang, name)
        m = by_name.get(name)
        if in_repo and m and m.get("container_path"):
            repo.store_clip(lang_dir(project, lang), m["container_path"], src)    # in place of the old file in uk/audio
            recorded.append(name)
        elif m and m.get("file_path") and os.path.isfile(m["file_path"]):
            shutil.copy2(src, m["file_path"])
        else:
            dst = os.path.join(lang_dir(project, lang), "audio", "applied", name + ".wav")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            meta.append({"bundle": "", "name": name, "wording": "", "file_id": "", "file_path": dst,
                         "container_path": "", "path_id": "", "md5": ""})
        stored += 1
    if meta:
        with open(meta_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=META_FIELDS)
            w.writeheader()
            w.writerows(meta)
    if in_repo:
        status.mark(lang_dir(project, lang), texts=changed_texts, recordings=recorded)     # a person changed these lines: the pipeline will not overwrite them
    discard_pending(project, lang)
    log(_("Збережено в проєкт: текстів {0}, нових записів {1}.").format(len(pend_t), stored))
    if in_repo:
        log(_("Далі: у теці проєкту зробіть git add, commit, push і створіть pull request."))
    return len(pend_t), stored


# ---------- playback and duration (WAV directly, FLAC/OGG through a temporary WAV) ----------
def playable(path):
    """Path to a WAV for playback; FLAC/OGG is decoded into a temporary file."""
    if not path or not os.path.isfile(path):
        return ""
    if path.lower().endswith(".wav"):
        return path
    import tempfile
    import soundfile as sf
    data, rate = sf.read(path, dtype="int16")
    out = os.path.join(tempfile.gettempdir(), "d4loc_play.wav")
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((data if data.ndim == 1 else data.mean(axis=1).astype("int16")).tobytes())
    return out


def duration(path):
    if not path or not os.path.isfile(path):
        return 0.0
    if path.lower().endswith(".wav"):
        return wav_duration(path)
    try:
        import soundfile as sf
        i = sf.info(path)
        return i.frames / i.samplerate
    except Exception:
        return 0.0


def new_language(project, lang, ref_lang="en"):
    """New language: an empty table with the keys of the reference language (empty text) for translating from scratch."""
    ld = lang_dir(project, lang)
    os.makedirs(ld, exist_ok=True)
    dst = os.path.join(ld, f"loca_{lang}_texts.csv")
    if not os.path.exists(dst):
        rows = texts.read_texts(os.path.join(lang_dir(project, ref_lang), f"loca_{ref_lang}_texts.csv"))
        texts.write_texts(dst, [(n, "", v, t) for n, _, v, t in rows])
