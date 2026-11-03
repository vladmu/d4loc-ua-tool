"""Entry point: python -m d4loc or the built .exe.  `--selftest <file>` checks that all dependencies are present."""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from d4loc.i18n import _


def selftest(path):
    lines = []
    try:
        import numpy
        import scipy
        import sv_ttk
        import soundfile
        import UnityPy
        from d4loc import VERSION, audio, game, gui, install, project, texts  # noqa: F401
        import io
        import numpy as np
        buf = io.BytesIO()
        soundfile.write(buf, np.zeros(1000, dtype="float32"), 24000, format="FLAC", subtype="PCM_16")
        import fmod_toolkit
        dll = os.path.join(os.path.dirname(fmod_toolkit.__file__), "libfmod", "Windows", "x64", "fmod.dll")
        if sys.platform == "win32" and not os.path.isfile(dll):
            raise FileNotFoundError(dll)  # fmod.dll is needed by UnityPy to decode the game's clips
        from archspec import cpu
        cpu.host()  # needs the archspec json files
        from d4loc import oggenc
        blob, _rate = oggenc.encode_opus(np.zeros(4800, dtype="int16"), 48000)       # PyAV with the Opus encoder
        back, brate = soundfile.read(io.BytesIO(blob), dtype="int16")                  # and reading the result back through soundfile
        if brate != 48000 or len(back) < 4800:
            raise RuntimeError("opus")
        lines += ["fmod ok", f"d4loc {VERSION}", f"UnityPy {UnityPy.__version__}", f"numpy {numpy.__version__}",
                  f"scipy {scipy.__version__}", f"soundfile {soundfile.__version__}", "flac ok", "opus ok", "OK"]
        code = 0
    except Exception as e:
        lines += [_("ПОМИЛКА: {0}: {1}").format(type(e).__name__, e)]
        code = 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code


def cli_install(game_dir, pack_dir, mix, voice, report):
    """Headless: install a content pack (a folder with manifest.json and the text, including a fork) into the game folder; for tests and CI. The result goes to the report."""
    from d4loc import install
    lines = []
    try:
        install.install_pack(game_dir, pack_dir, -14.0 if (mix and voice) else None, log=lines.append, with_voice=voice)
        lines.append("OK")
        code = 0
    except Exception as e:
        lines.append(_("ПОМИЛКА: {0}: {1}").format(type(e).__name__, e))
        code = 1
    with open(report, "w", encoding="utf-8") as f:
        f.write(chr(10).join(lines) + chr(10))
    return code


if __name__ == "__main__":
    if "--install" in sys.argv:
        i = sys.argv.index("--install")
        sys.exit(cli_install(sys.argv[i + 1], sys.argv[i + 2], "--no-mix" not in sys.argv, "--no-voice" not in sys.argv, sys.argv[i + 3]))
    if "--selftest" in sys.argv:
        sys.exit(selftest(sys.argv[sys.argv.index("--selftest") + 1]))
    from d4loc.gui import main
    main()
