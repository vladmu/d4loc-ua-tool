"""The translator project = a fork of the content repository: folder check, laying out a release, voices as .ogg, the toolcheck.json stamp."""
import io
import json
import os
import zipfile

import numpy as np
import pytest
import soundfile as sf

from d4loc import oggenc, repo, toolcheck, validate, texts, install

TEXTS = "name,wording,voice,tags\r\n_audiolocale,uk,,\r\nhello,Привіт,,\r\ndlg_a_01,Гей! *зітхає*,thalya,\r\n"
META = ("bundle,name,wording,file_id,file_path,container_path,path_id,md5\r\n"
        "loca_uk_audio.unity3d,dlg_a_01,,abc,,assets/audio/uk/abc.wav,1,\r\n")


def tone(seconds=0.5, rate=48000):
    t = np.arange(int(seconds * rate)) / rate
    return (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16), rate


@pytest.fixture
def fork(tmp_path):
    p = tmp_path / "fork"
    (p / "uk" / "audio" / "assets" / "audio" / "uk").mkdir(parents=True)
    (p / "uk" / "loca_uk_texts.csv").write_bytes(TEXTS.encode("utf-8-sig"))
    (p / "uk" / "audio_metadata.csv").write_bytes(META.encode("utf-8-sig"))
    (p / "manifest.json").write_text(json.dumps({"lang": "uk", "version": "0.1.0"}), encoding="utf-8")
    data, rate = tone()
    oggenc.write_opus(str(p / "uk" / "audio" / "assets" / "audio" / "uk" / "abc.ogg"), data, rate)
    return p


def test_inspect_folder_kinds(tmp_path, fork):
    assert repo.inspect_folder("")[0] == "missing"
    assert repo.inspect_folder(str(tmp_path / "нема"))[0] == "missing"
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    assert repo.inspect_folder(str(f))[0] == "not_dir"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert repo.inspect_folder(str(empty))[0] == "empty"
    (empty / ".git").mkdir()                                  # only .git: still empty
    assert repo.inspect_folder(str(empty))[0] == "empty"
    other = tmp_path / "other"
    other.mkdir()
    (other / "readme.md").write_text("чужа тека", encoding="utf-8")
    assert repo.inspect_folder(str(other))[0] == "foreign"
    assert repo.inspect_folder(str(fork)) == ("content", "")


def test_remote_name_warning(fork):
    git = fork / ".git"
    git.mkdir()
    (git / "config").write_text('[remote "origin"]\n\turl = https://github.com/someone/other-project.git\n')
    kind, msg = repo.inspect_folder(str(fork))
    assert kind == "content" and "other-project" in msg
    (git / "config").write_text('[remote "origin"]\n\turl = https://github.com/me/d4loc-ua-content.git\n')
    assert repo.inspect_folder(str(fork)) == ("content", "")


def test_git_exclude_keeps_english_out_of_commits(fork):
    assert repo.ensure_git_exclude(str(fork)) is False        # not a git folder: nothing is done
    (fork / ".git").mkdir()
    assert repo.ensure_git_exclude(str(fork)) is True
    repo.ensure_git_exclude(str(fork))                        # a repeated call does not duplicate entries
    lines = (fork / ".git" / "info" / "exclude").read_text().split()
    assert lines.count("/en/") == 1 and "pending/" in lines


def test_populate_from_release_zip_blocks_traversal(tmp_path):
    z = tmp_path / "rel.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("uk/loca_uk_texts.csv", TEXTS)
        zf.writestr("manifest.json", "{}")
    dst = tmp_path / "proj"
    repo.populate_from_release(str(dst), source=str(z), log=lambda m: None)
    assert (dst / "uk" / "loca_uk_texts.csv").is_file() and (dst / "manifest.json").is_file()
    assert repo.inspect_folder(str(dst))[0] == "content"
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("ok.txt", "x")
        zf.writestr("../evil.txt", "x")
    with pytest.raises(RuntimeError):
        repo.populate_from_release(str(tmp_path / "p2"), source=str(bad), log=lambda m: None)
    assert not (tmp_path / "evil.txt").exists()


def test_opus_roundtrip_is_readable_with_exact_enough_duration():
    for n in (38833, 42773, 41792, 44638, 48000):            # lengths at which libsndfile used to consider the file damaged
        data = (np.random.RandomState(n).randn(n) * 3000).astype(np.int16)
        blob, rate = oggenc.encode_opus(data, 48000)
        x, xsr = sf.read(io.BytesIO(blob), dtype="int16")
        assert xsr == 48000 and 0 <= (len(x) - n) / 48000 <= 0.021


def test_opus_resamples_unsupported_rates():
    data, _ = tone(0.4, 44100)
    blob, rate = oggenc.encode_opus(data, 44100)
    assert rate == 48000
    x, xsr = sf.read(io.BytesIO(blob), dtype="int16")
    assert xsr == 48000 and abs(len(x) / 48000 - 0.4) < 0.03


