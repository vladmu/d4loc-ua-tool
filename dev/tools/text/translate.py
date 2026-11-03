import argparse
import csv
import os

from tools import paths
from tools.text import public
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# Service markup that must not be given to the model: {attack:Damage}, <color=#..>, </color>, \n, %s
TOKEN_RE = re.compile(r"\{[^{}]*\}|<[^<>]*>|\\n|%\w")
MARK_RE = re.compile(r"⟦(\d+)⟧")
LETTER_RE = re.compile(r"[A-Za-z]")
CYRILLIC_RE = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
RU_ONLY_RE = re.compile(r"[ыэъёЫЭЪЁ]")
FOREIGN_RE = re.compile(r"[À-ɏ]")  # Latin with diacritics (Polish ł, ó and so on)
THINK_RE =re.compile(r"<think>.*?</think>", re.S)

SYSTEM_PROMPT = """You are a professional game localizer translating the humorous fantasy strategy game Dungeons 4 from English into Ukrainian.
Rules:
- Output ONLY the Ukrainian translation. No explanations, notes, quotes or prefixes.
- Use natural, idiomatic Ukrainian. Never use Russian, Polish or any other language.
{markers}- Keep line breaks as in the source.
- When "you" addresses one player, use the informal, playful «ти» (e.g. «Ти завершив…», «Знищ 40 героїв»). Use «ви» only when "you" clearly means several people or the context demands respect (e.g. addressing another character formally). In dialogue use «ти» unless the context clearly requires «ви».
- Do not capitalize common nouns in the middle of a sentence (write «темні ельфи», «герої», not «Темні Ельфи») unless the glossary says so.
- Keep the tone of the speaker (the Overlord is theatrical and sarcastic; characters may speak in dialect).
- Keep it short enough for UI where the source is short.{glossary}"""

MARKER_RULE = "- The text contains markers like ⟦0⟧, ⟦1⟧ for game variables and formatting. Copy every marker exactly once, unchanged, in a grammatically sensible place. Never invent markers that are not in the source.\n"


def protect(text):
    tokens = []

    def repl(m):
        tokens.append(m.group(0))
        return f"⟦{len(tokens) - 1}⟧"

    return TOKEN_RE.sub(repl, text), tokens


def restore(text, tokens):
    return MARK_RE.sub(lambda m: tokens[int(m.group(1))], text)


def valid(source, answer, n_tokens):
    found = sorted(int(x) for x in MARK_RE.findall(answer))
    if found != list(range(n_tokens)):
        return False
    if answer.count("\n") != source.count("\n"):
        return False
    if RU_ONLY_RE.search(answer) or FOREIGN_RE.search(answer) or not CYRILLIC_RE.search(answer):
        return False
    if len(source) > 20 and len(answer) > 4 * len(source):
        return False
    return True


def load_glossary(path):
    if not path or not os.path.isfile(path):
        return ""
    lines = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                lines.append(line.strip())
    return "\nUse these fixed term translations:\n" + "\n".join(lines) if lines else ""


def ask(cfg, row, protected, temperature, has_markers, hint=""):
    user = f"ID: {row['name']}\n"
    if row.get("voice"):
        user += f"Speaker: {row['voice']}\n"
    if hint:
        user += f"Note: {hint}\n"
    user += f"Text:\n{protected}"
    resp = requests.post(
        cfg.api.rstrip("/") + "/chat/completions",
        json={
            "model": cfg.model,
            "temperature": temperature,
            "max_tokens": int(len(protected) * 1.2) + 96,  # insurance against a loop that clogs the context
            "messages": [
                {"role": "system", "content": cfg.system_markers if has_markers else cfg.system_plain},
                {"role": "user", "content": user},
            ],
        },
        timeout=cfg.timeout,
    )
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"]
    answer = THINK_RE.sub("", answer).strip()
    answer = re.sub(r"^(Text|Переклад|Translation):\s*", "", answer).strip()
    if "\n" not in protected:  # the model likes to split two sentences into lines, while the original has none
        answer = re.sub(r"\s*\n\s*", " ", answer)
    return answer


