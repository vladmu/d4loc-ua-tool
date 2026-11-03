"""Unpacks the English text and voice-over of your copy of the game into the content folder (en/ is not committed: the repository ignores it).

This is the very same code the translator tool runs when you open the content folder as its project (project.ensure_language): the pipeline reads
the original lines (their text and their length, which the Ukrainian voice has to fit into) from there, so no second copy is kept.
The English audio belongs to the rights holders, so it stays only on your computer.

Run: python dev/run.py extract [--content FOLDER] [--repo OWNER/NAME] [--game GAME_FOLDER] [--force]
  --content  the content folder (default: content/ next to the project, or D4_CONTENT). If it does not exist or is empty, the latest release of the
             content repository is laid out in it first, exactly as the translator tool does. The other commands read the same folder: for a different
             one, set D4_CONTENT.
  --repo     whose release that is: by default the official content repository; pass "owner/name" (or the address) of your fork if it has its own releases.
"""
import argparse

from d4loc import download, game, project, repo
from tools import paths


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--content", default=paths.CONTENT, help="тека контенту (за замовчуванням content/ або D4_CONTENT)")
    p.add_argument("--repo", default=download.REPO, help="чий реліз брати, якщо теки нема або вона порожня: owner/name офіційного репозиторію контенту чи вашого fork")
    p.add_argument("--game", default=None, help="тека гри (за замовчуванням знаходиться сама)")
    p.add_argument("--force", action="store_true", help="розпакувати знову, навіть якщо розпаковане актуальне")
    cfg = p.parse_args()
    gd = game.require_game_dir(cfg.game or game.find_game_dir())
    kind, message = repo.inspect_folder(cfg.content)
    if kind in ("missing", "empty"):
        print("Беру реліз:", download.normalize_repo(cfg.repo))
        repo.populate_from_release(cfg.content, repo=cfg.repo)
    elif kind != "content":
        raise SystemExit(message or f"{cfg.content}: це не тека контенту (нема uk/loca_uk_texts.csv і manifest.json)")
    result = project.ensure_language(gd, "en", cfg.content, force=cfg.force)
    print(f"Англійська в {cfg.content}: {result}")
    if cfg.content != paths.CONTENT:
        print("Інші команди читають теку", paths.CONTENT, "- щоб вони працювали з цією, задайте змінну D4_CONTENT.")
