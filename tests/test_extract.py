"""One extraction for the translator tool and the developer command: project.ensure_language, and `extract` with its content folder and repository."""
import os
import sys

import pytest

from d4loc import project, repo
from tools.game import extract


def test_ensure_language_unpacks_once_and_follows_the_game(game_dir, tmp_path):
    proj = str(tmp_path / "proj")
    log = []
    assert project.ensure_language(game_dir, "xx", proj, log=log.append) == "missing"          # not in the game
    assert project.ensure_language(game_dir, "en", proj, log=log.append) == "unpacked"
    assert os.path.isfile(os.path.join(proj, "en", "loca_en_texts.csv"))
    assert project.ensure_language(game_dir, "en", proj, log=log.append) == "current"          # nothing changed: left alone
    assert project.ensure_language(game_dir, "en", proj, log=log.append, force=True) == "updated"
    en = [p for p in (os.path.join(r, f) for r, _d, fs in os.walk(game_dir) for f in fs) if p.endswith("loca_en_texts.csv")][0]
    with open(en, "ab") as f:
        f.write("extra,Extra line,,".encode("utf-8") + bytes([13, 10]))                         # the game was updated
    project.save_pending_texts(proj, "en", {"extra": "unsaved"})
    assert project.ensure_language(game_dir, "en", proj, log=log.append) == "pending"          # outdated, but there are unsaved changes: untouched
    project.discard_pending(proj, "en")
    assert project.ensure_language(game_dir, "en", proj, log=log.append) == "updated"
    assert "extra" in open(os.path.join(proj, "en", "loca_en_texts.csv"), encoding="utf-8-sig").read()


def test_extract_takes_the_release_of_the_given_repository_and_unpacks_english(game_dir, content_pack, tmp_path, monkeypatch, capsys):
    """--repo says whose release to take (a fork may have its own releases); nothing is cloned, the same release is laid out as in the translator tool."""
    import io
    from conftest import VOICE_NAMES, make_voice
    from d4loc import download
    monkeypatch.delenv("D4LOC_RELEASE_BASE", raising=False)
    make_voice(content_pack, VOICE_NAMES[:3])
    released = tmp_path / "released"
    download.build_release(str(content_pack), str(released))
    seen = []

    class Reply(io.BytesIO):
        def __init__(self, body):
            super().__init__(body)
            self.headers = {"Content-Length": str(len(body))}

    def fake_open(url, headers=None, timeout=15, method="GET"):
        seen.append(url)
        assert url.startswith("https://github.com/someone/myfork/releases/latest/download/"), url        # the fork's release, not the official one
        return Reply((released / url.rsplit("/", 1)[1]).read_bytes())
    monkeypatch.setattr(download, "_open", fake_open)
    content = tmp_path / "content"
    monkeypatch.setattr(sys, "argv", ["extract", "--content", str(content), "--repo", "https://github.com/someone/myfork.git", "--game", game_dir])
    extract.main()
    assert repo.inspect_folder(str(content))[0] == "content"                                    # the release was laid out
    assert os.path.isfile(content / "en" / "loca_en_texts.csv") and not (content / ".git").exists()      # the English unpacked next to it, no git involved
    capsys.readouterr()
    before = len(seen)
    monkeypatch.setattr(sys, "argv", ["extract", "--content", str(content), "--game", game_dir])
    extract.main()                                                                              # a second run only checks: the folder is a content folder already
    assert len(seen) == before and "current" in capsys.readouterr().out


def test_extract_refuses_a_foreign_folder(game_dir, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    (other / "notes.txt").write_text("not a content folder", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["extract", "--content", str(other), "--game", game_dir])
    with pytest.raises(SystemExit):
        extract.main()
    assert not (other / "en").exists()
