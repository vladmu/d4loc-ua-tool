"""Applies manual point fixes (manual_fixes/*.jsonl) to translations_uk.csv.

Each line of the file: {"name": key, "pairs": [[old phrase, new phrase], ...]}.
A phrase is replaced only if it is present in the current translation. Changed lines get the status
"edited", so that no automatic run overwrites them again.
"""
import argparse
import glob
import json
import os

from tools import paths
from tools.text import public

from tools.text import build
from tools.text import translate as tr


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--translations", default=paths.TRANSLATIONS)
    p.add_argument("--fixes", default=os.path.join(paths.MANUAL_FIXES, "*.jsonl"))
    cfg = p.parse_args()
    public.ensure_table(cfg.translations)       # a fresh work folder: rebuilt from content/uk, not translated again

    fields, rows = build.read_csv(cfg.translations)
    by_name = {r["name"]: r for r in rows}
    applied = missing_row = 0
    skipped = []
    for path in sorted(glob.glob(cfg.fixes)):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                fix = json.loads(line)
                row = by_name.get(fix["name"])
                if not row:
                    missing_row += 1
                    continue
                changed = False
                if "set" in fix:  # full replacement (for lines the model could not translate)
                    if row["uk"] != fix["set"]:
                        row["uk"] = fix["set"]
                        changed = True
                for old, new in fix.get("pairs", []):
                    if old in row["uk"]:
                        row["uk"] = row["uk"].replace(old, new)
                        changed = True
                    elif new not in row["uk"]:
                        skipped.append((fix["name"], old[:50]))
                if changed:
                    row["status"] = row["status"] if row["status"] in ("user", "recorded") else "edited"
                    applied += 1
    tr.write_atomic(cfg.translations, fields, rows)
    print(f"Застосовано до {applied} рядків; немає рядка: {missing_row}; фрази, яких не знайдено: {len(skipped)}")
    for name, old in skipped[:15]:
        print(f"  ? {name}: {old}")


if __name__ == "__main__":
    main()
