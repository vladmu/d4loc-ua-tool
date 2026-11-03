"""Launcher for the developer pipeline: python dev/run.py <command> [arguments]  (list of commands: python dev/run.py --help)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "src")]     # `tools` lives in dev/, the application package `d4loc` in src/

from tools.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