# Service keys that are not translated (formats, links, language names are built by the build script)
COPY_PREFIXES = ("_format_", "_lp_", "_audiolocale", "_languageName_")


# Names, links and brands that are the same in all the game's languages (verified by comparing en/ru/de)
COPY_NAMES = {
    "_title_capt", "dlc_deluxe_capt", "msgbox_option_ok", "ui_ok", "ui_anniversary_dungeons4",
    "ui_anniversary_kalypso", "ui_menu_purchase_switch", "ui_modding_overlay",
    "ui_modding_welcome_link_discord", "ui_setting_skinhand_val_legacy_capt",
}


def should_copy(name, source):
    if name.startswith(COPY_PREFIXES) or name in COPY_NAMES or "://" in source:
        return True
    return not LETTER_RE.search(MARK_RE.sub("", protect(source)[0]))


def translate_row(cfg, row):
    source = row["wording"]
    if should_copy(row["name"], source):
        return row["name"], source, "copied"
    protected, tokens = protect(source)
    for attempt in range(cfg.retries):
        try:
            answer = ask(cfg, row, protected, 0.1 + 0.2 * attempt, bool(tokens))
        except requests.RequestException as e:
            print(f"  ! {row['name']}: запит не вдався ({e})")
            time.sleep(2)
            continue
        if valid(source, answer, len(tokens)):
            return row["name"], restore(answer, tokens), "machine"
    return row["name"], "", "failed"


def load_existing(path):
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return {r["name"]: r for r in csv.DictReader(f)}


def write_atomic(path, fieldnames, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description="Переклад loca_en_texts.csv українською через локальну LLM")
    p.add_argument("--input", default=paths.EN_TEXTS)
    p.add_argument("--translations", default=paths.TRANSLATIONS)
    p.add_argument("--glossary", default=paths.GLOSSARY, help="рядки 'English = Українська'")
    p.add_argument("--api", default="http://127.0.0.1:9931/v1")
    p.add_argument("--model", default="qwen")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--limit", type=int, default=0, help="перекласти лише N нових рядків (для тесту)")
    cfg = p.parse_args()
    public.ensure_table(cfg.translations)       # a fresh work folder: rebuilt from content/uk, not translated again
    glossary = load_glossary(cfg.glossary)
    cfg.system_plain = SYSTEM_PROMPT.format(markers="", glossary=glossary)
    cfg.system_markers = SYSTEM_PROMPT.format(markers=MARKER_RULE, glossary=glossary)

    with open(cfg.input, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        src_fields = reader.fieldnames
        src_rows = list(reader)

    done = load_existing(cfg.translations)
    fields = ["name", "voice", "source", "uk", "status"]
    result = {}
    todo = []
    for r in src_rows:
        old = done.get(r["name"])
        if old and (old["status"] in ("edited", "user", "recorded") or
                    (old["status"] in ("machine", "copied") and old["source"] == r["wording"]
                     and (old["status"] == "copied") == should_copy(r["name"], r["wording"]))):
            result[r["name"]] = old
        else:
            todo.append(r)
    if cfg.limit:
        todo = todo[:cfg.limit]
    print(f"Рядків: {len(src_rows)}, вже готово: {len(result)}, до перекладу: {len(todo)}")

    def snapshot():
        rows = [result[r["name"]] for r in src_rows if r["name"] in result]
        write_atomic(cfg.translations, fields, rows)

    start = time.time()
    by_name = {r["name"]: r for r in todo}
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = [pool.submit(translate_row, cfg, r) for r in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            name, uk, status = fut.result()
            r = by_name[name]
            result[name] = {"name": name, "voice": r.get("voice", ""), "source": r["wording"],
                            "uk": uk, "status": status}
            if status == "failed":
                print(f"  ! не вдалось: {name}")
            if i % 50 == 0:
                snapshot()
                print(f"  {i}/{len(todo)}, {time.time() - start:.0f} с")
    snapshot()

    failed = sum(1 for t in result.values() if t["status"] == "failed")
    print(f"Готово: {cfg.translations} (не вдалось: {failed}). Далі: python dev/run.py build")


if __name__ == "__main__":
    main()
