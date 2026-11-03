import os

from conftest import make_game
from d4loc import game


def test_is_game_dir(game_dir, tmp_path):
    assert game.is_game_dir(game_dir)
    assert not game.is_game_dir(str(tmp_path))
    assert not game.is_game_dir(None)


def test_list_languages(game_dir):
    langs = game.list_languages(game_dir)
    assert set(langs) == {"en", "ru", "de"}
    assert langs["en"]["texts"].endswith("loca_en_texts.csv") and langs["en"]["audio"] == []


def test_list_languages_sees_audio_bundles(tmp_path):
    g = make_game(tmp_path, with_audio_bundle=True)
    assert len(game.list_languages(g)["en"]["audio"]) == 1


def test_compare_versions():
    local = {"build": "abc", "steam_buildid": "1", "label": "L"}
    assert game.compare_versions({"build": "abc"}, local)[0]
    assert game.compare_versions({"steam_buildid": "1"}, local)[0]
    ok, msg = game.compare_versions({"build": "zzz", "steam_buildid": "2", "release": "v9"}, local)
    assert not ok and "У вас" in msg
    assert game.compare_versions({}, local)[0]  # a pack without a version does not block


def test_version_info_reads_version_txt(game_dir):
    d = os.path.join(game_dir, "Dungeons 4_Data", "rfdata")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "version.txt"), "w", encoding="utf-8") as f:
        f.write("v1.11 build4 @00f2081\nрешта\n")
    assert game.version_info(game_dir)["release"] == "v1.11 build4"
