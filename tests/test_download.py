"""A release of three files: manifest.json, loca_uk_texts.csv, voice.zip. Download with resume, SHA-256, only what is needed."""
import functools
import http.server
import io
import json
import os
import re
import shutil
import socketserver
import threading
import zipfile

import pytest

from d4loc import download, install


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """A file server with Range support (like GitHub's): needed to test resuming."""

    requests = []

    def log_message(self, *a):
        pass

    def send_head(self):
        RangeHandler.requests.append(self.path)
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start = int(re.match(r"bytes=(\d+)-", rng).group(1))
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
        self.send_header("Content-Length", str(size - start))
        self.end_headers()
        return f


@pytest.fixture
def release(tmp_path, monkeypatch, content_pack):
    """A local "release": manifest.json and loca_uk_texts.csv side by side, the voices in voice.zip; a server with Range."""
    from conftest import VOICE_NAMES, make_voice
    make_voice(content_pack, VOICE_NAMES[:6])
    out = tmp_path / "rel"
    download.build_release(content_pack, str(out))        # the release is made by the real producer: the pair of download_content
    RangeHandler.requests = []
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(RangeHandler, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("D4LOC_RELEASE_BASE", f"http://127.0.0.1:{srv.server_address[1]}/")
    yield out
    srv.shutdown()


def test_manifest_is_a_release_file_fetched_separately(release):
    r = download.fetch_release()
    assert r["manifest"]["version"] == "1.0.0" and r["version"] == "1.0.0"
    assert set(r["assets"]) == set(download.ASSETS)
    assert download.total_size(r, with_voice=False) < download.total_size(r, with_voice=True)
    assert download.asset_size(r, download.VOICE_ASSET) == os.path.getsize(release / "voice.zip")


def test_text_only_does_not_touch_voice(release, tmp_path):
    r = download.fetch_release()
    RangeHandler.requests.clear()
    dest = str(tmp_path / "text_only")
    download.download_content(r, dest, with_voice=False, log=lambda s: None)
    assert install.has_content(dest) and not install.has_voice(dest)
    assert not any("voice.zip" in p for p in RangeHandler.requests)            # voices are not downloaded if they were not chosen
    assert open(os.path.join(dest, "uk", "loca_uk_texts.csv"), "rb").read() == (release / "loca_uk_texts.csv").read_bytes()   # text as is


def test_voice_downloaded_on_demand_and_not_repeated(release, tmp_path):
    r = download.fetch_release()
    dest = str(tmp_path / "full")
    download.download_content(r, dest, with_voice=False, log=lambda s: None)
    assert not install.has_voice(dest)
    download.download_content(r, dest, with_voice=True, log=lambda s: None)    # voice-over was chosen later: only voice.zip is fetched
    assert len(install.voice_files(dest)) == 6 and install.verify_pack(dest)[0] == "ok"
    RangeHandler.requests.clear()
    download.download_content(r, dest, with_voice=True, log=lambda s: None)    # everything is already there: nothing is downloaded
    assert RangeHandler.requests == []
    assert json.load(open(os.path.join(dest, ".complete"), encoding="utf-8"))


def test_wrong_checksum_is_rejected_and_file_removed(release, tmp_path):
    r = download.fetch_release()
    r["assets"]["loca_uk_texts.csv"]["sha256"] = "0" * 64
    dest = str(tmp_path / "d2")
    with pytest.raises(RuntimeError, match="Контрольна сума"):
        download.download_content(r, dest, with_voice=False, log=lambda s: None)
    assert not install.has_content(dest) and not os.path.exists(os.path.join(dest, "uk", "loca_uk_texts.csv.part"))


def test_checksum_ok_when_given(release, tmp_path):
    r = download.fetch_release()
    for name in download.ASSETS:
        r["assets"][name]["sha256"] = download.sha256_file(str(release / name))
    dest = str(tmp_path / "d5")
    download.download_content(r, dest, with_voice=True, log=lambda s: None)
    assert install.verify_pack(dest)[0] == "ok"


def test_partial_voice_download_resumes(release, tmp_path):
    r = download.fetch_release()
    r["assets"]["voice.zip"]["sha256"] = download.sha256_file(str(release / "voice.zip"))
    dest = tmp_path / "d3"
    dest.mkdir()
    data = (release / "voice.zip").read_bytes()
    (dest / "voice.zip.part").write_bytes(data[: len(data) // 3])               # interrupted earlier
    msgs = []
    download.download_content(r, str(dest), with_voice=True, log=msgs.append)
    assert any("докачування" in x for x in msgs) and len(install.voice_files(str(dest))) == 6


def test_garbage_voice_archive_is_rejected(release, tmp_path):
    r = download.fetch_release()
    dest = tmp_path / "d4"
    dest.mkdir()
    (dest / "voice.zip.part").write_bytes(b"x" * download.asset_size(r, "voice.zip"))   # full size, but not an archive
    with pytest.raises(RuntimeError, match="пошкоджений"):
        download.download_content(r, str(dest), with_voice=True, log=lambda s: None)
    assert not (dest / "voice.zip.part").exists()


def test_zip_slip_is_blocked(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("ok.txt", "x")
        zf.writestr("../evil.txt", "x")
    with pytest.raises(RuntimeError, match="Небезпечний"):
        download.extract_zip(str(z), str(tmp_path / "out"))
    assert not (tmp_path / "evil.txt").exists()


def test_cleanup_only_touches_our_download(tmp_path):
    ours = tmp_path / "ours"
    ours.mkdir()
    (ours / ".complete").write_text("{}")
    (ours / "x").write_text("x")
    assert download.cleanup(str(ours)) is True and not ours.exists()
    fork = tmp_path / "fork"
    (fork / ".git").mkdir(parents=True)
    (fork / ".complete").write_text("{}")
    assert download.cleanup(str(fork)) is False and fork.exists()             # a git fork is left alone
    plain = tmp_path / "plain"
    plain.mkdir()
    assert download.cleanup(str(plain)) is False and plain.exists()           # also without the marker


def test_latest_release_comes_through_download_links_and_not_from_the_api(monkeypatch):
    """Only the plain download links of the latest release are used: no repository branches and no GitHub API (60 requests an hour from one
    address are not enough for players behind one router)."""
    monkeypatch.delenv("D4LOC_RELEASE_BASE", raising=False)
    manifest = json.dumps({"version": "0.3.0", "game": {"build": "b"}}).encode()
    sizes = {"manifest.json": 170, "loca_uk_texts.csv": 1715021, "voice.zip": 139247951}
    seen = []

    class Reply(io.BytesIO):
        def __init__(self, body=b"", length=0):
            super().__init__(body)
            self.headers = {"Content-Length": str(length)}

    def fake_open(url, headers=None, timeout=15, method="GET"):
        seen.append(url)
        assert "api.github.com" not in url and "raw.githubusercontent" not in url and "/main/" not in url
        assert url.startswith("https://github.com/vladmu/d4loc-ua-content/releases/latest/download/")
        name = url.rsplit("/", 1)[1]
        return Reply(manifest if method == "GET" else b"", sizes[name])
    monkeypatch.setattr(download, "_open", fake_open)
    r = download.fetch_release()
    assert r["version"] == "0.3.0" and r["manifest"]["game"]["build"] == "b"
    assert {n: a["size"] for n, a in r["assets"].items()} == sizes and download.total_size(r, with_voice=False) == 1715191
    assert all(a["url"] in seen for a in r["assets"].values())


def test_build_release_and_unpack_are_a_pair(tmp_path, content_pack):
    """What build_release writes, download_content's unpacking turns back into a working pack: one description of the format, tested both ways."""
    from conftest import VOICE_NAMES, make_voice
    make_voice(content_pack, VOICE_NAMES[:6])
    out = tmp_path / "rel"
    voices, count = download.build_release(content_pack, str(out))
    assert voices == 6 and count >= 6
    assert sorted(os.listdir(out)) == sorted(download.ASSETS)                                     # exactly the three files, nothing else
    assert (out / "manifest.json").read_bytes() == open(os.path.join(content_pack, "manifest.json"), "rb").read()      # as they are in the content folder
    assert (out / "loca_uk_texts.csv").read_bytes() == open(os.path.join(content_pack, "uk", "loca_uk_texts.csv"), "rb").read()
    names = zipfile.ZipFile(out / "voice.zip").namelist()
    assert "uk/audio_metadata.csv" in names and not any(n.endswith("loca_uk_texts.csv") for n in names)     # voices only: the text is its own file
    dest = tmp_path / "unpacked"
    dest.mkdir()
    shutil.copy2(out / "manifest.json", dest / "manifest.json")
    (dest / "uk").mkdir()
    shutil.copy2(out / "loca_uk_texts.csv", dest / "uk" / "loca_uk_texts.csv")
    download.extract_zip(str(out / "voice.zip"), str(dest))
    assert install.has_content(str(dest)) and install.verify_pack(str(dest))[0] == "ok" and len(install.voice_files(str(dest))) == 6


def test_build_release_refuses_a_folder_without_voices(tmp_path, content_pack):
    meta = os.path.join(content_pack, "uk", "audio_metadata.csv")
    with open(meta, "w", encoding="utf-8-sig", newline="") as f:
        f.write("bundle,name,wording,file_id,file_path,container_path,path_id,md5" + chr(10))
    os.makedirs(os.path.join(content_pack, "uk", "audio"), exist_ok=True)
    with pytest.raises(RuntimeError):
        download.build_release(content_pack, str(tmp_path / "rel"))
    assert not any(n.endswith(".new") for n in os.listdir(tmp_path / "rel"))                      # no half-made archive is left behind
