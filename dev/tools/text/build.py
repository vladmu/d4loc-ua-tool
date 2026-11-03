import argparse
import csv
import os
import shutil

from tools import paths
from tools.text import public
import re

from tools.text import translate as tr


# Ukrainian language names in the game format: "name in the interface language (English)"
LANG_NAMES = {
    "ar": "арабська", "de": "німецька", "en": "англійська", "es": "іспанська", "fr": "французька",
    "it": "італійська", "ja": "японська", "ko": "корейська", "pl": "польська",
    "pt-br": "бразильська португальська", "pt-pt": "португальська", "ru": "російська", "tr": "турецька",
    "zh-hans": "спрощена китайська", "zh-hant": "традиційна китайська",
}
# Service lines that differ from the Russian values
OVERRIDES = {"_format_per_level": "(+{Value}/рів.)"}

RU_WORDS = re.compile(r"\b(уровн\w*|горяч\w*|сейчас|только|очень|нужно|хорош\w*|спасибо|пожалуйста|можно|которы\w*)\b", re.I)
# Addressing several people in the original, but ty-forms in the translation ("My brothers... in your eyes")
PLURAL_ADDRESS = re.compile(r"\b(brothers|brethren|friends|comrades|everyone|everybody|all of you|you all|guys|folks|gentlemen)\b", re.I)
TY_FORMS = re.compile(r"\b(ти|тебе|тобі|тобою|твій|твоя|твоє|твої|твоїх|твого|твоєї|твоєму|твоїм|твоїми|твоєю|твоїй)\b", re.I)
PLURAL_IMPERATIVE = re.compile(r"\b\w+(іть|йте|ьте)\b", re.I)


def clean_text(text):
    """Removes stress marks (U+0301) and stretched letter repeats ("Брааааааа" -> "Браааа")."""
    text = text.replace(chr(0x301), "")
    return re.sub(r"([А-Яа-яІіЇїЄєҐґ])" + chr(92) + "1{5,}", lambda m: m.group(1) * 4, text)


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def load_glossary(path):
    pairs = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8-sig"):
            if "=" in line and not line.lstrip().startswith("#"):
                en, uk = (x.strip() for x in line.split("=", 1))
                pairs.append((en, uk))
    return pairs


def service_value(name, src_row, ru, en_names):
    if name == "_audiolocale":
        return "uk"
    if name in OVERRIDES:
        return OVERRIDES[name]
    if name.startswith("_languageName_"):
        code = name[len("_languageName_"):]
        if code == "uk":
            return "Українська"
        if code == "auto":
            return "Автоматичний вибір"
        if code in LANG_NAMES:
            return f"{LANG_NAMES[code]} ({en_names[name]})"
    if name in ru:
        return ru[name]["wording"]
    return src_row["wording"]


def main():
    p = argparse.ArgumentParser(description="Збірка фінального loca_uk_texts.csv")
    p.add_argument("--source", default=paths.EN_TEXTS)
    p.add_argument("--translations", default=paths.TRANSLATIONS)
    p.add_argument("--ru", default=paths.game_file("loca_ru_texts.csv"))
    p.add_argument("--glossary", default=paths.GLOSSARY)
    p.add_argument("--output", default=paths.CONTENT_TEXTS)
    p.add_argument("--review", default=paths.REVIEW)
    cfg = p.parse_args()
    public.ensure_table(cfg.translations)       # a fresh work folder: rebuilt from content/uk, not translated again

    fields, src = read_csv(cfg.source)
    _, trans_rows = read_csv(cfg.translations)
    trans = {r["name"]: r for r in trans_rows}
    ru = {r["name"]: r for r in read_csv(cfg.ru)[1]}
    en_names = {r["name"]: r["wording"] for r in src if r["name"].startswith("_languageName_")}
    glossary = load_glossary(cfg.glossary)

    out, review = [], []
    stats = {"translated": 0, "english_fallback": 0, "service": 0, "placeholder_errors": 0}
    for r in src:
        name, text = r["name"], r["wording"]
        row = dict(r)
        out.append(row)
        if name == "_languageName_tr":  # we have an additional language: insert the name next to the others
            out.append({"name": "_languageName_uk", "wording": service_value("_languageName_uk", r, ru, en_names),
                        "voice": "", "tags": ""})
        if name.startswith(tr.COPY_PREFIXES):
            row["wording"] = service_value(name, r, ru, en_names)
            stats["service"] += 1
            continue
        t = trans.get(name)
        if not t or not t["uk"] or t["status"] == "failed":
            if tr.should_copy(name, text):
                continue
            stats["english_fallback"] += 1
            review.append((name, r["voice"], "немає перекладу", text, ""))
            continue
        uk = clean_text(t["uk"])
        if tr.should_copy(name, text):
            continue
        row["wording"] = uk
        stats["translated"] += 1

        reasons = []
        if sorted(tr.TOKEN_RE.findall(text)) != sorted(tr.TOKEN_RE.findall(uk)):
            reasons.append("розмітка змінена")
            stats["placeholder_errors"] += 1
        if RU_WORDS.search(uk):
            reasons.append("російські слова")
        if len(text) > 25 and not (0.5 <= len(uk) / len(text) <= 1.8):
            reasons.append("дивна довжина")
        if r["voice"] or name.startswith("dlg_"):
            if PLURAL_IMPERATIVE.search(uk):
                reasons.append("множина (ти/ви?)")
        elif PLURAL_IMPERATIVE.search(uk):
            reasons.append("множина (ти/ви?)")
        if PLURAL_ADDRESS.search(text) and TY_FORMS.search(uk):
            reasons.append("звернення до кількох: ви")
        for en_term, uk_term in glossary:
            if re.search(rf"\b{re.escape(en_term)}\b", text) and uk_term[:4].lower() not in uk.lower():
                reasons.append(f"глосарій: {en_term}")
                break
        if text[:1].isupper() != uk[:1].isupper() and text[:1].isalpha():
            reasons.append("регістр першої літери")
        if reasons:
            review.append((name, r["voice"], "; ".join(reasons), text, uk))

    os.makedirs(os.path.dirname(cfg.output), exist_ok=True)
    with open(cfg.output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    if cfg.output == paths.CONTENT_TEXTS:       # a copy for `sync`: it tells what build wrote from what somebody edited afterwards
        paths.ensure_work()
        shutil.copyfile(cfg.output, paths.BUILT_SNAPSHOT)
    paths.ensure_work()
    with open(cfg.review, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "voice", "reasons", "source", "uk"])
        w.writerows(review)
    print(f"{cfg.output}: {len(out)} рядків; {stats}")
    print(f"{cfg.review}: {len(review)} рядків на вичитку")


if __name__ == "__main__":
    main()
