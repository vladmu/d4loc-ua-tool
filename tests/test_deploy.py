"""The developer can install the content folder into the game from the command line, and remove it again: the same code as the installer window."""
import os
import sys

import pytest

from d4loc import game, install
from tools.game import deploy


def run(monkeypatch, command, *args):
    monkeypatch.setattr(sys, "argv", [f"python dev/run.py {command}", *args])
    return deploy.main()


def test_install_and_uninstall_from_the_command_line(game_dir, content_pack, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    b = game.bundles_dir(game_dir)
    before = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b) if f.endswith(".csv") and not f.startswith("loca_uk")}
    assert run(monkeypatch, "install", "--content", str(content_pack), "--game", game_dir, "--no-voice", "--force") == 0
    assert install.is_installed(game_dir)
    assert os.path.isfile(os.path.join(b, "D4Loc_loca_en_texts.csv.bak"))                       # the same backups as in the installer window
    assert run(monkeypatch, "uninstall", "--game", game_dir) == 0
    assert not install.is_installed(game_dir)
    after = {f: open(os.path.join(b, f), "rb").read() for f in os.listdir(b) if f.endswith(".csv") and not f.startswith("loca_uk")}
    assert after == before                                                                    # the originals are back byte for byte


def test_install_without_content_stops_with_a_clear_message(game_dir, tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "install", "--content", str(tmp_path / "empty"), "--game", game_dir)
    assert "нема перекладу" in str(e.value)
