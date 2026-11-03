"""The developer pipeline: paths, the command dispatcher, proofreading, exchange with the content repository."""
import json
import os

import pytest

from tools import __main__ as cli
from tools import paths


def test_paths_are_inside_repo():
    assert os.path.isdir(paths.CONFIG)
    for p in (paths.GLOSSARY, paths.STRESS_OVERRIDES, paths.STRESS_HINTS, paths.VOICE_CAST):
        assert os.path.isfile(p), p
    assert os.path.isdir(paths.MANUAL_FIXES)


def test_every_command_module_exists():
    root = paths.ROOT
    for name, mod, what in cli.COMMANDS:
        assert what
        assert os.path.isfile(os.path.join(root, "dev", *mod.split(".")) + ".py"), (name, mod)


def test_unknown_command_is_rejected(capsys):
    assert cli.main(["нема-такої"]) == 2
    assert cli.main(["--help"]) == 0
    assert "voice" in capsys.readouterr().out


def test_review_roundtrip(tmp_path, monkeypatch):
    from tools.text import review
    tr = tmp_path / "t.csv"
    tr.write_text("name,voice,source,uk,status\ndlg_a1,,Hello,Привіт,machine\ndlg_a2,,Bye,Бувай,machine\n", encoding="utf-8-sig")
    fixes = tmp_path / "fixes"
    fixes.mkdir()
    monkeypatch.setattr(paths, "TRANSLATIONS", str(tr))
    monkeypatch.setattr(paths, "MANUAL_FIXES", str(fixes))
    review.apply("a", str(_write(tmp_path / "f.txt", "2\tДо побачення\n")))
    rec = json.loads((fixes / "text_review_a.jsonl").read_text(encoding="utf-8"))
    assert rec == {"name": "dlg_a2", "set": "До побачення"}


def _write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def test_public_and_sync_roundtrip(tmp_path, monkeypatch):
    """build writes the game file into content; public publishes the statuses; sync carries edits from content back into the translation table."""
    from d4loc import status, texts
    from tools.text import public
    content = tmp_path / "content"
    (content / "uk").mkdir(parents=True)
    (content / "en").mkdir()
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Привіт", "", ""), ("ui_b", "Бувай", "", "")])
    texts.write_texts(str(content / "en" / "loca_en_texts.csv"), [("ui_a", "Hi", "", ""), ("ui_b", "Bye", "", "")])
    work = tmp_path / "work"
    work.mkdir()
    table = work / "tr.csv"
    table.write_text(chr(10).join(["name,voice,source,uk,status", "ui_a,,Hi,Привіт,machine", "ui_b,,Bye,Бувай,machine", ""]), encoding="utf-8-sig")
    snapshot = work / "snap.csv"
    texts.write_texts(str(snapshot), [("ui_a", "Привіт", "", ""), ("ui_b", "Бувай", "", "")])      # what build wrote
    for name, value in (("TRANSLATIONS", table), ("BUILT_SNAPSHOT", snapshot), ("WORK", work), ("CONTENT_TEXTS", content / "uk" / "loca_uk_texts.csv"),
                        ("CONTENT_UK", content / "uk"), ("EN_TEXTS", content / "en" / "loca_en_texts.csv")):
        monkeypatch.setattr(paths, name, str(value))
    public.export()
    assert status.read(str(content / "uk")) == {"ui_a": "machine", "ui_b": "machine"}              # the status is published, the text is already there
    texts.write_texts(str(content / "uk" / "loca_uk_texts.csv"), [("ui_a", "Вітаю", "", ""), ("ui_b", "Бувай", "", "")])      # an edit in a PR
    public.sync()
    out = table.read_text(encoding="utf-8-sig")
    assert ",Вітаю,user" in out and "Бувай,machine" in out                                         # the line changed by a person became user, the rest stayed


def test_work_folder_is_outside_the_repo_and_clean_only_removes_a_marked_one(tmp_path, monkeypatch, capsys):
    from tools import clean
    assert not os.path.abspath(paths.WORK).startswith(os.path.abspath(paths.ROOT)) or os.environ.get("D4_WORK")     # not inside the project by default
    work = tmp_path / "work"
    work.mkdir()
    (work / "translations_uk.csv").write_text("x", encoding="utf-8")
    monkeypatch.setattr(paths, "WORK", str(work))
    assert clean.main() == 1 and work.exists()                                  # no marker: a folder somebody else made is never removed
    paths.ensure_work()
    assert clean.main() == 0 and not work.exists()                              # the pipeline's own folder is removed
    assert clean.main() == 0                                                    # nothing to do the second time


def test_validate_command_detects_problems(tmp_path, capsys, monkeypatch):
    from tools.text import validate as vcmd
    f = tmp_path / "texts.csv"
    f.write_bytes("name,wording,voice,tags\r\ndlg_x,Привіт *зітхає {a,,\r\nui_x,Ок <sprite name=x> ы,,\r\n".encode("utf-8-sig"))
    monkeypatch.setattr("sys.argv", ["validate", str(f)])
    assert vcmd.main() == 1
    out = capsys.readouterr().out
    assert "зірочок" in out and "дужки" in out and "російські" in out and "теги" not in out
