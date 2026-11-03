"""Measuring the acoustic "fingerprint" of a recording: a third-octave spectrum, crest factor, tail/echo."""
import numpy as np, soundfile as sf, librosa

BANDS = [100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000]


def load(path, sr=22050):
    y, s = sf.read(path)
    y = y.astype(np.float32)
    if y.ndim > 1:
        y = y.mean(1)
    if s != sr:
        y = librosa.resample(y, orig_sr=s, target_sr=sr)
    return y, sr


def ltas(y, sr):
    """The spectrum averaged over frames with speech, in third-octave bands (dB, normalized to the overall level)."""
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    e = S.sum(0)
    S = S[:, e > 0.05 * e.max()]
    P = S.mean(1)
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    out = []
    for c in BANDS:
        lo, hi = c / 2 ** (1 / 6), c * 2 ** (1 / 6)
        out.append(10 * np.log10(P[(f >= lo) & (f < hi)].sum() + 1e-12))
    out = np.array(out)
    return out - 10 * np.log10(np.sum(10 ** (out / 10)))


def crest(y):
    return 20 * np.log10(np.max(np.abs(y)) / (np.sqrt(np.mean(y ** 2)) + 1e-9) + 1e-9)


def env_db(y, sr, hop=0.01):
    h = int(sr * hop)
    n = len(y) // h
    r = np.sqrt((y[: n * h].reshape(n, h) ** 2).mean(1) + 1e-12)
    return 20 * np.log10(r + 1e-9), hop


def tail_stats(y, sr):
    """The tail after the last speech: the level after 0.2 s (dB relative to the maximum) and the decay rate (dB/s)."""
    e, hop = env_db(y, sr)
    ref = e.max()
    idx = np.where(e > ref - 25)[0]
    if len(idx) == 0:
        return np.nan, np.nan
    last = idx[-1]
    k = int(0.2 / hop)
    after = e[last: last + int(0.6 / hop)]
    if len(after) < 8:
        return np.nan, np.nan
    lvl = e[min(last + k, len(e) - 1)] - ref
    t = np.arange(len(after)) * hop
    slope = np.polyfit(t, np.maximum(after, ref - 80), 1)[0]
    return float(lvl), float(slope)


def echo_peak(y, sr, lo=0.08, hi=0.45):
    e, hop = env_db(y, sr, 0.01)
    x = 10 ** (e / 20)
    x = x - x.mean()
    ac = np.correlate(x, x, "full")[len(x) - 1:]
    ac = ac / (ac[0] + 1e-12)
    a, b = int(lo / hop), int(hi / hop)
    seg = ac[a:b]
    return float(seg.max()), float((np.argmax(seg) + a) * hop)


def profile(paths):
    L, C, T, EP = [], [], [], []
    for p in paths:
        y, sr = load(p)
        if len(y) < sr:
            continue
        L.append(ltas(y, sr)); C.append(crest(y)); T.append(tail_stats(y, sr)); EP.append(echo_peak(y, sr))
    T = np.array(T)
    return {"ltas": np.mean(L, 0), "crest": float(np.mean(C)), "tail_lvl": float(np.nanmedian(T[:, 0])),
            "tail_slope": float(np.nanmedian(T[:, 1])), "echo": float(np.mean([e[0] for e in EP])), "n": len(L)}


def summary(p):
    L = p["ltas"]
    low = 10 * np.log10(np.sum(10 ** (L[:5] / 10)))      # 100–250 Hz
    mid = 10 * np.log10(np.sum(10 ** (L[5:13] / 10)))    # 315 Hz – 1.25 kHz
    pres = 10 * np.log10(np.sum(10 ** (L[13:18] / 10)))  # 2–5 kHz
    air = 10 * np.log10(np.sum(10 ** (L[18:] / 10)))     # 6.3–10 kHz
    return f"низ {low:5.1f} | сер {mid:5.1f} | присутн {pres:5.1f} | верх {air:5.1f} дБ; крест-фактор {p['crest']:4.1f} дБ; хвіст@0,2с {p['tail_lvl']:5.1f} дБ, спад {p['tail_slope']:6.1f} дБ/с; луна {p['echo']:.2f}"


def dip_stats(y, sr):
    """The depth of the dips between syllables/words (dB) and the dynamic range in speech: a room effect "fills in" the dips."""
    from scipy.signal import find_peaks
    e, hop = env_db(y, sr, 0.01)
    k = np.ones(3) / 3
    e = np.convolve(e, k, mode="same")
    pk, _ = find_peaks(e, prominence=6, distance=6)
    depths = []
    for a, b in zip(pk[:-1], pk[1:]):
        gap = (b - a) * hop
        if 0.08 < gap < 0.5:
            depths.append(min(e[a], e[b]) - e[a:b + 1].min())
    act = e[e > e.max() - 40]
    rng = float(np.percentile(act, 95) - np.percentile(act, 10)) if len(act) > 10 else np.nan
    return (float(np.median(depths)) if depths else np.nan), rng
