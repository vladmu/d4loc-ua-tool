"""Prepares the content repository's release files (their content is taken from content/ without transformation).

  python dev/run.py release [--out release_assets]

Three files to attach to the content release on GitHub:
  manifest.json       a copy of content/manifest.json (content version and game version), side by side, not archived
  loca_uk_texts.csv   a copy of content/uk/loca_uk_texts.csv: the translation, the game file as is (not archived); this is the "text only" mode
  voice.zip           the voices in one archive: uk/audio/** and uk/audio_metadata.csv
The application fetches manifest.json separately, the text always, and voice.zip only when the user chose voice-over (see src/d4loc/download.py).
Integrity is checked by the size of every file and by the CRC of the files in the archive."""
import argparse
import os

from d4loc import download
from tools import paths


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", default=os.path.join(paths.ROOT, "release_assets"))
    p.add_argument("--version", default=None, help="версія контенту для manifest.json (за замовчуванням лишається поточна)")
    p.add_argument("--game", default=None, help="тека гри: з неї береться версія для маніфесту")
    cfg = p.parse_args()
    if os.path.isfile(paths.EN_META):       # bring the index and manifest in step with the voice files that are really in content/
        from tools.game import index
        print("Індекс і маніфест:", index.sync(version=cfg.version, game_dir=cfg.game))
    for f in (paths.CONTENT_TEXTS, paths.CONTENT_META, paths.CONTENT_MANIFEST):
        if not os.path.isfile(f):
            raise SystemExit(f"Нема {f}: спершу python dev/run.py public і python dev/run.py voice")
    try:
        voices, count = download.build_release(paths.CONTENT, cfg.out)
    except RuntimeError:
        raise SystemExit("Файли релізу не схожі на пакет контенту")
    for name in download.ASSETS:
        f = os.path.join(cfg.out, name)
        print(f"{name:20s} {os.path.getsize(f) / 2**20:8.2f} МБ  SHA-256 {download.sha256_file(f)}")
    print(f"Готово: {cfg.out} (аудіофайлів {count}, голосів {voices})")


if __name__ == "__main__":
    main()
