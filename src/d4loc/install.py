"""Installing and removing the Ukrainian language: builds bundles from the user's game files without distributing anything that is not ours."""
import csv
import glob
import json
import os
import re
import shutil
import tempfile

import numpy as np

from . import audio, game, texts
from .i18n import _

LANG = "uk"
MANIFEST = "manifest.json"
TEXT_FILE = "loca_uk_texts.csv"


def text_path(pack_dir):
    """The text in the pack folder (an unpacked content.zip or a fork of the content repository): uk/loca_uk_texts.csv."""
    return os.path.join(pack_dir or "", "uk", TEXT_FILE)


def voice_files(pack_dir):
    """{line key: file}: voices from uk/audio by bundle paths and uk/audio_metadata.csv (.ogg; new recordings may be .flac or .wav)."""
    out = {}
    meta = os.path.join(pack_dir or "", "uk", "audio_metadata.csv")
    if os.path.isfile(meta):
        from . import repo
        ld = os.path.join(pack_dir, "uk")
        with open(meta, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                p = repo.clip_path(ld, r.get("container_path", "")) if r.get("container_path") else ""
                if r.get("name") and p:
                    out[r["name"]] = p
    return out


def has_content(pack_dir):
    """The pack folder has the translation data (manifest.json and the text). Voice-over (voice/) is not needed for that."""
    return bool(pack_dir) and os.path.isfile(os.path.join(pack_dir, MANIFEST)) and os.path.isfile(text_path(pack_dir))


def has_voice(pack_dir):
    return bool(voice_files(pack_dir))


def load_manifest(pack_dir):
    with open(os.path.join(pack_dir, MANIFEST), encoding="utf-8") as f:
        return json.load(f)


def _read_voice(path):
    import soundfile as sf
    data, rate = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, rate


def install_pack(game_dir, pack_dir, mix_db=-14.0, progress=None, log=print, with_voice=True):
    """Installs the Ukrainian language. The text and manifest come from pack_dir (the content is downloaded separately from the application);
    the voice-over comes from pack_dir/voice (if with_voice).
    Without voice-over the language is installed with the text only, and the game keeps playing the English voices (_audiolocale=en)."""
    game.require_game_dir(game_dir)
    if not has_content(pack_dir):
        raise RuntimeError(_("Немає перекладу (manifest.json і uk/loca_uk_texts.csv) у теці з контентом. Завантажте його або вкажіть теку."))
    man = load_manifest(pack_dir)
    lang = LANG
    b = game.bundles_dir(game_dir)
    # before any change: copy next to them (D4Loc_<name>.bak) every language file that will be changed (the language name in the menu) and verify the copies
    texts.backup_files(sorted(glob.glob(os.path.join(b, "loca_*_texts.csv"))), log)
    voice = {}
    if with_voice and has_voice(pack_dir):
        voice = voice_files(pack_dir)
        log(_("Знайдено голосових файлів: {0}").format(len(voice)))
    elif with_voice:
        raise RuntimeError(_("Озвучення не знайдено в теці з контентом. Встановіть «лише текст» або завантажте озвучення."))
    en_bundles = audio_bundle_paths(game_dir, "en") if voice else []
    if voice and not en_bundles:
        raise RuntimeError(_("У грі немає англійських аудіобандлів loca_en_audio*.unity3d"))
    total = len(en_bundles) + 2
    step = 0

    def tick(msg):
        nonlocal step
        step += 1
        log(msg)
        if progress:
            progress(step, total, msg)

    tmp = tempfile.mkdtemp(prefix="d4loc_")
    try:
        for src in en_bundles:
            name = os.path.basename(src).replace("loca_en_audio", f"loca_{lang}_audio", 1)
            dst = os.path.join(tmp, name)

            def rep(alias, obj, voice=voice, mix_db=mix_db):
                path = voice.get(alias)
                if not path:
                    return None
                v, rate = _read_voice(path)
                if mix_db is not None:
                    d = audio.decode_clip(obj)
                    if d is not None and d[1] == rate:
                        v = audio.mix_original(v, d[0], rate, mix_db)
                else:
                    v = audio.limit(v * (10 ** (audio.TARGET_DB / 20) / max(audio.active_rms(v, rate), 1e-6)), rate)
                return audio.to_pcm16(v), 1, rate

            audio.build_language_bundle(src, dst, lang, rep, log=log)
            tick(_("Збережено {0}").format(name))
        # everything was built without errors: only now do we change the game folder
        for f in sorted(os.listdir(tmp)):
            shutil.move(os.path.join(tmp, f), os.path.join(b, f))
        tick(_("Бандли встановлено") if en_bundles else _("Озвучення пропущено (режим «лише текст»)"))
        target = os.path.join(b, f"loca_{lang}_texts.csv")
        if os.path.exists(target):
            texts.backup_file(target)
        shutil.copy2(text_path(pack_dir), target)
        if not voice:
            _set_audiolocale(target, "en")
        texts.register_language(b, lang, texts.UK_NAMES, texts.UK_SELF_NAME, log)
        tick(_("Текст і назву мови встановлено"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _set_audiolocale(path, locale):
    """The _audiolocale line says which voice-over to use. For "text only" we set en so that the English voice-over stays."""
    data = open(path, "rb").read().decode("utf-8-sig")
    out = []
    for line in data.split(chr(10)):
        if line.startswith("_audiolocale,"):
            cr = chr(13) if line.endswith(chr(13)) else ""
            parts = line.rstrip(chr(13)).split(",")
            parts[1] = locale
            line = ",".join(parts) + cr
        out.append(line)
    with open(path, "wb") as f:
        f.write(chr(10).join(out).encode("utf-8-sig"))


def audio_bundle_paths(game_dir, lang):
    return list_audio(game_dir, lang)


def list_audio(game_dir, lang):
    b = game.bundles_dir(game_dir)
    return sorted(p for p in glob.glob(os.path.join(b, f"loca_{lang}_audio*.unity3d")))


def uninstall(game_dir, lang=LANG, log=print):
    game.require_game_dir(game_dir)
    b = game.bundles_dir(game_dir)
    for p in glob.glob(os.path.join(b, f"loca_{lang}_audio*")) + [os.path.join(b, f"loca_{lang}_texts.csv")]:
        if os.path.isfile(p):
            os.remove(p)
            log(_("видалено {0}").format(os.path.basename(p)))
    texts.unregister_language(b, lang, log)
    for bak in glob.glob(os.path.join(b, texts.BAK_PREFIX + "loca_*" + texts.BAK_SUFFIX)):
        orig = os.path.join(b, os.path.basename(bak)[len(texts.BAK_PREFIX):-len(texts.BAK_SUFFIX)])
        if os.path.isfile(orig) and open(orig, "rb").read() == open(bak, "rb").read():
            os.remove(bak)   # the file is again exactly the same as the original: the copy is no longer needed
            log(_("Файл відновлено до оригіналу: {0}").format(os.path.basename(orig)))
    log(_("Українізацію видалено."))


def is_installed(game_dir, lang=LANG):
    b = game.bundles_dir(game_dir)
    return os.path.isfile(os.path.join(b, f"loca_{lang}_texts.csv"))


def game_durations(game_dir):
    """{line name: [durations]} from the csv companions of the game's audio bundles (one name may be in both the main and the dev bundle)."""
    out = {}
    for f in glob.glob(os.path.join(game.bundles_dir(game_dir), "loca_en_audio*.csv")):
        for line in open(f, encoding="utf-8-sig", errors="replace"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    out.setdefault(parts[0], []).append(float(parts[1]))
                except ValueError:
                    pass
    return out


def coverage(game_dir, pack_dir):
    """Compares the game content with what the translation was designed for: text keys, names and durations of the lines (independent of the version number)."""
    b = game.bundles_dir(game_dir)
    en_keys = {r[0] for r in texts.read_texts(os.path.join(b, "loca_en_texts.csv"))}
    uk_keys = {r[0] for r in texts.read_texts(text_path(pack_dir))}
    game_dur = game_durations(game_dir)
    expected = {}
    import soundfile as sf
    for name, path in voice_files(pack_dir).items():       # the duration of a line is taken from the file itself (it differs from the original by up to 25 ms)
        try:
            i = sf.info(path)
            expected[name] = [i.frames / i.samplerate]
        except Exception:
            pass
    found = [n for n in expected if n in game_dur]
    # a name may occur in several bundles (main and dev): matching any one value is enough
    changed = [n for n in found if not any(abs(g - e) <= 0.05 for g in game_dur[n] for e in expected[n])]
    return {"text_total": len(en_keys), "text_missing": len(en_keys - uk_keys), "text_extra": len(uk_keys - en_keys),
            "voice_total": len(expected), "voice_found": len(found), "voice_changed": len(changed)}


def check_compat(game_dir, pack_dir):
    """(ok, message). The game is considered compatible if the version matches OR the content does (all lines are present with the same duration
    and all text keys are translated); otherwise a warning with concrete numbers."""
    ver_ok, ver_msg = game.compare_versions(load_manifest(pack_dir).get("game"), game.version_info(game_dir))
    try:
        c = coverage(game_dir, pack_dir)
    except OSError:
        return ver_ok, ver_msg
    content_ok = c["voice_total"] > 0 and c["voice_found"] == c["voice_total"] and c["voice_changed"] == 0 and c["text_missing"] == 0
    lines = []
    if c["text_missing"]:
        lines.append(_("У грі {0} текстів, яких нема в перекладі (лишаться англійськими).").format(c['text_missing']))
    if c["text_extra"]:
        lines.append(_("У перекладі {0} ключів, яких нема у вашій грі (ігноруються).").format(c['text_extra']))
    if c["voice_total"] and c["voice_found"] < c["voice_total"]:
        lines.append(_("Не знайдено {0} з {1} реплік контенту.").format(c['voice_total'] - c['voice_found'], c['voice_total']))
    if c["voice_changed"]:
        lines.append(_("У {0} реплік тривалість оригіналу інша (озвучення може не збігатися за довжиною).").format(c['voice_changed']))
    if ver_ok:
        return True, ver_msg
    if content_ok:
        return True, ver_msg + _(" Але вміст гри збігається: усі репліки й тексти на місці, тому переклад має працювати.")
    return False, ver_msg + (" " + " ".join(lines) if lines else "")


def verify_pack(pack_dir):
    """Checks the pack folder (an unpacked content.zip or a fork): whether there are voices according to the metadata and whether the files are readable.
    Returns (state, message): 'empty' (nothing there), 'foreign' (the files do not look like a pack), 'partial', 'ok'."""
    files = voice_files(pack_dir)
    meta = os.path.join(pack_dir or "", "uk", "audio_metadata.csv")
    if not os.path.isfile(meta):
        return "empty", _("Теку не знайдено або в ній нема голосів.")
    with open(meta, encoding="utf-8-sig", newline="") as f:
        expected = {r["name"] for r in csv.DictReader(f) if r.get("name")}
    if not files:
        return "foreign", _("У теці нема голосових файлів контенту (очікуються файли в uk/audio за шляхами з uk/audio_metadata.csv).")
    missing = len(expected - set(files))
    import soundfile as sf
    bad = 0
    names = sorted(files)
    for n in names[:: max(1, len(names) // 150)]:
        try:
            if sf.info(files[n]).frames <= 0:
                bad += 1
        except Exception:
            bad += 1
    if bad:
        return "partial", _("Є пошкоджені файли (серед перевірених {0}). Завантажте озвучення заново.").format(bad)
    if missing:
        return "partial", _("Озвучення неповне: бракує {0} з {1} голосів").format(missing, len(expected)) + "."
    return "ok", _("Озвучення перевірено: {0} голосів").format(len(files)) + "."
