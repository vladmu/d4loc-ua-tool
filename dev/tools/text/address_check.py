""""ty/vy" (informal/formal you) check in all lines: pronouns and possessives in all cases, 2nd-person verbs and the imperative mood.

Ukrainian and Russian forms are determined by a morphological analyzer (pymorphy3), and the translation is compared with
the game's Russian localization. Run: tts_env\\Scripts\\python.exe check_address.py
"""
import argparse
import csv
import os

from tools import paths
from tools.text import public
import re
import collections

import pymorphy3

WORD = re.compile(r"[А-Яа-яІіЇїЄєҐґЁё'’ʼ-]+")
LEMMAS = {
    "uk": {"sg": {"ти", "твій"}, "pl": {"ви", "ваш"}},
    "ru": {"sg": {"ты", "твой"}, "pl": {"вы", "ваш"}},
}
analyzers = {}


def analyzer(lang):
    if lang not in analyzers:
        analyzers[lang] = pymorphy3.MorphAnalyzer(lang=lang)
    return analyzers[lang]


_cache = {}


def classify_word(word, lang):
    key = (word.lower(), lang)
    if key in _cache:
        return _cache[key]
    res = None
    parses = analyzer(lang).parse(word.lower())
    for p in parses:  # pronouns and possessives: any parse is enough
        for n, lemmas in LEMMAS[lang].items():
            if p.normal_form in lemmas:
                res = n
    if res is None and parses:  # verbs: only the most probable parse
        tag = parses[0].tag
        if "VERB" in tag and "2per" in tag:
            res = "sg" if "sing" in tag else "pl" if "plur" in tag else None
    _cache[key] = res
    return res


def address(text, lang):
    found = collections.Counter(classify_word(w, lang) for w in WORD.findall(text))
    sg, pl = found.get("sg", 0), found.get("pl", 0)
    return ("mixed" if sg and pl else "sg" if sg else "pl" if pl else "-"), sg, pl


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--translations", default=paths.TRANSLATIONS)
    p.add_argument("--ru", default=paths.game_file("loca_ru_texts.csv"))
    p.add_argument("--out", default=paths.ADDRESS_REPORT)
    cfg = p.parse_args()
    public.ensure_table(cfg.translations)

    with open(cfg.ru, "r", encoding="utf-8-sig", newline="") as f:
        ru = {r["name"]: r["wording"] for r in csv.DictReader(f)}
    with open(cfg.translations, "r", encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] in ("machine", "edited", "user", "recorded") and r["name"] in ru]

    out = []
    stat = collections.defaultdict(collections.Counter)
    for r in rows:
        grp = "dlg" if r["name"].startswith("dlg_") else "ui"
        c_uk, *_ = address(r["uk"], "uk")
        c_ru, *_ = address(ru[r["name"]], "ru")
        stat[grp][(c_ru, c_uk)] += 1
        if c_uk == "mixed" or (grp == "dlg" and {c_ru, c_uk} == {"sg", "pl"}):
            out.append({"name": r["name"], "voice": r["voice"], "uk_address": c_uk, "ru_address": c_ru,
                        "source": r["source"].replace("\n", " / "), "ru": ru[r["name"]].replace("\n", " / "),
                        "uk": r["uk"].replace("\n", " / ")})
    for grp in ("dlg", "ui"):
        print(f"\n{grp}: (російська → українська), кількість рядків")
        for (a, b), n in sorted(stat[grp].items(), key=lambda x: -x[1]):
            print(f"  ru={a:5s} uk={b:5s} {n}")
    with open(cfg.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "voice", "uk_address", "ru_address", "source", "ru", "uk"])
        w.writeheader()
        w.writerows(out)
    print(f"\nПідозрілих (змішані форми в uk або dlg: ru і uk у протилежних): {len(out)} -> {cfg.out}")


if __name__ == "__main__":
    main()
