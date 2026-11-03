import os

import pytest

from conftest import make_game
from d4loc import game, install, project


def test_validate_reasons(tmp_path):
    assert game.validate_game_dir("")[0] is False
    assert game.validate_game_dir(None)[0] is False
    assert "не існує" in game.validate_game_dir(str(tmp_path / "nope"))[1]
    (tmp_path / "other").mkdir()
    assert "не тека Dungeons 4" in game.validate_game_dir(str(tmp_path / "other"))[1]
    g = tmp_path / "half" / "Dungeons 4_Data"
    g.mkdir(parents=True)
    assert "AssetBundles" in game.validate_game_dir(str(tmp_path / "half"))[1]


def test_missing_english_text_is_rejected(tmp_path):
    g = make_game(tmp_path)
    os.remove(os.path.join(game.bundles_dir(g), "loca_en_texts.csv"))
    ok, why = game.validate_game_dir(g)
    assert not ok and "loca_en_texts.csv" in why


def test_valid_game_passes(game_dir):
    assert game.validate_game_dir(game_dir) == (True, "")


def test_parent_folder_is_resolved(tmp_path):
    g = make_game(tmp_path)
    parent = os.path.dirname(g)
    assert game.resolve_game_dir(parent) == g
    assert game.resolve_game_dir(g) == g
    assert game.resolve_game_dir("") == ""


@pytest.mark.parametrize("bad", [None, "", "C:/definitely/not/here"])
def test_library_refuses_to_write_to_invalid_folder(bad):
    with pytest.raises(ValueError):
        install.install_pack(bad, None, None, with_voice=False, log=lambda m: None)
    with pytest.raises(ValueError):
        install.uninstall(bad, log=lambda m: None)
    with pytest.raises(ValueError):
        project.unpack_language(bad, "uk", "proj", log=lambda m: None)


def test_compat_by_content_not_only_version(game_dir, content_pack):
    # the fake game has few keys/lines: compatibility must be "not ok", and the message must contain numbers
    ok, msg = install.check_compat(game_dir, content_pack)
    assert ok is False and ("Контент створено" in msg or "реплік" in msg)
