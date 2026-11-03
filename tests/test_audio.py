import struct

import numpy as np
import pytest

from d4loc import audio


def test_fsb5_header_pcm16():
    pcm = np.arange(480, dtype="int16").tobytes()
    blob, frames = audio.build_fsb5_pcm16(pcm, 1, 48000)
    assert blob[:4] == b"FSB5" and frames == 480
    assert blob.endswith(pcm)
    version, nsamples = struct.unpack_from("<II", blob, 4)
    assert version == 1 and nsamples == 1


def test_fsb5_rejects_unsupported_rate():
    with pytest.raises(ValueError):
        audio.build_fsb5_pcm16(b"\0\0" * 10, 1, 12345)


def test_parse_audiodef():
    txt = "abc123\n  alias: dlg_one\n  volume: 1\ndef456\n  alias: dlg_two\n"
    d = audio.parse_audiodef(txt)
    assert d["abc123"] == ("abc123", "dlg_one") and d["def456"][1] == "dlg_two"


def test_lang_path():
    assert audio.lang_path("assets/audio/en/x/y.wav", "en", "uk") == "assets/audio/uk/x/y.wav"
    assert audio.lang_path("assets/audio/en.dlc_gloom/dev/z.wav", "en", "uk") == "assets/audio/uk.dlc_gloom/dev/z.wav"


def test_limit_and_rms():
    sr = 24000
    t = np.arange(sr) / sr
    loud = (2.0 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    assert np.abs(audio.limit(loud, sr)).max() <= 0.91
    quiet = (0.1 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    assert 0.06 < audio.active_rms(quiet, sr) < 0.08


def test_mix_original_keeps_length_and_ceiling():
    sr = 24000
    t = np.arange(sr * 2) / sr
    voice = np.where(t < 1.0, 0.3 * np.sin(2 * np.pi * 200 * t), 0).astype("float32")
    orig = (0.3 * np.sin(2 * np.pi * 110 * t)).astype("float32")
    out = audio.mix_original(voice, orig, sr, -14.0)
    assert len(out) == len(voice) and np.abs(out).max() <= 0.91
    assert np.abs(out[int(1.5 * sr):]).max() > 0.001  # in a pause of the voice the original "surfaces"
