"""The index of the content repository's voices: uk/audio_metadata.csv, the bundles' audiodef.txt / audioindex.txt and manifest.json.

The Ogg Opus voices themselves are written by `voice` (see tools/voice/store.py); this module keeps the files that describe them
in step with the game. Everything is derived from the English originals that the translator tool (or `extract`) unpacks into
content/en/: the Ukrainian language is a clone of the English bundles, so a line's key, file_id and path_id are the same and only the
names change (loca_en_audio* -> loca_uk_audio*, assets/audio/en* -> assets/audio/uk*); the audiodef/audioindex files are identical.

  content/uk/audio/<bundle path>   audiodef.txt and audioindex.txt of every bundle
  content/uk/audio_metadata.csv    line key -> bundle and path, only for lines that have a voice file (no local paths, no English text)
  content/manifest.json            content version, number of voices, version of the game the content was made for
"""
import csv
import json
import os
import re
import shutil

from d4loc import game
from d4loc.project import META_FIELDS
from tools import paths


def uk_container(container_path):
    return re.sub(r"^assets/audio/en", "assets/audio/uk", container_path.replace("\\", "/"))


def uk_bundle(bundle):
    return bundle.replace("loca_en_audio", "loca_uk_audio")


def voice_file(container_path):
    """Where the Ukrainian voice of a line (by its uk container path) lives in the content repository."""
    return os.path.join(paths.CONTENT_AUDIO, os.path.splitext(container_path)[0] + ".ogg")


def uk_rows(meta_path=None):
    """The lines of the game that can be voiced: [{bundle, name, file_id, path_id, container_path (uk), en_wav (the English original)}]."""
    meta_path = meta_path or paths.EN_META
    if not os.path.isfile(meta_path):
        raise SystemExit(f"Нема {meta_path}: спершу python dev/run.py extract (або відкрийте теку content як проєкт в інструменті перекладача)")
    out = []
    with open(meta_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            cp = r["container_path"].replace("\\", "/")
            out.append({"bundle": uk_bundle(r["bundle"]), "name": r["name"], "file_id": r["file_id"], "path_id": r["path_id"],
                        "container_path": uk_container(cp), "en_wav": os.path.normpath(os.path.join(paths.EN_AUDIO, os.path.splitext(cp)[0] + ".wav"))})
    return out


def sync(rows=None, version=None, game_dir=None):
    """Brings the index, the service files and the manifest in step with the voice files that are really in content/uk/audio. Returns a summary."""
    rows = rows if rows is not None else uk_rows()
    system = 0
    for dirpath, _d, files in os.walk(paths.EN_AUDIO):
        for fn in files:
            if fn in ("audiodef.txt", "audioindex.txt"):
                rel = os.path.relpath(os.path.join(dirpath, fn), paths.EN_AUDIO).replace(os.sep, "/")
                dst = os.path.join(paths.CONTENT_AUDIO, uk_container(rel))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(os.path.join(dirpath, fn), dst)
                system += 1
    have = [r for r in rows if os.path.isfile(voice_file(r["container_path"]))]
    os.makedirs(paths.CONTENT_UK, exist_ok=True)
    with open(paths.CONTENT_META, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=META_FIELDS, lineterminator="\n")
        w.writeheader()
        for r in have:
            w.writerow({"bundle": r["bundle"], "name": r["name"], "wording": "", "file_id": r["file_id"], "file_path": "",
                        "container_path": r["container_path"], "path_id": r["path_id"], "md5": ""})
    man = json.load(open(paths.CONTENT_MANIFEST, encoding="utf-8")) if os.path.isfile(paths.CONTENT_MANIFEST) else {}
    gd = game_dir or game.find_game_dir()
    man = {"version": version or man.get("version", "0.1.0"), "voices": len(have),
           "game": {k: v for k, v in game.version_info(gd).items() if k != "label"} if gd else man.get("game", {})}
    with open(paths.CONTENT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return f"voices {len(have)} of {len(rows)}, service files {system}, manifest version {man['version']}"
