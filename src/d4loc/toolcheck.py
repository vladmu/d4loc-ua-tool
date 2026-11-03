"""Verification stamp toolcheck.json: a "lock file" for pull requests to the content repository.

After changes are saved the translator tool validates the translation (validate.py) and writes toolcheck.json into the project root: the tool
version and the checksum of its exe, the validation result and the SHA-256 of every content file (manifest.json, uk/loca_uk_texts.csv,
uk/audio_metadata.csv, uk/status.csv, uk/audio/**). The content repository's CI recomputes the sums and reruns the validation: while the stamp
is missing or stale (files changed after the check), the PR check is red. In a PR the changes show up as changes of the sums of the changed files.

This is insurance against forgotten and unchecked edits, not protection against a malicious actor: the stamp can be forged, so the real gate is
rerunning the validation in CI."""
import hashlib
import json
import os
import sys

from . import validate
from .i18n import _

FILE = "toolcheck.json"
FORMAT = 1
RULES_VERSION = 1


class ToolcheckError(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tracked_files(project):
    """Content files covered by the stamp (paths with "/", sorted)."""
    out = []
    for rel in ("manifest.json", "uk/loca_uk_texts.csv", "uk/audio_metadata.csv", "uk/status.csv"):
        if os.path.isfile(os.path.join(project, rel)):
            out.append(rel)
    base = os.path.join(project, "uk", "audio")
    for d, _dirs, files in os.walk(base):
        for fn in files:
            out.append(os.path.relpath(os.path.join(d, fn), project).replace(os.sep, "/"))
    return sorted(out)


def compute_files(project):
    return {rel: sha256_file(os.path.join(project, rel)) for rel in tracked_files(project)}


def tree_hash(files):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(f"{rel}\0{files[rel]}\n".encode("utf-8"))
    return h.hexdigest()


def tool_identity():
    """Version and SHA-256 of the application: for the built exe it is the sum of the file itself (it can be compared with the release's SHA256SUMS.txt), for code it is "source"."""
    from . import VERSION
    exe = sys.executable if getattr(sys, "frozen", False) else None
    return {"version": VERSION, "sha256": sha256_file(exe) if exe and os.path.isfile(exe) else "source"}


def write(project):
    """Validates the translation and writes toolcheck.json. If there are validation errors, the stamp is not written (ToolcheckError with the list)."""
    texts_path = os.path.join(project, "uk", "loca_uk_texts.csv")
    found = validate.check_file(texts_path)
    errors = [f"{n}: {m}" for n, k, m in found if k == "error"]
    if errors:
        raise ToolcheckError(_("Перевірка перекладу знайшла помилки ({0}); виправте їх, і штамп буде записано. Перші: {1}").format(
            len(errors), "; ".join(errors[:5])))
    files = compute_files(project)
    data = {"format": FORMAT, "tool": tool_identity(),
            "checks": {"validator": RULES_VERSION, "errors": 0, "warnings": sum(1 for _n, k, _m in found if k == "warning")},
            "tree": tree_hash(files), "files": files}
    path = os.path.join(project, FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return data


def verify(project, known_tool_hashes=None):
    """List of problems (empty if the stamp is valid): a missing or damaged file, changed/added/deleted files, validation errors,
    an unknown application (if a set of known release sums was passed)."""
    path = os.path.join(project, FILE)
    if not os.path.isfile(path):
        return [_("Нема toolcheck.json: відкрийте проєкт в інструменті перекладача й застосуйте зміни, щоб він записав штамп перевірки.")]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        saved = data["files"]
    except (OSError, ValueError, KeyError):
        return [_("toolcheck.json пошкоджений.")]
    problems = []
    now = compute_files(project)
    changed = sorted(r for r in now if r in saved and now[r] != saved[r])
    added = sorted(set(now) - set(saved))
    removed = sorted(set(saved) - set(now))
    if changed or added or removed:
        problems.append(_("Файли змінено після перевірки (змінено {0}, додано {1}, видалено {2}): запустіть інструмент і застосуйте зміни ще раз.").format(
            len(changed), len(added), len(removed)) + " " + ", ".join((changed + added + removed)[:5]))
    if data.get("tree") != tree_hash(saved):
        problems.append(_("Контрольна сума дерева у toolcheck.json не збігається зі списком файлів."))
    texts_path = os.path.join(project, "uk", "loca_uk_texts.csv")
    if os.path.isfile(texts_path):
        errors = [f"{n}: {m}" for n, k, m in validate.check_file(texts_path) if k == "error"]
        if errors:
            problems.append(_("Перевірка перекладу знайшла помилки ({0}). Перші: {1}").format(len(errors), "; ".join(errors[:5])))
    if known_tool_hashes is not None:
        sha = (data.get("tool") or {}).get("sha256")
        if sha == "source" or sha not in known_tool_hashes:
            problems.append(_("Штамп створено невідомим застосунком (його суми нема серед релізів інструмента)."))
    return problems
