import json
import os
import sys

import pytest

os.environ["D4LOC_LANG"] = "uk"   # the tests check the Ukrainian messages regardless of the system language

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_ROOT, "src"), os.path.join(_ROOT, "dev")]      # the application package (src/d4loc) and the developer pipeline (dev/tools)

HEADER = "name,wording,voice,tags\r\n"


def make_game(tmp_path, with_audio_bundle=False):
    """A minimal "game": a Dungeons 4_Data/rfdata/AssetBundles folder with language CSVs."""
    g = tmp_path / "Dungeons 4"
    b = g / "Dungeons 4_Data" / "rfdata" / "AssetBundles"
    b.mkdir(parents=True)
    for lang in ("en", "ru", "de"):
        (b / f"loca_{lang}_texts.csv").write_bytes(
            (HEADER + f"_audiolocale,{lang},,\r\n_languageName_en,English,,\r\n_languageName_ru,Русский,,\r\n"
             f"_languageName_tr,Türkçe,,\r\nhello,Hello {lang},,\r\n").encode("utf-8-sig"))
    if with_audio_bundle:
        (b / "loca_en_audio.unity3d").write_bytes(b"not a real bundle")
    return str(g)


@pytest.fixture
def game_dir(tmp_path):
    return make_game(tmp_path)


VOICE_NAMES = [f"dlg_test_line_{i:02d}" for i in range(40)]


def make_voice(pack, names):
    """Voices in the fork/pack structure: uk/audio/<bundle path>.ogg + uk/audio_metadata.csv (key -> path)."""
    import numpy as np
    from d4loc import oggenc
    uk = os.path.join(pack, "uk")
    os.makedirs(os.path.join(uk, "audio", "assets", "audio", "uk"), exist_ok=True)
    rows = ["bundle,name,wording,file_id,file_path,container_path,path_id,md5"]
    for i, n in enumerate(names):
        cp = f"assets/audio/uk/{n}.wav"
        oggenc.write_opus(os.path.join(uk, "audio", "assets", "audio", "uk", n + ".ogg"), np.zeros(4800, dtype="int16"), 48000)
        rows.append(f"loca_uk_audio.unity3d,{n},,{i},,{cp},{i},")
    with open(os.path.join(uk, "audio_metadata.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("\r\n".join(rows) + "\r\n")


@pytest.fixture
def content_pack(tmp_path):
    """A content pack folder (an unpacked content.zip or a fork): manifest.json and uk/loca_uk_texts.csv; no voices."""
    d = tmp_path / "uk_pack"
    (d / "uk").mkdir(parents=True)
    (d / "uk" / "loca_uk_texts.csv").write_bytes(
        (HEADER + "_audiolocale,uk,,\r\n_languageName_uk,Українська (Ukrainian),,\r\nhello,Привіт,,\r\n").encode("utf-8-sig"))
    (d / "manifest.json").write_text(json.dumps({"lang": "uk", "version": "1.0.0", "voices": len(VOICE_NAMES),
                                                 "game": {"build": "abcdef0123456789", "release": "v1"}}), encoding="utf-8")
    return str(d)


def new_app(gui, tries=6):
    """tkinter sometimes fails to create a second window in the same process right after the first was destroyed: retry briefly before giving up."""
    import time
    import tkinter
    for i in range(tries):
        try:
            return gui.App()
        except tkinter.TclError:
            if i == tries - 1:
                raise
            time.sleep(0.4)