def test_clip_lookup_and_store_replaces_old_file(fork):
    ld = str(fork / "uk")
    old = repo.clip_path(ld, "assets/audio/uk/abc.wav")
    assert old.endswith("abc.ogg") and os.path.isfile(old)
    assert repo.clip_path(ld, "assets/audio/uk/нема.wav") == ""
    wav = fork / "new.wav"
    data, rate = tone(0.3, 44100)
    sf.write(str(wav), data, rate, subtype="PCM_16")
    rel = repo.store_clip(ld, "assets/audio/uk/abc.wav", str(wav))
    assert rel == "uk/audio/assets/audio/uk/abc.ogg"
    x, xsr = sf.read(repo.clip_path(ld, "assets/audio/uk/abc.wav"), dtype="int16")
    assert abs(len(x) / xsr - 0.3) < 0.03                    # the new line became .ogg in place of the old one


def test_voice_files_reads_fork_tree(fork):
    files = install.voice_files(str(fork))
    assert set(files) == {"dlg_a_01"} and files["dlg_a_01"].endswith("abc.ogg")
    assert install.text_path(str(fork)).endswith(os.path.join("uk", "loca_uk_texts.csv"))
    assert install.has_content(str(fork)) is True              # manifest.json and uk/loca_uk_texts.csv are in place


def test_validate_rules():
    assert validate.check_text("dlg_a", "Привіт *зітхає") [0]
    assert validate.check_text("ui_a", "Ок {a")[0]
    assert validate.check_text("ui_a", "Ок <b>текст")[0]
    assert validate.check_text("ui_a", "Ок <sprite name=x> гроші")[0] == []
    assert validate.check_text("ui_a", "ы")[0]
    assert validate.check_text("res_a", "Золоті жили ")[1] == []          # a space at the edge in res_* is part of the value
    assert validate.check_rows([("a", "x", "", ""), ("a", "y", "", "")])[0][2] == "ключ повторюється"


def test_toolcheck_stamp_detects_tampering(fork):
    data = toolcheck.write(str(fork))
    assert data["tool"]["sha256"] == "source" and set(data["files"]) >= {"uk/loca_uk_texts.csv", "manifest.json", "uk/audio_metadata.csv"}
    assert toolcheck.verify(str(fork)) == []
    # a text change after the stamp
    (fork / "uk" / "loca_uk_texts.csv").write_bytes(TEXTS.replace("Привіт", "Вітаю").encode("utf-8-sig"))
    assert "змінено" in toolcheck.verify(str(fork))[0]
    toolcheck.write(str(fork))
    assert toolcheck.verify(str(fork)) == []
    # a voice was added or substituted
    clip = fork / "uk" / "audio" / "assets" / "audio" / "uk" / "extra.ogg"
    clip.write_bytes(b"x")
    assert "додано 1" in toolcheck.verify(str(fork))[0]
    clip.unlink()
    # a stamp from an unknown application
    assert any("невідомим" in p for p in toolcheck.verify(str(fork), known_tool_hashes={"deadbeef"}))
    assert toolcheck.verify(str(fork), known_tool_hashes={"source"}) != []     # "source" is never considered a release


def test_toolcheck_refuses_when_translation_has_errors(fork):
    (fork / "uk" / "loca_uk_texts.csv").write_bytes("name,wording,voice,tags\r\nui_a,ы,,\r\n".encode("utf-8-sig"))
    with pytest.raises(toolcheck.ToolcheckError):
        toolcheck.write(str(fork))
    assert not (fork / "toolcheck.json").exists()
    assert toolcheck.verify(str(fork))[0].startswith("Нема toolcheck.json")


def test_missing_stamp_is_reported(fork):
    assert "Нема toolcheck.json" in toolcheck.verify(str(fork))[0]
    (fork / "toolcheck.json").write_text("не json", encoding="utf-8")
    assert "пошкоджений" in toolcheck.verify(str(fork))[0]


def test_save_writes_project_and_never_touches_the_game(fork, game_dir, tmp_path, monkeypatch):
    """"Save" writes only into the fork project (the same file, no transformation) and nothing into the game: installation happens only in the installer window."""
    from d4loc import game, project
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    proj = str(fork)
    b = game.bundles_dir(game_dir)
    before = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b)}
    project.save_pending_texts(proj, "uk", {"hello": "Вітаю, мандрівнику"})
    wav = tmp_path / "rec.wav"
    data, rate = tone(0.3, 44100)
    sf.write(str(wav), data, rate, subtype="PCM_16")
    project.stage_audio(proj, "uk", "dlg_a_01", str(wav))
    assert project.save(proj, "uk", log=lambda m: None) == (1, 1)
    rows = {r[0]: r[1] for r in texts.read_texts(os.path.join(proj, "uk", "loca_uk_texts.csv"))}
    assert rows["hello"] == "Вітаю, мандрівнику" and rows["dlg_a_01"] == "Гей! *зітхає*"     # the rest of the lines are untouched
    clip = repo.clip_path(os.path.join(proj, "uk"), "assets/audio/uk/abc.wav")
    x, xsr = sf.read(clip, dtype="int16")
    assert clip.endswith(".ogg") and abs(len(x) / xsr - 0.3) < 0.03                          # the new line became .ogg in place of the old one
    assert project.load_pending_texts(proj, "uk") == {} and project.list_pending_audio(proj, "uk") == []
    after = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b)}
    assert after == before                                                                  # no changes in the game folder, no .bak files
    assert not os.path.exists(os.path.join(proj, ".d4loc"))                                  # no intermediate folders
