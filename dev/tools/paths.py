"""The single place for the developer pipeline's paths.

ROOT       the root of the application repository
CONFIG     glossary, stress rules, voice cast, history of manual edits (pipeline settings, in this repository)
CONTENT    the separate content repository (only the translation and voices: uk/ and manifest.json), cloned here or pointed to
           by the D4_CONTENT variable
WORK       a local work folder OUTSIDE the repository (%LOCALAPPDATA%/D4LocToolkit/work; change it with the environment variable D4_WORK):
           the translation table, the reports and the draft state. Everything in it can be rebuilt from content/, `python dev/run.py clean` removes it.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.path.join(ROOT, "dev", "config")
CONTENT = os.environ.get("D4_CONTENT") or os.path.join(ROOT, "content")
WORK = os.environ.get("D4_WORK") or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "D4LocToolkit", "work")
WORK_MARKER = ".d4loc-work"       # `clean` removes only a folder that carries this marker, i.e. one the pipeline created itself

MANUAL_FIXES = os.path.join(CONFIG, "manual_fixes")
GLOSSARY = os.path.join(CONFIG, "glossary.txt")
STRESS_OVERRIDES = os.path.join(CONFIG, "stress_overrides.txt")
STRESS_HINTS = os.path.join(CONFIG, "stress_hints.txt")
VOICE_CAST = os.path.join(CONFIG, "voice_cast.json")

# content repository: the unpacked Ukrainian in the same structure the translator tool works with
CONTENT_UK = os.path.join(CONTENT, "uk")
CONTENT_TEXTS = os.path.join(CONTENT_UK, "loca_uk_texts.csv")
CONTENT_AUDIO = os.path.join(CONTENT_UK, "audio")
CONTENT_META = os.path.join(CONTENT_UK, "audio_metadata.csv")
CONTENT_MANIFEST = os.path.join(CONTENT, "manifest.json")

# English originals from your game, unpacked by the translator tool or `extract` into the content folder (en/ is not committed)
CONTENT_EN = os.path.join(CONTENT, "en")
EN_TEXTS = os.path.join(CONTENT_EN, "loca_en_texts.csv")
EN_META = os.path.join(CONTENT_EN, "audio_metadata.csv")
EN_AUDIO = os.path.join(CONTENT_EN, "audio")

# work folder files
TRANSLATIONS = os.path.join(WORK, "translations_uk.csv")    # the full translation table (with the original, local only)
BUILT_SNAPSHOT = os.path.join(WORK, "built_snapshot.csv")   # a copy of what `build` last wrote into content/uk: `sync` compares edits against it
REVIEW = os.path.join(WORK, "review_uk.csv")
ADDRESS_REPORT = os.path.join(WORK, "address_report.csv")
UK_AUDIO = os.path.join(WORK, "uk_audio")                   # the report of the voice synthesis


def game_file(name):
    """A file from your game's AssetBundles (the game folder is found automatically: Steam, Epic, GOG)."""
    from d4loc import game
    gd = game.find_game_dir()
    return os.path.join(game.bundles_dir(gd), name) if gd else name


def ensure_work():
    """Creates the work folder with its marker."""
    os.makedirs(WORK, exist_ok=True)
    marker = os.path.join(WORK, WORK_MARKER)
    if not os.path.isfile(marker):
        with open(marker, "w", encoding="utf-8") as f:
            f.write("created by python dev/run.py; `python dev/run.py clean` may remove this folder\n")
