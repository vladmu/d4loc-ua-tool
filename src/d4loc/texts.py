"""Game texts (loca_<lang>_texts.csv): reading, writing, registering the language in the menu."""
import csv
import os
import shutil
from .i18n import _

# How the game's language files name Ukrainian in different languages (the language selection menu)
UK_NAMES = {
    "en": "Ukrainian", "ar": "الأوكرانية (Ukrainian)", "de": "Ukrainisch (Ukrainian)", "es": "Ucraniano (Ukrainian)",
    "fr": "Ukrainien (Ukrainian)", "it": "Ucraino (Ukrainian)", "ja": "ウクライナ語 (Ukrainian)",
    "ko": "우크라이나어 (Ukrainian)", "pl": "ukraiński (Ukrainian)", "pt-br": "Ucraniano (Ukrainian)",
    "pt-pt": "Ucraniano (Ukrainian)", "ru": "украинский (Ukrainian)", "tr": "Ukraynaca (Ukrainian)",
    "zh-hans": "乌克兰语 (Ukrainian)", "zh-hant": "烏克蘭語 (Ukrainian)",
}
UK_SELF_NAME = "Українська (Ukrainian)"


def read_texts(path):
    """[(name, wording, voice, tags)] preserving order; an empty list if the file does not exist."""
    rows = []
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows.append((r.get("name", "").strip(), r.get("wording", ""), r.get("voice", ""), r.get("tags", "")))
    return rows


def write_texts(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["name", "wording", "voice", "tags"])
        w.writerows(rows)


BAK_PREFIX = "D4Loc_"
BAK_SUFFIX = ".bak"


def backup_path(path):
    """The backup lies next to the original: D4Loc_<name>.bak. The .bak extension and the D4Loc_ prefix are needed so that the game does not take
    the copy for a language file or bundle (those are always named loca_<lang>_... and end in .csv / .unity3d)."""
    return os.path.join(os.path.dirname(path), BAK_PREFIX + os.path.basename(path) + BAK_SUFFIX)


def backup_file(path):
    """Copies the file next to it as D4Loc_<name>.bak once (the original is not overwritten) and checks that the copy is exact."""
    dst = backup_path(path)
    if not os.path.exists(dst):
        shutil.copy2(path, dst)
        if os.path.getsize(dst) != os.path.getsize(path) or open(dst, "rb").read() != open(path, "rb").read():
            os.remove(dst)
            raise RuntimeError(_("Не вдалося створити точну резервну копію {0}. Нічого не змінено.").format(os.path.basename(path)))
    return dst


def backup_files(paths, log=print):
    """First backups of ALL the files that will be changed, and only then the change itself: if a copy fails, the game stays untouched."""
    n = 0
    for p in paths:
        if os.path.isfile(p):
            backup_file(p)
            n += 1
    log(_("Резервні копії створено й перевірено: {0} файлів").format(n))


def has_language_name(path, lang):
    key = f"_languageName_{lang}".encode()
    return b"\n" + key + b"," in b"\n" + open(path, "rb").read().replace(b"\r\n", b"\n")


def add_language_name(path, lang, value):
    """Appends a _languageName_<lang> line after the last _languageName_*; returns True if it changed the file."""
    data = open(path, "rb").read()
    if has_language_name(path, lang):
        return False
    nl = b"\r\n" if b"\r\n" in data else b"\n"
    line = f"_languageName_{lang},{value},,".encode("utf-8") + nl
    pos = data.rfind(b"_languageName_")
    if pos < 0:
        data += (b"" if data.endswith(nl) else nl) + line
    else:
        end = data.index(b"\n", pos) + 1
        data = data[:end] + line + data[end:]
    with open(path, "wb") as f:
        f.write(data)
    return True


def remove_language_name(path, lang):
    data = open(path, "rb").read()
    key = f"_languageName_{lang},".encode()
    out, changed = [], False
    for line in data.split(b"\n"):
        if line.startswith(key):
            changed = True
            continue
        out.append(line)
    if changed:
        with open(path, "wb") as f:
            f.write(b"\n".join(out))
    return changed


def register_language(bundles, lang, names, self_name, log=print):
    """Adds the language name to all existing loca_*_texts.csv (with a backup)."""
    import glob
    for p in sorted(glob.glob(os.path.join(bundles, "loca_*_texts.csv"))):
        code = os.path.basename(p)[5:-len("_texts.csv")]
        value = self_name if code == lang else names.get(code, names.get("en", self_name))
        if code != lang:   # we create our own language file ourselves, it has no original
            backup_file(p)
        if add_language_name(p, lang, value):
            log(f"назву мови додано: {os.path.basename(p)}")


def unregister_language(bundles, lang, log=print):
    import glob
    for p in sorted(glob.glob(os.path.join(bundles, "loca_*_texts.csv"))):
        if os.path.basename(p) == f"loca_{lang}_texts.csv":
            continue
        if remove_language_name(p, lang):
            log(f"назву мови прибрано: {os.path.basename(p)}")
