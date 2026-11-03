"""Encoding a voice into Ogg Opus (through PyAV/FFmpeg): in the content repository voices are stored as .ogg and go into the game decoded to PCM.

The OGG encoder built into soundfile crashes the process on Windows, so we encode through PyAV.
32 kbit/s mono is transparent to the ear for speech, and the files are several times smaller than FLAC."""
import io
import math

import numpy as np

OPUS_RATES = (8000, 12000, 16000, 24000, 48000)
DEFAULT_BITRATE = 32000


def encode_opus(data, rate, bitrate=DEFAULT_BITRATE):
    """int16 (mono) -> Ogg Opus bytes. Sample rates that Opus does not support are converted to 48 kHz; the length is padded with silence to a multiple of 20 ms
    (a difference from the original of up to 20 ms). Returns (bytes, rate)."""
    import av
    data = np.asarray(data)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype != np.int16:
        data = np.clip(data, -32768, 32767).astype(np.int16)
    if rate not in OPUS_RATES:
        from scipy.signal import resample_poly
        g = math.gcd(rate, 48000)
        data = np.clip(resample_poly(data.astype(np.float32), 48000 // g, rate // g), -32768, 32767).astype(np.int16)
        rate = 48000
    # the end of the Opus stream must fall on a frame boundary (20 ms): otherwise libsndfile considers some files damaged
    pad = (-len(data)) % (rate // 50)
    if pad:
        data = np.concatenate([data, np.zeros(pad, dtype=np.int16)])
    buf = io.BytesIO()
    out = av.open(buf, "w", format="ogg")
    st = out.add_stream("libopus", rate=rate)
    st.layout = "mono"
    st.bit_rate = bitrate
    fmt = st.codec_context.format.name
    arr = data.astype(np.float32) / 32768 if "flt" in fmt else data
    frame = av.AudioFrame.from_ndarray(arr.reshape(1, -1), format=fmt, layout="mono")
    frame.sample_rate = rate
    for pkt in st.encode(frame):
        out.mux(pkt)
    for pkt in st.encode(None):
        out.mux(pkt)
    out.close()
    return buf.getvalue(), rate


def write_opus(path, data, rate, bitrate=DEFAULT_BITRATE):
    blob, rate = encode_opus(data, rate, bitrate)
    with open(path, "wb") as f:
        f.write(blob)
    return rate
