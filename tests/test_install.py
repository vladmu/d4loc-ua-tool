import os
import shutil

import pytest

from d4loc import game, install, texts


def test_content_pack_detection(content_pack, tmp_path):
    assert install.has_content(content_pack)
    assert not install.has_content(str(tmp_path / "nothing"))
    assert not install.has_content(None)
    man = install.load_manifest(content_pack)
    assert man["lang"] == "uk" and man["game"].get("build")


def test_install_without_content_fails_clearly(game_dir, tmp_path):
    with pytest.raises(RuntimeError, match="Немає перекладу"):
        install.install_pack(game_dir, str(tmp_path / "empty"), None, with_voice=False, log=lambda m: None)


def test_text_only_install_and_uninstall(game_dir, content_pack, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    install.install_pack(game_dir, content_pack, None, with_voice=False, log=lambda m: None)
    b = game.bundles_dir(game_dir)
    uk = open(os.path.join(b, "loca_uk_texts.csv"), "rb").read().decode("utf-8-sig")
    assert "_audiolocale,en" in uk  # without voice-over the game keeps the English voices
    assert not [f for f in os.listdir(b) if "audio" in f]
    assert install.is_installed(game_dir)
    for lang in ("en", "ru", "de"):
        assert texts.has_language_name(os.path.join(b, f"loca_{lang}_texts.csv"), "uk")
    install.uninstall(game_dir, log=lambda m: None)
    assert not install.is_installed(game_dir)
    assert not texts.has_language_name(os.path.join(b, "loca_en_texts.csv"), "uk")


def test_install_with_voice_but_no_pack_fails_clearly(game_dir, content_pack):
    with pytest.raises(RuntimeError, match="Озвучення не знайдено"):
        install.install_pack(game_dir, content_pack, -14.0, log=lambda m: None)


def test_set_audiolocale_keeps_other_rows(tmp_path):
    p = tmp_path / "t.csv"
    p.write_bytes("name,wording,voice,tags\r\n_audiolocale,uk,,\r\nx,Привіт,,\r\n".encode("utf-8-sig"))
    install._set_audiolocale(str(p), "en")
    out = p.read_bytes().decode("utf-8-sig")
    assert "_audiolocale,en,," in out and "x,Привіт,," in out


def test_verify_pack_states(tmp_path):
    from conftest import VOICE_NAMES, make_voice
    empty = str(tmp_path / "empty")
    os.makedirs(empty)
    assert install.verify_pack(empty)[0] == "empty"                         # no metadata
    foreign = str(tmp_path / "foreign")
    make_voice(foreign, VOICE_NAMES[:5])
    for f in os.listdir(os.path.join(foreign, "uk", "audio", "assets", "audio", "uk")):
        os.remove(os.path.join(foreign, "uk", "audio", "assets", "audio", "uk", f))
    assert install.verify_pack(foreign)[0] == "foreign"                     # metadata exists, files do not
    partial = str(tmp_path / "partial")
    make_voice(partial, VOICE_NAMES)
    os.remove(os.path.join(partial, "uk", "audio", "assets", "audio", "uk", VOICE_NAMES[0] + ".ogg"))
    state, msg = install.verify_pack(partial)
    assert state == "partial" and "бракує 1 з 40" in msg
    full = str(tmp_path / "full")
    make_voice(full, VOICE_NAMES)
    assert install.verify_pack(full)[0] == "ok"
    bad = str(tmp_path / "bad")
    make_voice(bad, VOICE_NAMES)
    open(os.path.join(bad, "uk", "audio", "assets", "audio", "uk", VOICE_NAMES[1] + ".ogg"), "wb").write(b"not an ogg")
    assert install.verify_pack(bad)[0] == "partial"                         # a damaged file


def test_backups_live_next_to_originals(game_dir, content_pack, tmp_path, monkeypatch):
    """The copy lies next to the original as D4Loc_<name>.bak (the game will not take it for a language file), and the original is unchanged after a repeated installation."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    b = game.bundles_dir(game_dir)
    original = open(os.path.join(b, "loca_en_texts.csv"), "rb").read()
    install.install_pack(game_dir, content_pack, None, with_voice=False, log=lambda m: None)
    bak = os.path.join(b, "D4Loc_loca_en_texts.csv.bak")
    assert open(bak, "rb").read() == original                                      # the original itself
    assert open(os.path.join(b, "loca_en_texts.csv"), "rb").read() != original     # and in the game it is already modified
    install.install_pack(game_dir, content_pack, None, with_voice=False, log=lambda m: None)
    assert open(bak, "rb").read() == original                                      # a repeated installation does not overwrite the original
    assert not os.path.exists(os.path.join(game_dir, "D4Loc_backup"))              # there is no separate folder in the game
    assert not os.path.exists(tmp_path / "appdata" / "D4LocToolkit" / "backup")    # nothing is written to the user profile
    # the game looks for loca_*_texts.csv: the copies do not end up there, and our own searches do not see them either
    assert all(not f.startswith("loca_") for f in os.listdir(b) if f.endswith(".bak"))
    assert set(game.list_languages(game_dir)) == {"en", "ru", "de", "uk"}


def test_backup_failure_leaves_game_untouched(game_dir, content_pack, tmp_path, monkeypatch):
    """First copies of all the files, and only then the change: if a copy fails, no game file is changed."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    b = game.bundles_dir(game_dir)
    before = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b)}

    def boom(src, dst, **kw):
        raise OSError("диск повний")
    monkeypatch.setattr(texts.shutil, "copy2", boom)
    with pytest.raises(OSError):
        install.install_pack(game_dir, content_pack, None, with_voice=False, log=lambda m: None)
    after = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b)}
    assert after == before    # neither language names nor loca_uk_texts.csv


def test_inexact_backup_is_rejected(tmp_path, monkeypatch):
    src = tmp_path / "a.csv"
    src.write_bytes(b"original")

    def bad_copy(s, d, **kw):
        open(d, "wb").write(b"broken")
    monkeypatch.setattr(texts.shutil, "copy2", bad_copy)
    with pytest.raises(RuntimeError, match="точну резервну копію"):
        texts.backup_file(str(src))
    assert not os.path.exists(texts.backup_path(str(src)))


def test_all_language_files_backed_up_before_patch(game_dir, content_pack, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    b = game.bundles_dir(game_dir)
    originals = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b) if f.endswith("_texts.csv")}
    install.install_pack(game_dir, content_pack, None, with_voice=False, log=lambda m: None)
    for f, data in originals.items():
        assert open(os.path.join(b, texts.backup_path(f)), "rb").read() == data, f   # the original of every changed file lies next to it


def test_uninstall_restores_originals_and_removes_backups(game_dir, content_pack, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    b = game.bundles_dir(game_dir)
    originals = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b)}
    install.install_pack(game_dir, content_pack, None, with_voice=False, log=lambda m: None)
    assert any(f.endswith(".bak") for f in os.listdir(b))
    install.uninstall(game_dir, log=lambda m: None)
    after = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b)}
    assert after == originals          # byte for byte as before the installation, no extra files (the .bak files are removed too)


def test_local_pack_is_project_with_content_else_none(content_pack, tmp_path):
    from d4loc import gui
    assert gui.local_pack(str(tmp_path / "nothing")) is None
    assert gui.local_pack(str(content_pack)) == str(content_pack)
