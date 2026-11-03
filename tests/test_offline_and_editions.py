"""Two executables: the Toolkit (installer and translator tool) and the players' Installer (no translator tool). Both can install from the release
files that lie next to them, without the internet; without those files the content is downloaded from the repository, as before."""
import os
import shutil
import sys

import pytest

from d4loc import download, edition, install

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="лише Windows")


@pytest.fixture
def beside_exe(tmp_path, content_pack):
    """A folder as a player gets it: the three files of the content release lie next to the program."""
    from conftest import VOICE_NAMES, make_voice
    make_voice(content_pack, VOICE_NAMES[:6])
    folder = tmp_path / "next_to_exe"
    download.build_release(content_pack, str(folder))
    return folder


def test_release_files_next_to_the_program_are_used_without_the_network(beside_exe, tmp_path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("the internet must not be used when the release files lie next to the program")
    monkeypatch.setattr(download, "_open", no_network)
    rel = download.fetch_release(local_dir=str(beside_exe))
    assert rel["local"] == str(beside_exe) and rel["manifest"]["version"]
    assert set(rel["assets"]) == set(download.ASSETS)
    dest = tmp_path / "temp_pack"
    download.download_content(rel, str(dest), with_voice=True, log=lambda m: None)
    assert install.has_content(str(dest)) and len(install.voice_files(str(dest))) == 6 and install.verify_pack(str(dest))[0] == "ok"
    assert sorted(os.listdir(beside_exe)) == sorted(download.ASSETS)          # the player's files are untouched: only copies were used


def test_text_next_to_the_program_and_no_internet_means_text_only(beside_exe, tmp_path, monkeypatch):
    os.remove(beside_exe / "voice.zip")
    monkeypatch.setattr(download, "_remote_release", lambda timeout, repo=None: None)          # no internet
    rel = download.fetch_release(local_dir=str(beside_exe))
    assert rel["local"] and download.VOICE_ASSET not in rel["assets"]               # no voices: the window offers the text only
    assert download.download_size(rel, with_voice=False) == 0                       # nothing has to be downloaded
    dest = tmp_path / "temp_pack"
    download.download_content(rel, str(dest), with_voice=False, log=lambda m: None)
    assert install.has_content(str(dest)) and not install.has_voice(str(dest))


def test_a_missing_voice_zip_is_downloaded_if_it_belongs_to_the_same_content(beside_exe, monkeypatch):
    """Per file: the text lies next to the program and is copied, the voices are not there and come from the repository (the same content version only)."""
    voice_url = {"size": 139_000_000, "url": "https://example.invalid/voice.zip", "sha256": "abc"}
    version = download.local_release(str(beside_exe))["manifest"]["version"]
    os.remove(beside_exe / "voice.zip")
    monkeypatch.setattr(download, "_remote_release", lambda timeout, repo=None: {"manifest": {"version": version}, "assets": {download.VOICE_ASSET: voice_url}})
    rel = download.fetch_release(local_dir=str(beside_exe))
    assert download.is_local(rel["assets"][download.TEXT_ASSET]) and not download.is_local(rel["assets"][download.VOICE_ASSET])
    assert download.download_size(rel, with_voice=True) == 139_000_000 and download.download_size(rel, with_voice=False) == 0
    monkeypatch.setattr(download, "_remote_release", lambda timeout, repo=None: {"manifest": {"version": "99.0.0"}, "assets": {download.VOICE_ASSET: voice_url}})
    assert download.VOICE_ASSET not in download.fetch_release(local_dir=str(beside_exe))["assets"]      # voices of another version are never mixed with this text


def test_without_the_files_the_release_comes_from_the_repository(tmp_path, monkeypatch):
    folder = tmp_path / "empty"
    folder.mkdir()
    assert download.local_release(str(folder)) is None
    (folder / "manifest.json").write_text("{}", encoding="utf-8")               # the text is missing too: still not a release
    assert download.local_release(str(folder)) is None
    asked = []
    monkeypatch.setattr(download, "_release_info", lambda timeout, repo=None: asked.append(timeout))
    assert download.fetch_release(local_dir=str(folder)) is None and asked        # fell through to the network


def test_the_installer_has_no_translator_tool_and_the_toolkit_has(monkeypatch, tmp_path, game_dir):
    tk = pytest.importorskip("tkinter")
    from conftest import new_app
    from d4loc import gui, i18n
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(i18n, "LANG", "uk")
    monkeypatch.setattr(gui.download, "fetch_release", lambda timeout=15, local_dir=None: None)
    for translator in (True, False):
        monkeypatch.setattr(edition, "TRANSLATOR", translator)
        app = new_app(gui)
        try:
            app.withdraw()
            app.update()
            assert (app.frame.b_tool is not None) is translator
            assert (edition.app_name() in app.title()) and (("Installer" in app.title()) is (not translator))
        finally:
            app.destroy()


def test_the_players_installer_never_uses_a_translator_project(content_pack, monkeypatch):
    """The Toolkit installs the content of its project folder; the players' Installer has no project at all, so it ignores one even if it exists."""
    from d4loc import gui
    monkeypatch.setattr(edition, "TRANSLATOR", True)
    assert gui.local_pack(str(content_pack)) == str(content_pack)
    monkeypatch.setattr(edition, "TRANSLATOR", False)
    assert gui.local_pack(str(content_pack)) is None
