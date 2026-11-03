"""Translation validation before writing into the game and before a PR: markup, stage directions, common slips.

The content repository has no English original, so we check what can be checked without it: balanced {…}, <…> and *…* in dialogues,
no letters ы э ё ъ, double spaces, leftover English. Errors must be fixed, remarks are warnings only."""
import re

from . import texts
from .i18n import _

RU_ONLY = re.compile("[ыэёъЫЭЁЪ]")
LATIN_RUN = re.compile(r"[A-Za-z]{4,}")
TAG = re.compile(r"<[^>]+>")
# proper names that stay in Latin letters (the game, companies, platforms); res_*: a space at the edge is part of the value, the game adds it
PROPER = {"Dungeons", "Dungeon", "Discord", "Steam", "Community", "Demo", "Realmforge", "Studios", "Kalypso", "Media",
          "support", "kalypsomedia", "Digital", "Deluxe", "Edition"}


def check_text(name, wording):
    """(errors, remarks) for one line."""
    errs, warns = [], []
    if RU_ONLY.search(wording):
        errs.append(_("російські літери (ы, э, ё, ъ)"))
    if wording.count("{") != wording.count("}"):
        errs.append(_("незбалансовані фігурні дужки {…}"))
    if name.startswith("dlg_") and wording.count("*") % 2:   # in dialogues *…* are stage directions; in descriptions the asterisks are game markup
        errs.append(_("непарна кількість зірочок у ремарці *…*"))
    opens = len(re.findall(r"<(?!/|sprite|br\b)[a-z]+", wording, re.I))   # sprite and br are self-closing game tags
    closes = len(re.findall(r"</[a-z]+>", wording, re.I))
    if opens != closes:
        errs.append(_("незбалансовані теги <…></…>"))
    if "  " in wording:
        warns.append(_("подвійний пробіл"))
    if wording != wording.strip() and not name.startswith(("res_", "_")):   # res_*, _* (service): a space at the edge is the value
        warns.append(_("пробіли на краях"))
    words = [w for w in LATIN_RUN.findall(TAG.sub("", re.sub(r"https?://\S+|\{[^}]*\}", "", wording))) if w not in PROPER]
    if len(words) >= 3:
        warns.append(_("багато латиниці (залишок англійського?): {0}").format(" ".join(words[:4])))
    return errs, warns


def check_rows(rows, only=None):
    """[(key, 'error'|'remark', message)] for lines (name, wording, voice, tags); only is a set of keys to check."""
    out, seen = [], set()
    for name, wording, _v, _t in rows:
        if name in seen:
            out.append((name, "error", _("ключ повторюється")))
        seen.add(name)
        if only is not None and name not in only:
            continue
        errs, warns = check_text(name, wording)
        out += [(name, "error", m) for m in errs] + [(name, "warning", m) for m in warns]
    return out


def check_file(path):
    return check_rows(texts.read_texts(path))
