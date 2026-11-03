"""Installs the content folder into your game and removes it again, from the command line: the same code as the installer window (install.install_pack,
install.uninstall), so the backups, the language-menu line and the version check are identical. Handy right after `voice`: listen to the result in the game.

  python dev/run.py install   [--content FOLDER] [--game GAME_FOLDER] [--no-voice] [--no-mix] [--force]
  python dev/run.py uninstall [--game GAME_FOLDER]

  --content  the content folder (default: content/ or D4_CONTENT)
  --no-voice text only, the game keeps the English voices
  --no-mix   do not mix the quiet English original under the Ukrainian voice
  --force    install even if the game version differs from the one the content was made for
"""
import argparse
import sys

from d4loc import game, install
from tools import paths


def _progress(i, n, msg):
    if n:
        print(f"  {msg}: {100 * i / n:.0f}%", flush=True)


def do_install(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--content", default=paths.CONTENT)
    p.add_argument("--game", default=None)
    p.add_argument("--no-voice", action="store_true")
    p.add_argument("--no-mix", action="store_true")
    p.add_argument("--force", action="store_true")
    cfg = p.parse_args(argv)
    gd = game.require_game_dir(cfg.game or game.find_game_dir())
    if not install.has_content(cfg.content):
        raise SystemExit(f"У {cfg.content} нема перекладу (manifest.json і uk/loca_uk_texts.csv). Спершу python dev/run.py build")
    ok, msg = install.check_compat(gd, cfg.content)
    print(msg)
    if not ok and not cfg.force:
        raise SystemExit("Версія гри не збігається з тією, для якої зроблено контент. Додайте --force, щоб установити на власний ризик.")
    voice = not cfg.no_voice
    install.install_pack(gd, cfg.content, -14.0 if (voice and not cfg.no_mix) else None, _progress, print, with_voice=voice)
    print("Готово. У грі: Налаштування -> Мова -> «Українська (Ukrainian)». Прибрати: python dev/run.py uninstall")
    return 0


def do_uninstall(argv):
    p = argparse.ArgumentParser(description="Видалення української мови з теки гри")
    p.add_argument("--game", default=None)
    cfg = p.parse_args(argv)
    gd = game.require_game_dir(cfg.game or game.find_game_dir())
    install.uninstall(gd, log=print)
    print("Готово: мовні файли гри повернено до оригіналу.")
    return 0


def main():
    cmd = sys.argv[0].split()[-1] if sys.argv else "install"
    return (do_uninstall if cmd == "uninstall" else do_install)(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
