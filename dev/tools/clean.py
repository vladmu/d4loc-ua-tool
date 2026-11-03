"""Removes the pipeline's work folder (the translation table, the reports, the build snapshot).

Run: python dev/run.py clean

Nothing in it is needed after publishing: the text, the voices, the status of every line and the state of the voice synthesis live in the
content repository, and any command that needs the translation table rebuilds it from there. Only a folder that carries the marker
(created by the pipeline itself) is removed; a folder you pointed D4_WORK at for other purposes is never touched.
"""
import os
import shutil
import sys

from tools import paths


def main(argv=None):
    if not os.path.isdir(paths.WORK):
        print(f"Робочої теки нема: {paths.WORK}")
        return 0
    if not os.path.isfile(os.path.join(paths.WORK, paths.WORK_MARKER)):
        print(f"Не видаляю {paths.WORK}: у ній нема маркера {paths.WORK_MARKER}, тобто її створив не конвеєр. Видаліть її самі, якщо це дійсно непотрібне.")
        return 1
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _x, fs in os.walk(paths.WORK) for f in fs)
    shutil.rmtree(paths.WORK)
    print(f"Робочу теку видалено: {paths.WORK} ({size / 2**20:.1f} МБ). Усе потрібне відновиться з content/.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
