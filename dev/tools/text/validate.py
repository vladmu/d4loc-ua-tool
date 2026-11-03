"""Validating the translation in the content repository (content/uk/loca_uk_texts.csv): markup, stage directions, common slips.

  python dev/run.py validate [path to loca_uk_texts.csv]

The translator tool checks the same before saving. Exit code 1 if there are errors (remarks do not count)."""
import sys

from d4loc import validate
from tools import paths


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else paths.CONTENT_TEXTS
    found = validate.check_file(path)
    for name, kind, msg in found:
        print(f"{'ПОМИЛКА' if kind == 'error' else 'увага'} {name}: {msg}")
    errors = sum(1 for _n, k, _m in found if k == "error")
    print(f"Перевірено {path}: помилок {errors}, зауважень {len(found) - errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
