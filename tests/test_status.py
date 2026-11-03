"""The status of every line (uk/status.csv in the content repository): the translator tool marks what a person changed, the pipeline respects it."""
import csv
import os

import pytest

from d4loc import project, repo, status, texts, toolcheck
from tools import paths
from tools.text import public
from tools.voice import store


def test_status_file_is_sorted_and_read_back(tmp_path):
    status.write(str(tmp_path), {"b": "machine", "a": "edited"})
    assert (tmp_path / "status.csv").read_bytes().decode("utf-8-sig") == "name,status\na,edited\nb,machine\n"      # LF, sorted: small diffs in a pull request
    assert status.read(str(tmp_path)) == {"a": "edited", "b": "machine"}
    assert status.read(str(tmp_path / "nothing")) == {}


def test_mark_texts_as_user_and_recordings_as_recorded(tmp_path):
    status.write(str(tmp_path), {"a": "machine", "b": "machine", "c": "machine"})
    assert status.mark(str(tmp_path), texts=["a", "b"], recordings=["b"]) == 2
    assert status.read(str(tmp_path)) == {"a": "user", "b": "recorded", "c": "machine"}       # a recording wins over a text change
    status.mark(str(tmp_path), texts=["b"])
    assert status.read(str(tmp_path))["b"] == "recorded"                                    # a later text edit does not lower a recorded line


def test_save_marks_changed_lines_in_the_fork(content_pack, tmp_path, monkeypatch):
    """«Save» in the translator tool: a text that really changed becomes `user`; untouched lines are not marked."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    proj = str(content_pack)
    with open(os.path.join(proj, "uk", "loca_uk_texts.csv"), "wb") as f:
        f.write(("name,wording,voice,tags\r\nhello,Привіт,,\r\nbye,Бувай,,\r\n").encode("utf-8-sig"))
    project.save_pending_texts(proj, "uk", {"hello": "Вітаю", "bye": "Бувай"})              # `bye` is "edited" to the same text: not a change
    project.save(proj, "uk", log=lambda m: None)
    assert status.read(os.path.join(proj, "uk")) == {"hello": "user"}


def test_toolcheck_covers_the_status_file(content_pack):
    proj = str(content_pack)
    status.write(os.path.join(proj, "uk"), {"hello": "machine"})
    assert "uk/status.csv" in toolcheck.tracked_files(proj)


def test_a_recorded_line_is_never_synthesized_again(tmp_path):
    dst = str(tmp_path / "a.ogg")
    import numpy as np
    store.write_clip(dst, np.zeros(4800, dtype="float32"), 24000)
    assert store.decide(dst, "s", "other-sig", recorded=True) == "community"        # even though the text changed
    assert store.decide(dst, "s", "other-sig", recorded=False) == "make"


def point_paths(monkeypatch, tmp_path):
    content = tmp_path / "content"
    for name, rel in (("CONTENT", ""), ("CONTENT_UK", "uk"), ("CONTENT_TEXTS", "uk/loca_uk_texts.csv"), ("CONTENT_EN", "en"),
                      ("EN_TEXTS", "en/loca_en_texts.csv")):
        monkeypatch.setattr(paths, name, os.path.join(str(content), *rel.split("/")) if rel else str(content))
    monkeypatch.setattr(paths, "TRANSLATIONS", str(tmp_path / "workspace" / "translations_uk.csv"))
    monkeypatch.setattr(paths, "WORK", str(tmp_path / "workspace"))
    monkeypatch.setattr(paths, "BUILT_SNAPSHOT", str(tmp_path / "workspace" / "built_snapshot.csv"))
    return content


def test_sync_rebuilds_the_working_table_from_content(tmp_path, monkeypatch):
    """No local table (a fresh checkout): text and status come from content/uk, the English original from content/en."""
    content = point_paths(monkeypatch, tmp_path)
    (content / "uk").mkdir(parents=True)
    (content / "en").mkdir()
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Привіт", "", ""), ("ui_b", "Бувай", "narrator", "")])
    texts.write_texts(str(content / "en" / "loca_en_texts.csv"), [("ui_a", "Hi", "", ""), ("ui_b", "Bye", "", "")])
    status.write(str(content / "uk"), {"ui_a": "recorded"})
    public.sync()
    rows = list(csv.DictReader(open(paths.TRANSLATIONS, encoding="utf-8-sig", newline="")))
    got = {r["name"]: r for r in rows}
    assert got["ui_a"]["uk"] == "Привіт" and got["ui_a"]["source"] == "Hi" and got["ui_a"]["status"] == "recorded"
    assert got["ui_b"]["voice"] == "narrator" and got["ui_b"]["status"] == "edited"          # no mark in status.csv: treated as edited


def test_export_keeps_a_persons_mark(tmp_path, monkeypatch):
    content = point_paths(monkeypatch, tmp_path)
    (content / "uk").mkdir(parents=True)
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Привіт", "", ""), ("ui_b", "Бувай", "", "")])
    os.makedirs(os.path.dirname(paths.TRANSLATIONS))
    with open(paths.TRANSLATIONS, "w", encoding="utf-8-sig", newline="") as f:
        f.write("name,voice,source,uk,status\nui_a,,Hi,Привіт,machine\nui_b,,Bye,Бувай,machine\n")
    status.write(str(content / "uk"), {"ui_a": "recorded"})
    public.export()
    assert status.read(str(content / "uk")) == {"ui_a": "recorded", "ui_b": "machine"}     # the pipeline never lowers a recorded line


def test_commands_rebuild_a_missing_table_from_content(tmp_path, monkeypatch):
    """Any command that needs the table rebuilds it when the work folder is fresh, instead of translating everything again."""
    content = point_paths(monkeypatch, tmp_path)
    (content / "uk").mkdir(parents=True)
    (content / "en").mkdir()
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Привіт", "", "")])
    texts.write_texts(str(content / "en" / "loca_en_texts.csv"), [("ui_a", "Hi", "", "")])
    assert not os.path.exists(paths.TRANSLATIONS)
    public.ensure_table()
    assert os.path.isfile(paths.TRANSLATIONS)
    public.ensure_table("/some/other/table.csv")                             # a custom path is never touched
    assert not os.path.exists("/some/other/table.csv")


def test_sync_uses_the_build_snapshot_to_find_edits_made_outside_the_tool(tmp_path, monkeypatch):
    content = point_paths(monkeypatch, tmp_path)
    (content / "uk").mkdir(parents=True)
    (content / "en").mkdir()
    texts.write_texts(str(content / "en" / "loca_en_texts.csv"), [("ui_a", "Hi", "", ""), ("ui_b", "Bye", "", "")])
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Привіт", "", ""), ("ui_b", "Бувай", "", "")])
    public.sync()                                                            # builds the table
    os.makedirs(paths.WORK, exist_ok=True)
    texts.write_texts(paths.BUILT_SNAPSHOT, [("ui_a", "Привіт", "", ""), ("ui_b", "Бувай", "", "")])
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Вітаю", "", ""), ("ui_b", "Бувай", "", "")])    # edited in the GitHub web editor
    public.sync()
    got = {r["name"]: r for r in csv.DictReader(open(paths.TRANSLATIONS, encoding="utf-8-sig", newline=""))}
    assert got["ui_a"]["uk"] == "Вітаю" and got["ui_a"]["status"] == "user" and got["ui_b"]["status"] == "edited"
