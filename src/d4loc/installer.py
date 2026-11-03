"""Entry point of the players' executable (D4Loc-UA-Installer.exe): the same application as the Toolkit, without the translator tool."""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from d4loc import edition  # noqa: E402

edition.TRANSLATOR = False

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from d4loc.__main__ import selftest
        sys.exit(selftest(sys.argv[sys.argv.index("--selftest") + 1]))
    from d4loc.gui import main
    main()
