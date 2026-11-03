import argparse
import csv
import os

from tools import paths
from tools.text import public
import time

from tools.text import translate as tr
from tools.text import build

HINTS = {
    "множина": "The previous translation wrongly used a plural/formal imperative (e.g. «Майте», «Знищте»). "
               "Address ONE player informally with the singular imperative (e.g. «Май», «Знищ», «Заверши»).",
    "звернення до кількох": "The speaker addresses SEVERAL people (e.g. «My brothers»). Use the plural/formal "
                            "forms «ви», «ваш», «ваших», «вас» and plural imperatives. Never use «ти», «твій», «твоїх».",
    "російські слова": "The previous translation contained Russian words. Use correct Ukrainian vocabulary only "
                       "(e.g. «рівень», «гарячі клавіші», «зараз», «тільки», «дуже», «потрібно», «можна»).",
}


def main():
    p = argparse.ArgumentParser(description="Повторний переклад рядків із review_uk.csv")
    p.add_argument("--translations", default=paths.TRANSLATIONS)
    p.add_argument("--review", default=paths.REVIEW)
    p.add_argument("--api", default="http://127.0.0.1:9931/v1")
    p.add_argument("--model", default="qwen")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--glossary", default=paths.GLOSSARY)
    cfg = p.parse_args()
    public.ensure_table(cfg.translations)       # a fresh work folder: rebuilt from content/uk, not translated again
    cfg.system_plain = tr.SYSTEM_PROMPT.format(markers="", glossary=tr.load_glossary(cfg.glossary))
    cfg.system_markers = tr.SYSTEM_PROMPT.format(markers=tr.MARKER_RULE, glossary=tr.load_glossary(cfg.glossary))

    fields, rows = build.read_csv(cfg.translations)
    by_name = {r["name"]: r for r in rows}
    with open(cfg.review, "r", encoding="utf-8-sig", newline="") as f:
        todo = [r for r in csv.DictReader(f) if any(k in r["reasons"] for k in HINTS)]
    print(f"Рядків для виправлення: {len(todo)}")

    fixed = 0
    for i, rv in enumerate(todo, 1):
        row = by_name.get(rv["name"])
        if not row or row["status"] in ("edited", "user", "recorded"):
            continue
        multi = "звернення до кількох" in rv["reasons"]
        hint = " ".join(h for k, h in HINTS.items()
                        if k in rv["reasons"] and not (multi and k == "множина"))
        source = row["source"]
        protected, tokens = tr.protect(source)
        for attempt in range(3):
            try:
                answer = tr.ask(cfg, {"name": row["name"], "voice": row["voice"]}, protected,
                                0.1 + 0.2 * attempt, bool(tokens), hint)
            except Exception as e:
                print(f"  ! {row['name']}: {e}")
                time.sleep(2)
                continue
            if not tr.valid(source, answer, len(tokens)):
                continue
            new = tr.restore(answer, tokens)
            if build.RU_WORDS.search(new):
                continue
            if multi and build.TY_FORMS.search(new):
                continue
            if not multi and (build.PLURAL_IMPERATIVE.search(new)
                              and not build.PLURAL_IMPERATIVE.search(source)):
                continue
            row["uk"] = new
            fixed += 1
            break
        if i % 20 == 0:
            tr.write_atomic(cfg.translations, fields, rows)
            print(f"  {i}/{len(todo)}, виправлено {fixed}")
    tr.write_atomic(cfg.translations, fields, rows)
    print(f"Готово: виправлено {fixed} із {len(todo)}")


if __name__ == "__main__":
    main()
