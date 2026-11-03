"""Translation <-> the content repository (content/uk/loca_uk_texts.csv in the game format and content/uk/status.csv).

`build` writes the game file straight into content/uk, so publishing is only about the status of the lines:

  python dev/run.py public [--clean]
        status of every line (the working translation table) -> content/uk/status.csv. A line that a person marked `user` or `recorded`
        keeps that mark. --clean then removes the work folder (see `python dev/run.py clean`).
  python dev/run.py sync
        import: edits and statuses from content/uk (including from a pull request) -> the working translation table, so that the next
        build does not wipe community edits.

The working translation table lives in the work folder and is only a working copy. When it is missing (a fresh work folder), every command
that needs it rebuilds it with ensure_table(): the Ukrainian text and the status come from content/uk, the English original from content/en
(unpacked by the translator tool or `extract`). Nothing is translated twice because of a missing table.

There is no English text in the content repository (it belongs to the rights holders): everyone takes it from their own copy of the game.
"""
import csv
import os
import sys

from d4loc import status, texts
from tools import paths

FIELDS = ["name", "voice", "source", "uk", "status"]


def read_table(path=None):
    path = path or paths.TRANSLATIONS
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_table(rows, fields=FIELDS):
    paths.ensure_work()
    tmp = paths.TRANSLATIONS + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, paths.TRANSLATIONS)


def bootstrap():
    """The working table rebuilt from content: Ukrainian text and status from content/uk, English original from content/en."""
    if not os.path.isfile(paths.EN_TEXTS):
        raise SystemExit(f"Нема {paths.EN_TEXTS}: спершу python dev/run.py extract (або відкрийте теку content як проєкт в інструменті перекладача)")
    marks = status.read(paths.CONTENT_UK)
    source = {r[0]: r[1] for r in texts.read_texts(paths.EN_TEXTS)}
    rows = [{"name": n, "voice": v, "source": source.get(n, ""), "uk": w, "status": marks.get(n) or "edited"}
            for n, w, v, _t in texts.read_texts(paths.CONTENT_TEXTS)]
    write_table(rows)
    print(f"Робочу таблицю відновлено з контенту: {len(rows)} рядків (рядки без позначки в status.csv мають статус edited)")


def ensure_table(path=None):
    """Rebuilds the working table from content when it does not exist (only for the default location; nothing to do without content)."""
    if (path is None or os.path.abspath(path) == os.path.abspath(paths.TRANSLATIONS)) \
            and not os.path.isfile(paths.TRANSLATIONS) and os.path.isfile(paths.CONTENT_TEXTS):
        bootstrap()


def export(clean=False):
    ensure_table()
    table = {r["name"]: r["status"] for r in read_table() if r["status"] and r["status"] != "failed"}
    keys = {r[0] for r in texts.read_texts(paths.CONTENT_TEXTS)}
    current = status.read(paths.CONTENT_UK)
    out = {}
    for name in keys:
        mark = current.get(name)
        if mark in (status.USER, status.RECORDED):
            out[name] = mark                        # a person's mark from a pull request is never lowered by the pipeline
        elif name in table:
            out[name] = table[name]
    status.write(paths.CONTENT_UK, out)
    print(f"Статуси рядків: {len(out)} у {status.path(paths.CONTENT_UK)}")
    if clean:
        from tools import clean as cleaner
        cleaner.main([])


def sync():
    ensure_table()
    repo_rows = texts.read_texts(paths.CONTENT_TEXTS)
    repo = {r[0]: r[1] for r in repo_rows}
    marks = status.read(paths.CONTENT_UK)
    built = {r[0]: r[1] for r in texts.read_texts(paths.BUILT_SNAPSHOT)} if os.path.isfile(paths.BUILT_SNAPSHOT) else {}
    rows = read_table()
    fields = list(rows[0].keys()) if rows else FIELDS
    changed = {n for n, w in repo.items() if n in built and built[n] != w}
    n = 0
    for r in rows:
        name = r["name"]
        mark = marks.get(name)
        human = mark in (status.USER, status.RECORDED)
        if name in changed:
            r["uk"] = repo[name]
            r["status"] = mark if human else status.USER
            n += 1
        elif human and r["status"] != mark:
            r["status"] = mark
            n += 1
    write_table(rows, fields)
    print(f"Правок і статусів із репозиторію перенесено в таблицю перекладу: {n} (змінених текстів: {len(changed)}). Далі: python dev/run.py build")


def main():
    cmd = sys.argv[0].split()[-1] if sys.argv else "public"
    if cmd == "sync":
        sync()
    else:
        export(clean="--clean" in sys.argv[1:])


if __name__ == "__main__":
    main()
