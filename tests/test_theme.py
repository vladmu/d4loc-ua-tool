"""A Windows theme change: the application reacts to the WM_SETTINGCHANGE message ("ImmersiveColorSet"), without polling the registry."""
import ctypes
import os
import sys
import time
from ctypes import wintypes

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="лише Windows")


def test_theme_switches_on_windows_message(monkeypatch):
    tk = pytest.importorskip("tkinter")
    from conftest import new_app
    from d4loc import gui
    state = {"dark": False}
    monkeypatch.setattr(gui, "system_dark", lambda: state["dark"])
    try:
        app = new_app(gui)
    except tk.TclError:
        raise      # on Windows the window must always be created: a failure must be visible, not silently skipped
    try:
        app.withdraw()
        for _i in range(200):          # the subscription appears as soon as the window has a top-level shell
            app.update()
            time.sleep(0.02)
            if app._theme_hooked:
                break
        assert app._theme_hooked
        user32 = ctypes.windll.user32
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_void_p]
        user32.GetParent.restype = wintypes.HWND
        hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()

        def send(text):
            buf = ctypes.create_unicode_buffer(text)
            user32.SendMessageW(hwnd, 0x001A, 0, ctypes.cast(buf, ctypes.c_void_p))
            for _i in range(10):
                app.update()
                time.sleep(0.02)

        state["dark"] = True
        send("intl")
        assert gui.DARK is False            # other settings are ignored
        send("ImmersiveColorSet")
        assert gui.DARK is True
        state["dark"] = False
        send("ImmersiveColorSet")
        assert gui.DARK is False
    finally:
        app.destroy()


def test_window_background_is_a_shipped_photo():
    """The background is one file inside the application (no game files are read); it is loaded once and reused."""
    from d4loc import scenery
    img = scenery.image()
    assert img is not None and img.mode == "RGB" and img.width >= 1280 and img is scenery.image()
    assert os.path.basename(scenery.FILE) == "background.jpg" and os.path.getsize(scenery.FILE) < 1_000_000      # a light file: the .exe stays small
