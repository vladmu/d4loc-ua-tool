import os

from d4loc import game, texts


def test_read_write_roundtrip(tmp_path):
    p = tmp_path / "t.csv"
    rows = [("a", "Привіт, світе", "", ""), ("b", "з «лапками», комами\nі переносом", "thalya", "x")]
    texts.write_texts(str(p), rows)
    assert texts.read_texts(str(p)) == rows


def test_read_missing_file_is_empty(tmp_path):
    assert texts.read_texts(str(tmp_path / "nope.csv")) == []


def test_add_and_remove_language_name(game_dir):
    p = game.bundles_dir(game_dir) + "/loca_en_texts.csv"
    assert not texts.has_language_name(p, "uk")
    assert texts.add_language_name(p, "uk", "Ukrainian") is True
    assert texts.has_language_name(p, "uk")
    assert texts.add_language_name(p, "uk", "Ukrainian") is False  # idempotent
    assert texts.remove_language_name(p, "uk") is True
    assert not texts.has_language_name(p, "uk")
    assert texts.remove_language_name(p, "uk") is False


def test_name_inserted_after_last_language_name(game_dir):
    p = game.bundles_dir(game_dir) + "/loca_ru_texts.csv"
    texts.add_language_name(p, "uk", "украинский")
    lines = open(p, "rb").read().decode("utf-8-sig").splitlines()
    i = [n for n, line in enumerate(lines) if line.startswith("_languageName_uk")][0]
    assert lines[i - 1].startswith("_languageName_tr")  # right after the last _languageName_*


def test_register_and_unregister_make_backups(game_dir, tmp_path):
    b = game.bundles_dir(game_dir)
    texts.register_language(b, "uk", texts.UK_NAMES, texts.UK_SELF_NAME, log=lambda m: None)
    for lang in ("en", "ru", "de"):
        assert texts.has_language_name(f"{b}/loca_{lang}_texts.csv", "uk")
    assert sorted(f for f in os.listdir(b) if f.endswith(".bak")) == [
        "D4Loc_loca_de_texts.csv.bak", "D4Loc_loca_en_texts.csv.bak", "D4Loc_loca_ru_texts.csv.bak"]
    texts.unregister_language(b, "uk", log=lambda m: None)
    for lang in ("en", "ru", "de"):
        assert not texts.has_language_name(f"{b}/loca_{lang}_texts.csv", "uk")
