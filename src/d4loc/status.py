"""The status of every line of the translation: uk/status.csv in the content repository (only the key and the status; the text,
the voice and the English original live in their own files).

  name,status
  dlg_x,machine

machine   the text is a draft of the language model; the voice is synthesized
edited    corrected by hand during proofreading
copied    taken from the original as is (names, formats)
user      the text was changed by a person (the translator tool or a pull request); the voice is synthesized again from the new text
recorded  a person recorded the voice and a pull request accepted it; the pipeline leaves both the text and the voice of this line alone

The translator tool sets `user` when a text is changed and `recorded` when a new recording is stored. The file lives next to the text
and voices it describes, so the status travels with every pull request and is covered by the verification stamp (toolcheck.json).
"""
import csv
import os

FILE = "status.csv"
FIELDS = ["name", "status"]
USER = "user"
RECORDED = "recorded"
# statuses of lines that a person has touched: the pipeline never translates them again
HUMAN = ("edited", USER, RECORDED)


def path(lang_dir):
    return os.path.join(lang_dir, FILE)


def read(lang_dir):
    """{name: status}; an empty dict if the file does not exist."""
    p = path(lang_dir)
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        return {r["name"]: r.get("status", "") for r in csv.DictReader(f) if r.get("name")}


def write(lang_dir, data):
    """Sorted by name, LF line endings, so that a pull request shows only the lines that really changed."""
    os.makedirs(lang_dir, exist_ok=True)
    with open(path(lang_dir), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for name in sorted(data):
            w.writerow({"name": name, "status": data[name]})


def mark(lang_dir, texts=(), recordings=()):
    """Texts changed by a person -> user (unless the line is already recorded); stored recordings -> recorded. Returns the number of lines touched."""
    data = read(lang_dir)
    for name in texts:
        if data.get(name) != RECORDED:
            data[name] = USER
    for name in recordings:
        data[name] = RECORDED
    if texts or recordings:
        write(lang_dir, data)
    return len(set(texts) | set(recordings))
