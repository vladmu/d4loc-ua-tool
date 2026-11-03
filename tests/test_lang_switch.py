"""The EN | UA language switcher: rebuilds the screen, remembers the choice and does not affect later runs."""
import json
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="лише Windows")


def test_language_flags(monkeypatch, tmp_path):
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("D4LOC_LANG", raising=False)
    from conftest import new_app
    from d4loc import gui, i18n
    monkeypatch.setattr(i18n, "LANG", "uk")
    try:
        app = new_app(gui)
    except tk.TclError:
        raise      # on Windows the window must always be created: a failure must be visible, not silently skipped
    try:
        app.withdraw()
        app.update()
        app.remote_done = True   # the release manifest has already been received: the new window will refresh the versions at once
        assert app.lang_var.get() == "uk"
        assert app.frame.b_tool.cget("text") == "Інструмент перекладача"
        app.set_ui_language("en")
        app.update()
        assert i18n.LANG == "en" and app.lang_var.get() == "en"
        assert app.frame.b_tool.cget("text") == "Translator tool"      # the screen was rebuilt
        saved = json.load(open(os.path.join(str(tmp_path), "D4LocToolkit", "settings.json"), encoding="utf-8"))
        assert saved["ui_lang"] == "en"
        app.set_ui_language("uk")
        app.update()
        assert app.frame.b_tool.cget("text") == "Інструмент перекладача"
        fr_en, fr_uk = app._flag_frames["en"][0], app._flag_frames["uk"][0]
        assert str(fr_uk.cget("highlightbackground")) != str(fr_en.cget("highlightbackground"))   # the active one has a frame
    finally:
        app.destroy()
        i18n.set_language("uk")


def test_project_folder_is_asked_once(monkeypatch, tmp_path, game_dir):
    """The project folder is chosen once: afterwards the tool opens at once, without questions."""
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("D4LOC_LANG", raising=False)
    fork = tmp_path / "fork"
    (fork / "uk").mkdir(parents=True)
    (fork / "uk" / "loca_uk_texts.csv").write_text("name,wording,voice,tags", encoding="utf-8")
    (fork / "manifest.json").write_text("{}", encoding="utf-8")
    os.makedirs(os.path.join(str(tmp_path), "D4LocToolkit"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "D4LocToolkit", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"game_dir": game_dir, "project_dir": str(fork)}, f)
    from conftest import new_app
    from d4loc import gui, i18n
    monkeypatch.setattr(i18n, "LANG", "uk")
    try:
        app = new_app(gui)
    except tk.TclError:
        raise      # on Windows the window must always be created: a failure must be visible, not silently skipped
    try:
        app.withdraw()
        app.update()
        monkeypatch.setattr(gui.filedialog, "askdirectory", lambda *a, **k: pytest.fail("не мало питати теку"))
        monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: pytest.fail("не мало показувати підказку"))
        went = []
        monkeypatch.setattr(app, "leave_to", lambda name: went.append(name))
        app.open_tool()
        assert went == ["tool"] and app.project_dir == str(fork)
        # the saved folder disappeared or is no longer a fork: then we ask, as the first time
        (fork / "manifest.json").unlink()
        asked = []
        monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: asked.append("info"))
        monkeypatch.setattr(gui.filedialog, "askdirectory", lambda *a, **k: asked.append("dialog") or "")
        app.open_tool()
        assert asked == ["info", "dialog"] and went == ["tool"]
    finally:
        app.destroy()
        i18n.set_language("uk")


@pytest.mark.parametrize("unlock,state", [(False, "disabled"), (True, "readonly")])
def test_target_language_selector_is_locked_by_default(monkeypatch, tmp_path, game_dir, unlock, state):
    """Choosing the target language in the translator tool is locked (uk only); it is unlocked only by a deliberate setting."""
    tk = pytest.importorskip("tkinter")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("D4LOC_LANG", raising=False)
    if unlock:
        monkeypatch.setenv("D4LOC_UNLOCK_LANGUAGES", "1")
    else:
        monkeypatch.delenv("D4LOC_UNLOCK_LANGUAGES", raising=False)
    fork = tmp_path / "fork"
    (fork / "uk").mkdir(parents=True)
    (fork / "uk" / "loca_uk_texts.csv").write_text("name,wording,voice,tags", encoding="utf-8")
    (fork / "manifest.json").write_text("{}", encoding="utf-8")
    os.makedirs(os.path.join(str(tmp_path), "D4LocToolkit"), exist_ok=True)
    with open(os.path.join(str(tmp_path), "D4LocToolkit", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"game_dir": game_dir, "project_dir": str(fork)}, f)
    from conftest import new_app
    from d4loc import gui, i18n
    monkeypatch.setattr(i18n, "LANG", "uk")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: False)
    try:
        app = new_app(gui)
    except tk.TclError:
        raise      # on Windows the window must always be created: a failure must be visible, not silently skipped
    try:
        app.withdraw()
        app.update()
        app.show("tool")
        app.update()
        cb = app.frame.tgt_cb
        assert str(cb.cget("state")) == state
        assert cb.get() == "uk" and (unlock or list(cb.cget("values")) == ["uk"])
    finally:
        app.destroy()
        i18n.set_language("uk")
