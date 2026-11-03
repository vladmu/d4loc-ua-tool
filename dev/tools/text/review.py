"""Proofreading the translation: review dump <prefix>  /  review apply <prefix> <edits-file>.

dump prints numbered lines (original and translation) for proofreading, apply turns an edits file
(lines "number<TAB>new translation") into dev/config/manual_fixes/text_review_<prefix>.jsonl.
The fixes command then applies the edits.
"""
import csv
import json
import os
import sys

from tools import paths

VOICE_TAGS = {"": "", "thalya": "T", "thalya_good": "Tg", "story_brother": "Br", "tanos": "Tn", "story_angel": "An"}


def rows(prefix):
    from tools.text import public
    public.ensure_table()
    with open(paths.TRANSLATIONS, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r["name"].startswith("dlg_" + prefix) and r["status"] in ("machine", "edited", "user", "recorded")]


def dump(prefix):
    for i, r in enumerate(rows(prefix), 1):
        v = VOICE_TAGS.get(r["voice"], r["voice"][:8])
        print(f"{i}|{v}|{r['source'].replace(chr(10), ' ')}||{r['uk'].replace(chr(10), ' ')}")


def apply(prefix, fixes_file):
    rs = rows(prefix)
    n = 0
    with open(os.path.join(paths.MANUAL_FIXES, f"text_review_{prefix}.jsonl"), "w", encoding="utf-8") as out:
        for line in open(fixes_file, encoding="utf-8"):
            if "\t" in line:
                i, t = line.rstrip("\n").split("\t", 1)
                out.write(json.dumps({"name": rs[int(i) - 1]["name"], "set": t.strip()}, ensure_ascii=False) + "\n")
                n += 1
    print("правок", n)


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "dump":
        dump(a[1])
    elif len(a) == 3 and a[0] == "apply":
        apply(a[1], a[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
