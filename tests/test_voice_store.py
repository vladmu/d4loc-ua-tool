"""Voice storage of the developer pipeline: the Opus file in content/ is the single source; community-edited files are left alone;
the index of the voices is derived from the English originals unpacked in content/en/."""
import csv
import json
import os

import numpy as np

from d4loc.project import META_FIELDS
from tools import paths
from tools.game import index
from tools.voice import store


def tone(seconds=0.3, rate=24000):
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate


def test_write_clip_makes_opus_and_decide_follows_state(tmp_path):
    dst = str(tmp_path / "audio" / "assets" / "uk" / "dlg_a.ogg")
    assert store.decide(dst, None, "s1") == "make"                         # nothing there yet
    a, rate = tone()
    sha = store.write_clip(dst, a, rate)
    assert os.path.isfile(dst) and sha == store.sha(dst)
    assert store.decide(dst, "s1", "s1") == "same"                          # up to date
    assert store.decide(dst, "s1", "s2") == "make"                          # the inputs changed
    assert store.decide(dst, "s1", "s1", force=True) == "make"
    assert store.decide(dst, "s1", "s2", recorded=True) == "community"      # a person's recording is not overwritten even though the text changed
    assert store.decide(dst, "s1", "s2", recorded=True, force=True) == "make"


def test_state_lives_in_a_small_sorted_csv(tmp_path):
    path = str(tmp_path / "uk" / "voice_state.csv")
    store.save_state(path, {"b": "sig-b", "a": "sig-a"})
    assert open(path, encoding="utf-8-sig", newline="").read().split(chr(10)) == ["name,sig", "a,sig-a", "b,sig-b", ""]      # LF, sorted: small diffs in a pull request
    assert store.load_state(path) == {"a": "sig-a", "b": "sig-b"}
    assert store.load_state(str(tmp_path / "none.csv")) == {}


def point_paths_at(monkeypatch, content):
    for name, rel in (("CONTENT", ""), ("CONTENT_UK", "uk"), ("CONTENT_AUDIO", "uk/audio"), ("CONTENT_META", "uk/audio_metadata.csv"),
                      ("CONTENT_MANIFEST", "manifest.json"), ("CONTENT_EN", "en"), ("EN_META", "en/audio_metadata.csv"), ("EN_AUDIO", "en/audio")):
        monkeypatch.setattr(paths, name, os.path.join(str(content), *rel.split("/")) if rel else str(content))
    monkeypatch.setattr(index.game, "find_game_dir", lambda: None)


def english_original(content, names):
    """What the translator tool unpacks into content/en/: metadata with English bundle and path names, plus the service files."""
    base = content / "en" / "audio" / "assets" / "audio" / "en.dlc_gloom"
    base.mkdir(parents=True)
    (base / "audiodef.txt").write_text("alias: a\n", encoding="utf-8")
    (base / "audioindex.txt").write_text("index\n", encoding="utf-8")
    with open(content / "en" / "audio_metadata.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=META_FIELDS)
        w.writeheader()
        for i, n in enumerate(names):
            w.writerow({"bundle": "loca_en_audio.dlc_gloom.unity3d", "name": n, "wording": "English text", "file_id": f"id{i}", "file_path": "C:/somewhere/else.wav",
                        "container_path": f"assets/audio/en.dlc_gloom/2025/{n}.wav", "path_id": str(i), "md5": "m"})


def test_uk_rows_are_derived_from_the_english_unpack(tmp_path, monkeypatch):
    content = tmp_path / "content"
    point_paths_at(monkeypatch, content)
    english_original(content, ["dlg_a", "dlg_b"])
    rows = index.uk_rows()
    assert rows[0]["bundle"] == "loca_uk_audio.dlc_gloom.unity3d"
    assert rows[0]["container_path"] == "assets/audio/uk.dlc_gloom/2025/dlg_a.wav"      # only the language part of the names changes
    assert rows[0]["file_id"] == "id0" and rows[0]["path_id"] == "0"                     # the identifiers stay the same
    assert rows[0]["en_wav"].endswith(os.path.join("en", "audio", "assets", "audio", "en.dlc_gloom", "2025", "dlg_a.wav"))   # taken from content/en, not from the stored absolute path


def test_index_lists_only_lines_that_have_a_voice(tmp_path, monkeypatch):
    content = tmp_path / "content"
    point_paths_at(monkeypatch, content)
    english_original(content, ["dlg_a", "dlg_b"])
    rows = index.uk_rows()
    a, rate = tone()
    store.write_clip(index.voice_file(rows[0]["container_path"]), a, rate)       # only dlg_a has a voice
    summary = index.sync(rows, version="0.2.0")
    assert "voices 1 of 2" in summary and "service files 2" in summary
    meta = list(csv.DictReader(open(paths.CONTENT_META, encoding="utf-8-sig", newline="")))
    assert [r["name"] for r in meta] == ["dlg_a"] and meta[0]["file_path"] == "" and meta[0]["wording"] == ""   # no local paths, no English text
    assert meta[0]["bundle"] == "loca_uk_audio.dlc_gloom.unity3d"
    man = json.load(open(paths.CONTENT_MANIFEST, encoding="utf-8"))
    assert man["version"] == "0.2.0" and man["voices"] == 1
    assert (content / "uk" / "audio" / "assets" / "audio" / "uk.dlc_gloom" / "audiodef.txt").read_text(encoding="utf-8") == "alias: a\n"   # copied into the uk folder
