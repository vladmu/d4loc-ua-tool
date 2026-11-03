"""Every interface string in _() has an English translation with the same {placeholders}."""
import ast
import glob
import os
import re

from d4loc import i18n
from d4loc.strings_en import EN

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "d4loc")


def keys_in_sources():
    found = set()
    for path in glob.glob(os.path.join(SRC, "*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_" and n.args and isinstance(n.args[0], ast.Constant):
                found.add(n.args[0].value)
    return found


def test_every_key_has_english():
    missing = [k for k in keys_in_sources() if k not in EN]
    assert not missing, missing


def test_placeholders_and_newlines_match():
    for k, v in EN.items():
        assert sorted(re.findall(r"\{\d+[^}]*\}", k)) == sorted(re.findall(r"\{\d+[^}]*\}", v)), k
        assert k.count("\n") == v.count("\n"), k


def test_no_cyrillic_in_english():
    for k, v in EN.items():
        if "Russian letters" in v:      # the letters ы э ё ъ are mentioned literally
            continue
        assert not re.search(r"[А-Яа-яІіЇїЄє]", v), v


def test_language_switch_and_fallback(monkeypatch):
    monkeypatch.setattr(i18n, "LANG", "uk")
    assert i18n._("Огляд…") == "Огляд…"
    monkeypatch.setattr(i18n, "LANG", "en")
    assert i18n._("Огляд…") == "Browse…"
    assert i18n._("немає такого ключа") == "немає такого ключа"


def test_detect_forced(monkeypatch):
    monkeypatch.setenv("D4LOC_LANG", "uk")
    assert i18n.detect() == "uk"
    monkeypatch.setenv("D4LOC_LANG", "de")
    assert i18n.detect() in ("uk", "en")   # an unknown forced language is ignored
