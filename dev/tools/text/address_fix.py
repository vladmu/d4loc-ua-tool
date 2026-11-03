"""Harmonizing "ty/vy" (informal/formal you) in the translation by rule, not by the Russian:

  * by default there is one addressee (the player or a character): "ty", singular, imperative "знищ";
  * "vy" only when the English original clearly addresses a group (brothers, y'all, Forward Creatures...).

Every new translation is checked with the analyzer (pymorphy3): after the fix the text must contain
only forms of the required number. Run in tts_env, because pymorphy3 is installed there:
  tts_env\\Scripts\\python.exe fix_address.py [--dry-run]
"""
import argparse
import os

from tools import paths
from tools.text import public
import re
import time

import requests

from tools.text import build
from tools.text import address_check as ca
from tools.text import translate as tr

# Addressing a group in the English original
_NOUNS = (r"creatures|heroes|minions|dwarves|snots|maggots|worms|friends|folks|men|boys|lads|brothers|sisters|"
          r"brethren|faithful|comrades|ones|fools|idiots|slackers")
GROUP_CUE = re.compile(
    r"\b(y'all|you all|you lot|all of you|both of you|you two|everyone|everybody|"
    r"my (" + _NOUNS + r")|"
    r"(you|hey|oh|ah|come|go|forward|onward|onwards|move|listen|attention|quickly|brothers),? "
    r"((my|you|lazy|stupid|dear|faithful|brave|old|little|dumb|poor) )*(" + _NOUNS + r"))\b", re.I)
# Polite forms of address where "vy" may be justified
FORMAL_CUE = re.compile(r"\b(your (majesty|highness|excellency|grace|honou?r)|my lord|my lady|sir|madam|ma'am)\b", re.I)

HINT_PLURAL = ("The speaker addresses SEVERAL people. Use the plural forms «ви», «ваш», «ваших», «вас» and "
               "plural verb/imperative forms (e.g. «знищте», «дізнаєтесь»). Never use «ти», «твій», «твоїх».")
HINT_SINGLE = ("The speaker addresses ONE person informally. Use «ти», «твій», «твоїх» and singular verb/imperative "
               "forms (e.g. «знищ», «дізнаєшся», «зроби»). Never use «ви», «ваш», plural imperatives («знищте»).")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--translations", default=paths.TRANSLATIONS)
    p.add_argument("--api", default="http://127.0.0.1:9931/v1")
    p.add_argument("--model", default="qwen")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--glossary", default=paths.GLOSSARY)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--scope", choices=["ui", "dlg", "all"], default="all")
    cfg = p.parse_args()
    public.ensure_table(cfg.translations)       # a fresh work folder: rebuilt from content/uk, not translated again
    glossary = tr.load_glossary(cfg.glossary)
    cfg.system_plain = tr.SYSTEM_PROMPT.format(markers="", glossary=glossary)
    cfg.system_markers = tr.SYSTEM_PROMPT.format(markers=tr.MARKER_RULE, glossary=glossary)

    fields, rows = build.read_csv(cfg.translations)
    todo = []
    for r in rows:
        if r["status"] != "machine" or FORMAL_CUE.search(r["source"]):
            continue
        is_dlg = r["name"].startswith("dlg_")
        if (cfg.scope == "ui" and is_dlg) or (cfg.scope == "dlg" and not is_dlg):
            continue
        cls, _, _ = ca.address(r["uk"], "uk")
        target = "pl" if GROUP_CUE.search(r["source"]) else "sg"
        if target == "sg" and cls in ("pl", "mixed"):
            todo.append((r, target, cls))
        elif target == "pl" and cls in ("sg", "mixed"):
            todo.append((r, target, cls))
    n_sg = sum(1 for _, t, _ in todo if t == "sg")
    print(f"До виправлення: {len(todo)} (до однини {n_sg}, до множини {len(todo) - n_sg})")

    fixed = rejected = 0
    for i, (r, target, cls) in enumerate(todo, 1):
        if cfg.dry_run:
            if i <= 40:
                print(f"  {target} <- {cls}: [{r['voice'] or '-'}] {r['source'][:60]} | {r['uk'][:60]}")
            continue
        hint = HINT_PLURAL if target == "pl" else HINT_SINGLE
        protected, tokens = tr.protect(r["source"])
        done = False
        for attempt in range(3):
            try:
                answer = tr.ask(cfg, {"name": r["name"], "voice": r["voice"]}, protected, 0.1 + 0.2 * attempt,
                                bool(tokens), hint)
            except requests.RequestException as e:
                print(f"  ! {r['name']}: {e}")
                time.sleep(2)
                continue
            if not tr.valid(r["source"], answer, len(tokens)):
                continue
            new = tr.restore(answer, tokens)
            new_cls, _, _ = ca.address(new, "uk")
            if build.RU_WORDS.search(new):
                continue
            if new_cls == target or (new_cls == "-" and target == "sg"):
                r["uk"] = new
                fixed += 1
                done = True
                break
        if not done:
            rejected += 1
        if i % 25 == 0:
            tr.write_atomic(cfg.translations, fields, rows)
            print(f"  {i}/{len(todo)}, виправлено {fixed}, не вдалось узгодити {rejected}")
    if not cfg.dry_run:
        tr.write_atomic(cfg.translations, fields, rows)
    print(f"Готово: виправлено {fixed}, лишено як було {rejected}")


if __name__ == "__main__":
    main()
