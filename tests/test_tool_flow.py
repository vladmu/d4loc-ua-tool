"""The translator tool: "Save and install" leads to the installer window, "Save" only writes into the project; the tool writes nothing into the game."""
import json
import os
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="лише Windows")


@pytest.fixture
def tool_app(monkeypatch, tmp_path, game_dir):
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("D4LOC_LANG", raising=False)
    fork = tmp_path / "fork"
    (fork / "uk").mkdir(parents=True)
    (fork / "uk" / "loca_uk_texts.csv").write_text("name,wording,voice,tags" + chr(13) + chr(10) + "hello,Привіт,," + chr(13) + chr(10), encoding="utf-8")
    (fork / "manifest.json").write_text("{}", encoding="utf-8")
    os.makedirs(os.path.join(str(tmp_path), "D4LocToolkit"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "D4LocToolkit", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"game_dir": game_dir, "project_dir": str(fork)}, f)
    from conftest import new_app
    from d4loc import gui, i18n
    monkeypatch.setattr(i18n, "LANG", "uk")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui.download, "fetch_release", lambda timeout=15: None)   # nothing is downloaded in the test
    try:
        app = new_app(gui)
    except tk.TclError:
        raise      # on Windows the window must always be created: a failure must be visible, not silently skipped
    app.withdraw()
    app.update()
    yield app, fork, gui
    app.destroy()
    i18n.set_language("uk")


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def test_three_buttons_and_install_goes_through_installer_window(tool_app, monkeypatch):
    app, fork, gui = tool_app
    called = []
    monkeypatch.setattr(gui.InstallFrame, "do_install", lambda self, confirm=True: called.append(("install", confirm)))
    app.show("tool")
    end = time.time() + 15
    while time.time() < end and app.frame.b_save_install.instate(["disabled"]):
        pump(app, 0.1)       # the window is locked while the pack is loaded and unpacked: wait for that to finish
    f = app.frame
    assert [str(b.cget("text")) for b in (f.b_save_install, f.b_save, f.b_disc)] == ["Зберегти й встановити", "Зберегти", "Скасувати"]
    assert f.b_save.instate(["disabled"]) and f.b_disc.instate(["disabled"])        # no changes: there is nothing to save or cancel
    assert not f.b_save_install.instate(["disabled"])                               # but the project can always be installed into the game
    f.save(install_after=True)
    end = time.time() + 8
    while time.time() < end and not called:      # the transition and the start happen asynchronously: we wait instead of guessing the time
        pump(app, 0.1)
    assert isinstance(app.frame, gui.InstallFrame) and called == [("install", False)]      # we moved to the installer window and started its normal dialog


def test_save_only_writes_project(tool_app, tmp_path, game_dir):
    from d4loc import game
    app, fork, gui = tool_app
    b = game.bundles_dir(game_dir)
    before = {n: open(os.path.join(b, n), "rb").read() for n in os.listdir(b)}
    app.show("tool")
    pump(app, 1.0)
    f = app.frame
    f.pend_t["hello"] = "Вітаю"
    from d4loc import project
    project.save_pending_texts(str(fork), "uk", f.pend_t)
    f.save()
    end = time.time() + 10
    while time.time() < end and not (fork / "toolcheck.json").is_file():     # saving runs in a background thread: we wait for the result
        pump(app, 0.1)
    pump(app, 0.3)
    assert "Вітаю" in (fork / "uk" / "loca_uk_texts.csv").read_text(encoding="utf-8")
    assert (fork / "toolcheck.json").is_file()                                      # the verification stamp was written
    assert isinstance(app.frame, gui.ToolFrame)                                     # we stayed in the tool
    assert {n: open(os.path.join(b, n), "rb").read() for n in os.listdir(b)} == before   # nothing changed in the game
