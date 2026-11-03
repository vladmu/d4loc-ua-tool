"""Downloading content from the latest release of the content repository. A release consists of three files:

  manifest.json       the content version and the game version it was made for (kept separate, not archived)
  loca_uk_texts.csv   the translation: the game file as is (not archived); this is the "text only" mode
  voice.zip           the voices (uk/audio/** and uk/audio_metadata.csv) in one archive

Everything is laid out in the pack folder exactly as in the content repository (manifest.json, uk/loca_uk_texts.csv, uk/audio/**), and both the
installer and the translator tool work from it. Files are downloaded with resume support; integrity is checked by the size of every file
and by the CRC of the files in the archive. Nothing is taken from repository branches: only from the release. The application and the content live in separate repositories, so a new version
of the translation can be published without rebuilding the application.
The address can be overridden with the environment variable D4LOC_RELEASE_BASE (a server folder with these three files; for tests)."""
import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

from . import VERSION
from .i18n import _

REPO = "vladmu/d4loc-ua-content"   # content repository (translation and voice-over); application code: d4loc-ua-tool
MANIFEST_ASSET = "manifest.json"
TEXT_ASSET = "loca_uk_texts.csv"
VOICE_ASSET = "voice.zip"
ASSETS = (MANIFEST_ASSET, TEXT_ASSET, VOICE_ASSET)
USER_AGENT = f"D4LocToolkit/{VERSION}"


def _open(url, headers=None, timeout=15, method="GET"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})}, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def release_base():
    base = os.environ.get("D4LOC_RELEASE_BASE")
    return (base if base.endswith("/") else base + "/") if base else None


def pack_dir_in(data_dir):
    """The content pack lives in the data folder (the same place as the translator project), not next to the .exe."""
    return os.path.join(data_dir, "uk_pack")


def temp_dir():
    """Temporary download folder used when there is no ready pack: a fixed name so that an interrupted download can be resumed."""
    import tempfile
    return os.path.join(tempfile.gettempdir(), "D4LocToolkit-download")


def normalize_repo(repo):
    """"owner/name" from "owner/name", "https://github.com/owner/name" or "https://github.com/owner/name.git"; the default repository if empty."""
    repo = (repo or "").strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if repo.startswith(prefix):
            repo = repo[len(prefix):]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return repo or REPO


def _release_info(timeout, repo=None):
    """The latest release of the content repository, found through the plain download links https://github.com/<repo>/releases/latest/download/<file>:
    the size of every file comes from the response headers. The GitHub API is not used on purpose: it allows only 60 requests an hour from one address
    without a token, and many players may share an address. The links have no such limit. {'tag': None, 'assets': {name: {size, url, sha256: None}}} or None."""
    base = f"https://github.com/{normalize_repo(repo)}/releases/latest/download/"
    assets = {}
    for name in ASSETS:
        try:
            with _open(base + name, timeout=timeout, method="HEAD") as r:
                assets[name] = {"size": int(r.headers.get("Content-Length") or 0), "url": base + name, "sha256": None}
        except (urllib.error.URLError, OSError, ValueError):
            pass
    if MANIFEST_ASSET in assets and TEXT_ASSET in assets:
        return {"tag": None, "assets": assets}
    return None


def exe_dir():
    """The folder of the built executable; None when the application runs from source."""
    return os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else None


