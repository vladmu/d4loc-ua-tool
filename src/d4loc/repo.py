"""The translator's project folder = a fork of the content repository (d4loc-ua-content).

The repository itself is the unpacked Ukrainian language in the same structure the tool works with:
  uk/loca_uk_texts.csv             the translation in the game format (name, wording, voice, tags)
  uk/audio/<bundle path>   voice files where they lie in the game bundles (Ogg Opus; the tool encodes any new recording to .ogg itself)
  uk/audio_metadata.csv    line key -> path in the bundle
  en/                      the English unpacked from your game (not committed: .git/info/exclude)
The application checks that the given folder looks like a fork, lays the latest release into it when needed (an empty folder) and writes
edits into uk/. The git work itself (fork, clone, commit, push, pull request) is done by the user.
"""
import os
import re

from . import download
from .i18n import _

REMOTE_NAME = "d4loc-ua-content"    # this is the name of the content repository, and hence of its forks
LANG = "uk"
AUDIO_EXTS = (".ogg", ".flac", ".wav")


# ---------- checking the folder ----------
def _git_remotes(path):
    """Remote URLs from .git/config (without running git)."""
    cfg = os.path.join(path, ".git", "config")
    if not os.path.isfile(cfg):
        return []
    try:
        with open(cfg, encoding="utf-8", errors="replace") as f:
            return re.findall(r"^\s*url\s*=\s*(\S+)", f.read(), re.M)
    except OSError:
        return []


def inspect_folder(path):
    """(kind, message). Kinds: 'missing', 'not_dir', 'empty', 'content' (a fork or an unpacked release), 'foreign'.
    For 'content' the message may be a warning (for example, origin does not look like the content repository) or empty."""
    if not path or not str(path).strip():
        return "missing", _("Теку проєкту не вказано.")
    path = str(path)
    if os.path.isfile(path):
        return "not_dir", _("Це файл, а не тека.")
    if not os.path.isdir(path):
        return "missing", _("Такої теки не існує.")
    if not [e for e in os.listdir(path) if e != ".git"]:
        return "empty", ""
    if not (os.path.isfile(os.path.join(path, LANG, f"loca_{LANG}_texts.csv")) and os.path.isfile(os.path.join(path, "manifest.json"))):
        return "foreign", _("У цій теці вже є файли, але це не fork репозиторію контенту {0} (немає uk/loca_uk_texts.csv і manifest.json).").format(REMOTE_NAME)
    remotes = _git_remotes(path)
    if remotes and not any(REMOTE_NAME in r for r in remotes):
        return "content", _("Увага: адреса origin у git ({0}) не схожа на {1}. Переконайтесь, що це ваш fork контенту.").format(remotes[0], REMOTE_NAME)
    return "content", ""


def is_content_project(path):
    return inspect_folder(path)[0] == "content"


def add_git_exclude(project, entry):
    """Appends an entry to .git/info/exclude (locally, without touching .gitignore). Returns False if the folder is not a git repository."""
    if not os.path.isdir(os.path.join(project, ".git")):
        return False
    info = os.path.join(project, ".git", "info")
    os.makedirs(info, exist_ok=True)
    ex = os.path.join(info, "exclude")
    cur = open(ex, encoding="utf-8").read() if os.path.isfile(ex) else ""
    if entry not in cur.split():
        with open(ex, "a", encoding="utf-8", newline="\n") as f:
            f.write(("" if cur.endswith("\n") or not cur else "\n") + entry + "\n")
    return True


def ensure_git_exclude(project):
    """The English from the game (en/) and the queue of changes (uk/pending/) must never end up in a commit."""
    ok = add_git_exclude(project, "/en/")
    add_git_exclude(project, "pending/")
    add_git_exclude(project, "source.json")
    return ok


# ---------- laying a release into an empty folder ----------
def populate_from_release(project, progress=None, log=print, source=None, repo=None):
    """Empty folder: downloads the latest content release (manifest.json, loca_uk_texts.csv and voice.zip) and lays it out as in the content repository.
    The folder does not become a git repository: for a pull request the user must fork and clone it themselves. source (for tests): a local zip."""
    os.makedirs(project, exist_ok=True)
    if source and os.path.isfile(source):
        n = download.extract_zip(source, project)
        log(_("Контент розкладено в теку проєкту: {0} файлів.").format(n))
        return os.path.basename(source)
    release = download.fetch_release(repo=repo)
    if not release:
        raise RuntimeError(_("Не вдалося дізнатися останній реліз контенту (немає інтернету?)."))
    download.download_content(release, project, True, progress, log)
    return release.get("_tag") or release.get("version")


# ---------- voice files in the bundle structure ----------
def clip_path(lang_dir, container_path):
    """The line's file in uk/audio by the path from the bundle: the extension in the repository may be .ogg, .flac or .wav."""
    stem = os.path.splitext(container_path)[0]
    for ext in AUDIO_EXTS:
        p = os.path.join(lang_dir, "audio", stem + ext)
        if os.path.isfile(p):
            return p
    return ""


def store_clip(lang_dir, container_path, wav_path):
    """New recording of a line (a WAV from the queue; any input format has already been converted to WAV) -> .ogg in place of the old file.
    In the game the line goes the other way, decoded to PCM: the game bundles do not accept Ogg."""
    import soundfile as sf
    from . import oggenc
    data, rate = sf.read(wav_path, dtype="int16", always_2d=True)
    stem = os.path.join(lang_dir, "audio", os.path.splitext(container_path)[0])
    os.makedirs(os.path.dirname(stem), exist_ok=True)
    for ext in AUDIO_EXTS:
        if os.path.isfile(stem + ext):
            os.remove(stem + ext)
    oggenc.write_opus(stem + ".ogg", data, rate)
    return os.path.relpath(stem + ".ogg", os.path.dirname(lang_dir)).replace(os.sep, "/")
