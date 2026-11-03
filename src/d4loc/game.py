"""Finding the game and its language files."""
import glob
import os
import re
from .i18n import _

GAME_DIRNAME = "Dungeons 4"
APPID = 1643310
BUNDLES_SUB = os.path.join("Dungeons 4_Data", "rfdata", "AssetBundles")
TEXT_RE = re.compile(r"^loca_(?P<lang>[a-z]{2}(?:-[a-z]{2,4})?)_texts\.csv$")
AUDIO_RE = re.compile(r"^loca_(?P<lang>[a-z]{2}(?:-[a-z]{2,4})?)_audio(?P<suffix>.*)\.unity3d$")


def _steam_libraries():
    paths = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            paths.append(winreg.QueryValueEx(k, name)[0])
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    paths += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    libs = []
    for steam in paths:
        steam = os.path.normpath(steam)
        libs.append(steam)
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            try:
                for m in re.finditer(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="replace").read()):
                    libs.append(os.path.normpath(m.group(1).replace("\\\\", "\\")))
            except OSError:
                pass
    seen, out = set(), []
    for p in libs:
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def _other_store_dirs():
    """Epic Games Store, GOG and the usual folders (best effort: not verified on every build)."""
    out = []
    try:  # Epic: manifests with InstallLocation
        base = os.path.join(os.environ.get("ProgramData", r"C:" + chr(92) + "ProgramData"), "Epic", "EpicGamesLauncher", "Data", "Manifests")
        if os.path.isdir(base):
            import json
            for f in os.listdir(base):
                if f.endswith(".item"):
                    d = json.load(open(os.path.join(base, f), encoding="utf-8", errors="replace"))
                    if "dungeons 4" in (d.get("DisplayName", "") or "").lower():
                        out.append(d.get("InstallLocation", ""))
    except (OSError, ValueError):
        pass
    try:  # GOG: registry
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE,):
            with winreg.OpenKey(hive, "SOFTWARE" + chr(92) + "WOW6432Node" + chr(92) + "GOG.com" + chr(92) + "Games") as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    with winreg.OpenKey(k, winreg.EnumKey(k, i)) as g:
                        try:
                            if "dungeons 4" in winreg.QueryValueEx(g, "gameName")[0].lower():
                                out.append(winreg.QueryValueEx(g, "path")[0])
                        except OSError:
                            pass
    except (ImportError, OSError):
        pass
    for root in (r"C:" + chr(92) + "GOG Games", r"C:" + chr(92) + "Program Files (x86)" + chr(92) + "GOG Galaxy" + chr(92) + "Games",
                 r"C:" + chr(92) + "Program Files" + chr(92) + "Epic Games", r"D:" + chr(92) + "Games", r"C:" + chr(92) + "Games"):
        for n in ("Dungeons 4", "Dungeons4"):
            out.append(os.path.join(root, n))
    return out


def find_game_dir(remembered=None):
    """The game folder (the one containing 'Dungeons 4_Data') or None.
    Order: the one remembered by the user -> Steam libraries via appmanifest_<appid>.acf (the real folder name) -> a 'Dungeons 4' folder."""
    if remembered and is_game_dir(remembered):
        return remembered
    for lib in _steam_libraries():
        steamapps = os.path.join(lib, "steamapps")
        names = []
        acf = os.path.join(steamapps, f"appmanifest_{APPID}.acf")
        try:
            m = re.search(r'"installdir"\s+"([^"]+)"', open(acf, encoding="utf-8", errors="replace").read())
            if m:
                names.append(m.group(1))
        except OSError:
            pass
        names.append(GAME_DIRNAME)
        for n in names:
            cand = os.path.join(steamapps, "common", n)
            if is_game_dir(cand):
                return cand
    for cand in _other_store_dirs():
        if is_game_dir(cand):
            return cand
    return None


def resolve_game_dir(path):
    """If a parent folder is given (e.g. steamapps/common), look for 'Dungeons 4' inside it; otherwise return it as is."""
    if not path:
        return path
    if is_game_dir(path):
        return path
    for n in (GAME_DIRNAME, "Dungeons4"):
        cand = os.path.join(path, n)
        if is_game_dir(cand):
            return cand
    return path