def local_release(folder=None):
    """A release made of the files that lie next to the executable: manifest.json and loca_uk_texts.csv (and, for the voices, voice.zip), exactly
    the files of a release of the content repository. With them the installation needs no internet. None if the two required files are not there."""
    folder = folder or exe_dir()
    if not folder:
        return None
    paths = {name: os.path.join(folder, name) for name in ASSETS}
    if not (os.path.isfile(paths[MANIFEST_ASSET]) and os.path.isfile(paths[TEXT_ASSET])):
        return None
    try:
        with open(paths[MANIFEST_ASSET], encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return None
    assets = {name: {"size": os.path.getsize(p), "url": None, "path": p, "sha256": None} for name, p in paths.items() if os.path.isfile(p)}
    return {"version": manifest.get("version"), "_tag": None, "manifest": manifest, "assets": assets, "local": folder}


def _remote_release(timeout, repo=None):
    """The latest release of the content repository: {'version', '_tag', 'manifest', 'assets'} or None if there is no network or release."""
    try:
        base = release_base()
        if base:                                           # test server
            assets = {}
            for name in ASSETS:
                try:
                    with _open(base + name, timeout=timeout, method="HEAD") as r:
                        assets[name] = {"size": int(r.headers.get("Content-Length") or 0), "url": base + name, "sha256": None}
                except (urllib.error.URLError, OSError, ValueError):
                    pass
            info = {"tag": None, "assets": assets}
        else:
            info = _release_info(timeout, repo)
        if not info or MANIFEST_ASSET not in info["assets"]:
            return None
        with _open(info["assets"][MANIFEST_ASSET]["url"], timeout=timeout) as r:
            manifest = json.loads(r.read().decode("utf-8"))
        return {"version": manifest.get("version") or (info["tag"] or "").lstrip("v") or None, "_tag": info["tag"],
                "manifest": manifest, "assets": info["assets"]}
    except (urllib.error.URLError, OSError, ValueError):
        return None


def fetch_release(timeout=6, local_dir=None, repo=None):
    """The release to install from: {'version', '_tag', 'manifest' (the release's manifest.json), 'assets' {name: {size, url or path, sha256}}} or None.
    Release files that lie next to the executable (local_release) are used as they are; a file that is missing there (the voices, voice.zip) is taken
    from the repository if it belongs to the same version of the content. Without such files everything comes from the latest release of the repository (repo: "owner/name" of the official one or of a fork)."""
    local = local_release(local_dir)
    if not local:
        return _remote_release(timeout, repo)
    if VOICE_ASSET not in local["assets"]:
        remote = _remote_release(timeout, repo)
        if remote and VOICE_ASSET in remote["assets"] and remote["manifest"].get("version") == local["manifest"].get("version"):
            local["assets"][VOICE_ASSET] = remote["assets"][VOICE_ASSET]
    return local


def is_local(asset):
    """True if the file lies next to the program (it is copied), False if it has to be downloaded."""
    return bool(asset and asset.get("path"))


def download_size(release, with_voice=True):
    """How much has to be downloaded from the repository: only the files that do not lie next to the program."""
    names = (MANIFEST_ASSET, TEXT_ASSET) + ((VOICE_ASSET,) if with_voice else ())
    return sum(asset_size(release, n) for n in names if not is_local(((release or {}).get("assets") or {}).get(n)))


def asset_size(release, name):
    return ((release or {}).get("assets", {}).get(name) or {}).get("size", 0)


def total_size(release, with_voice=True):
    """How much needs to be downloaded: the text with the manifest (small) and, if needed, the voices."""
    return asset_size(release, MANIFEST_ASSET) + asset_size(release, TEXT_ASSET) + (asset_size(release, VOICE_ASSET) if with_voice else 0)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_zip(zpath, dest):
    """Checks the CRC of the archive's files and unpacks it into dest, never letting paths escape the folder. Returns the number of files."""
    with zipfile.ZipFile(zpath) as z:
        bad = z.testzip()
        if bad:
            raise zipfile.BadZipFile(bad)
        root = os.path.abspath(dest)
        infos = [i for i in z.infolist() if not i.is_dir()]
        for info in infos:
            target = os.path.abspath(os.path.join(dest, info.filename))
            if not target.startswith(root + os.sep):
                raise RuntimeError(_("Небезпечний шлях в архіві: {0}").format(info.filename))
        z.extractall(dest)
    return len(infos)


def make_voice_zip(content_dir, zpath):
    """voice.zip: uk/audio_metadata.csv and everything under uk/audio in one archive, with the paths of the content folder (the pair of extract_zip).
    The audio is already compressed, so it is only stored. Returns the number of audio files."""
    count = 0
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(os.path.join(content_dir, "uk", "audio_metadata.csv"), "uk/audio_metadata.csv", compress_type=zipfile.ZIP_DEFLATED)
        for d, _dirs, files in os.walk(os.path.join(content_dir, "uk", "audio")):
            for fn in sorted(files):
                full = os.path.join(d, fn)
                rel = os.path.relpath(full, content_dir).replace(os.sep, "/")
                z.write(full, rel, compress_type=zipfile.ZIP_STORED if fn.lower().endswith((".ogg", ".flac")) else zipfile.ZIP_DEFLATED)
                count += 1
    return count


def build_release(content_dir, out_dir):
    """The three files of a content release (the pair of download_content): manifest.json and loca_uk_texts.csv as they are in the content folder,
    and voice.zip. Checks that they unpack into something that looks like a content pack. Returns (number of voices, number of audio files)."""
    import shutil
    import tempfile
    from . import install
    text = os.path.join(content_dir, "uk", install.TEXT_FILE)
    manifest = os.path.join(content_dir, "manifest.json")
    os.makedirs(out_dir, exist_ok=True)
    tmp_zip = os.path.join(out_dir, VOICE_ASSET + ".new")
    count = make_voice_zip(content_dir, tmp_zip)
    with tempfile.TemporaryDirectory(prefix="d4loc_release_check_") as tmp:
        shutil.copy2(manifest, os.path.join(tmp, MANIFEST_ASSET))
        os.makedirs(os.path.join(tmp, "uk"))
        shutil.copy2(text, os.path.join(tmp, "uk", install.TEXT_FILE))
        extract_zip(tmp_zip, tmp)
        ok = install.has_content(tmp)
        voices = len(install.voice_files(tmp))
    if not ok or not voices:
        os.remove(tmp_zip)
        raise RuntimeError("The release files do not look like a content pack")
    for old in os.listdir(out_dir):
        if old != VOICE_ASSET + ".new":
            os.remove(os.path.join(out_dir, old))
    shutil.copy2(manifest, os.path.join(out_dir, MANIFEST_ASSET))
    shutil.copy2(text, os.path.join(out_dir, TEXT_ASSET))
    os.replace(tmp_zip, os.path.join(out_dir, VOICE_ASSET))
    return voices, count


def _fetch_file(release, name, target, progress, log):
    """Downloads a release file into target (with resume and SHA-256 verification) and returns the path."""
    a = (release.get("assets") or {}).get(name)
    if not a or not (a.get("url") or a.get("path")):
        raise RuntimeError(_("У релізі немає файлу {0}.").format(name))
    size, want = a.get("size", 0), a.get("sha256")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    part = target + ".part"
    if a.get("path"):          # a file next to the executable: copied (the original is never touched), no network
        log(_("Беру {0} ({1:.1f} МБ) поряд із програмою").format(name, size / 2**20))
        shutil.copyfile(a["path"], part)
        return part
    start = os.path.getsize(part) if os.path.isfile(part) else 0
    if start and size and start > size:
        os.remove(part)
        start = 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    log(_("Завантажую {0} ({1:.1f} МБ){2}").format(name, size / 2**20, ' — докачування з ' + str(start // 2**20) + ' МБ' if start else ''))
    if not (size and start == size):
        with _open(a["url"], headers, timeout=30) as r:
            if start and getattr(r, "status", 200) != 206:
                start = 0  # the server does not support resuming: start over
            with open(part, "ab" if start else "wb") as f:
                done = start
                for chunk in iter(lambda: r.read(1 << 20), b""):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, max(size, done, 1), _("{0}: {1:.0f} з {2:.0f} МБ").format(name, done / 2**20, max(size, done) / 2**20))
    if want and sha256_file(part) != want:
        os.remove(part)
        raise RuntimeError(_("Контрольна сума {0} не збігається. Файл видалено, спробуйте ще раз.").format(name))
    return part


def _mark_complete(dest, release):
    with open(os.path.join(dest, ".complete"), "w", encoding="utf-8") as f:
        json.dump({"version": release.get("version"), "tag": release.get("_tag")}, f)


def download_text(release, dest, progress=None, log=print):
    """manifest.json and loca_uk_texts.csv ("text only" mode): puts manifest.json and uk/loca_uk_texts.csv into the pack folder dest."""
    for name, rel in ((MANIFEST_ASSET, MANIFEST_ASSET), (TEXT_ASSET, os.path.join("uk", TEXT_ASSET))):
        part = _fetch_file(release, name, os.path.join(dest, rel), progress, log)
        os.replace(part, os.path.join(dest, rel))
    _mark_complete(dest, release)
    return dest


def download_voice(release, dest, progress=None, log=print):
    """voice.zip: downloads and unpacks the voices into uk/audio and uk/audio_metadata.csv of the pack folder dest."""
    part = _fetch_file(release, VOICE_ASSET, os.path.join(dest, VOICE_ASSET), progress, log)
    try:
        extract_zip(part, dest)
    except zipfile.BadZipFile:
        os.remove(part)
        raise RuntimeError(_("Архів {0} пошкоджений. Файл видалено, спробуйте ще раз.").format(VOICE_ASSET))
    os.remove(part)
    _mark_complete(dest, release)
    log(_("Контент розпаковано: {0}").format(dest))
    return dest


def download_content(release, dest, with_voice=True, progress=None, log=print):
    """What is missing from the pack folder dest: the text (if absent) and the voices (if needed and absent)."""
    from . import install
    os.makedirs(dest, exist_ok=True)
    if not install.has_content(dest):
        download_text(release, dest, progress, log)
    if with_voice and not install.has_voice(dest):
        download_voice(release, dest, progress, log)
    return dest


def cleanup(dest):
    """Removes content that we downloaded ourselves (a folder with a .complete marker). Never touches a folder that is a git repository (a fork)."""
    import shutil
    if os.path.isfile(os.path.join(dest, ".complete")) and not os.path.isdir(os.path.join(dest, ".git")):
        shutil.rmtree(dest, ignore_errors=True)
        return True
    return False