def validate_game_dir(path):
    """(ok, reason): is the game folder suitable for installation? The reasons are in Ukrainian, to be shown to the user."""
    if not path or not str(path).strip():
        return False, _("Теку гри не вказано.")
    path = str(path)
    if not os.path.isdir(path):
        return False, _("Такої теки не існує.")
    if not os.path.isdir(os.path.join(path, "Dungeons 4_Data")):
        return False, _("Це не тека Dungeons 4: у ній нема підтеки «Dungeons 4_Data».")
    b = bundles_dir(path)
    if not os.path.isdir(b):
        return False, _("У теці гри нема «Dungeons 4_Data\\rfdata\\AssetBundles». Можливо, це інша версія гри або пошкоджена установка.")
    if not os.path.isfile(os.path.join(b, "loca_en_texts.csv")):
        return False, _("У теці гри нема англійського тексту loca_en_texts.csv (гра пошкоджена або це не Dungeons 4).")
    if not os.access(b, os.W_OK):
        return False, _("Нема права запису в теку гри. Запустіть застосунок від імені адміністратора або перенесіть гру.")
    return True, ""


def require_game_dir(path):
    """For functions that write into the game folder: stop immediately if the folder is not suitable."""
    ok, why = validate_game_dir(path)
    if not ok:
        raise ValueError(why)
    return path


def is_game_dir(path):
    return bool(path) and os.path.isdir(os.path.join(str(path), BUNDLES_SUB))


def bundles_dir(game_dir):
    return os.path.join(game_dir, BUNDLES_SUB)


def list_languages(game_dir):
    """{code: {'texts': path|None, 'audio': [bundle paths]}} for the languages found in the game."""
    b = bundles_dir(game_dir)
    langs = {}
    for f in sorted(os.listdir(b)):
        m = TEXT_RE.match(f)
        if m:
            langs.setdefault(m.group("lang"), {"texts": None, "audio": []})["texts"] = os.path.join(b, f)
        m = AUDIO_RE.match(f)
        if m:
            langs.setdefault(m.group("lang"), {"texts": None, "audio": []})["audio"].append(os.path.join(b, f))
    return langs


def audio_bundle_names(game_dir, lang="en"):
    return sorted(os.path.basename(p) for p in list_languages(game_dir).get(lang, {}).get("audio", []))



def version_info(game_dir):
    """Version of the installed game: {'build': Unity project build hash | None, 'steam_buildid': str | None, 'label': a string}."""
    info = {"build": None, "steam_buildid": None, "release": None}
    try:  # a readable game version, e.g. "v1.11 build4 @00f2081"
        with open(os.path.join(game_dir, "Dungeons 4_Data", "rfdata", "version.txt"), encoding="utf-8") as f:
            first = f.readline().strip()
        info["release"] = first.split("@")[0].strip() or None
    except OSError:
        pass
    try:
        import UnityPy
        env = UnityPy.load(os.path.join(game_dir, "Dungeons 4_Data", "globalgamemanagers"))
        for obj in env.objects:
            if obj.type.name == "PlayerSettings":
                v = (obj.read_typetree().get("bundleVersion") or "").strip()
                info["build"] = v or None
                break
    except Exception:
        pass
    # Steam: appmanifest_<appid>.acf lies in steamapps next to common/
    acf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(game_dir))), f"appmanifest_{APPID}.acf")
    try:
        m = re.search(r'"buildid"\s+"(\d+)"', open(acf, encoding="utf-8", errors="replace").read())
        info["steam_buildid"] = m.group(1) if m else None
    except OSError:
        pass
    parts = []
    if info["release"]:
        parts.append(info["release"])
    if info["build"]:
        parts.append(_("збірка {0}").format(info['build'][:8]))
    if info["steam_buildid"]:
        parts.append(f"Steam {info['steam_buildid']}")
    info["label"] = ", ".join(parts) or _("версію не вдалося визначити")
    return info


def compare_versions(pack_game, local):
    """(matches?, message). pack_game is the 'game' dictionary from the pack's manifest.json."""
    if not pack_game or not (pack_game.get("build") or pack_game.get("steam_buildid")):
        return True, _("Контент не вказує версію гри.")
    same_build = pack_game.get("build") and local.get("build") and pack_game["build"] == local["build"]
    same_steam = pack_game.get("steam_buildid") and local.get("steam_buildid") and pack_game["steam_buildid"] == local["steam_buildid"]
    if same_build or same_steam:
        return True, _("Версія гри збігається з контентом.")
    want = ", ".join(x for x in (_("збірка {0}").format(str(pack_game.get('build') or '')[:8]) if pack_game.get("build") else "",
                                  f"Steam {pack_game.get('steam_buildid')}" if pack_game.get("steam_buildid") else "") if x)
    return False, _("Контент створено для гри: {0}. У вас: {1}.").format(want, local['label'])
