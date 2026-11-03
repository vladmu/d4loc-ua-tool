"""Effects for the voice-over: a heroic echo, an ominous one ("global evil"), cathedral/holiness, a ghost.

All effects are pure DSP (numpy/scipy/librosa), with no third-party plugins. Input and output: float32 mono.
"""
import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

try:
    import librosa
except ImportError:
    librosa = None


def _rms(a):
    return float(np.sqrt(np.mean(a ** 2))) + 1e-9


def _match_level(wet, dry):
    return wet * (_rms(dry) / _rms(wet))


def _limit(a, ceil=0.9):
    peak = float(np.max(np.abs(a))) + 1e-9
    return a * (ceil / peak) if peak > ceil else a


def reverb_ir(sr, rt60=1.8, damping_hz=5000, pre_delay=0.02, seed=1):
    rng = np.random.default_rng(seed)
    n = int(sr * (rt60 + pre_delay))
    t = np.arange(n) / sr
    ir = rng.standard_normal(n) * np.exp(-6.9 * np.maximum(t - pre_delay, 0) / rt60)
    ir[t < pre_delay] = 0
    ir = sosfilt(butter(2, damping_hz, "low", fs=sr, output="sos"), ir)
    ir[0] = 0
    return (ir / (np.sqrt(np.sum(ir ** 2)) + 1e-9)).astype(np.float32)


def reverb(a, sr, rt60=1.8, wet=0.25, damping_hz=5000, pre_delay=0.02):
    w = fftconvolve(a, reverb_ir(sr, rt60, damping_hz, pre_delay))[: len(a) + int(sr * rt60)]
    w = _match_level(w[: len(a) + int(sr * rt60 * 0.6)], a)
    out = np.zeros(len(w), dtype=np.float32)
    out[: len(a)] += a * (1 - wet)
    out += w.astype(np.float32) * wet
    return out


def echo(a, sr, delays=(0.14, 0.28), gains=(0.35, 0.2)):
    n = len(a) + int(sr * max(delays)) + 1
    out = np.zeros(n, dtype=np.float32)
    out[: len(a)] += a
    for d, g in zip(delays, gains):
        k = int(sr * d)
        out[k: k + len(a)] += a * g
    return out


def low_shelf(a, sr, gain_db=5.0, fc=220):
    g = 10 ** (gain_db / 20) - 1
    lp = sosfilt(butter(2, fc, "low", fs=sr, output="sos"), a)
    return a + g * lp


def high_boost(a, sr, gain_db=3.0, fc=3500):
    g = 10 ** (gain_db / 20) - 1
    hp = sosfilt(butter(2, fc, "high", fs=sr, output="sos"), a)
    return a + g * hp


def heroic_echo(a, sr):
    """Heroic echo: a clear slapback + a large hall, with slightly brighter highs."""
    x = high_boost(a, sr, 2.0)
    x = echo(x, sr, (0.16, 0.32), (0.30, 0.16))
    return _limit(reverb(x, sr, rt60=2.2, wet=0.28, damping_hz=6000))


def global_evil(a, sr):
    """The threatening voice of "global evil": lower, doubled an octave below, a deepened bass and a long murky tail."""
    low = librosa.effects.pitch_shift(a, sr=sr, n_steps=-12)          # doubling an octave below
    main = librosa.effects.pitch_shift(a, sr=sr, n_steps=-2.0)        # the main voice a little lower
    n = min(len(main), len(low))
    mix = main[:n] * 0.85 + low[:n] * 0.45
    mix = np.tanh(mix * 1.6) / np.tanh(1.6)                            # soft saturation
    mix = low_shelf(mix, sr, 7.0, 200)
    mix = high_boost(mix, sr, -3.0, 4500)
    mix = reverb(mix, sr, rt60=3.0, wet=0.30, damping_hz=3500, pre_delay=0.04)
    return _limit(_match_level(mix, a))


def cathedral(a, sr):
    """Sacred, majestic: a long cathedral and a light chorus."""
    up = librosa.effects.pitch_shift(a, sr=sr, n_steps=0.15)
    dn = librosa.effects.pitch_shift(a, sr=sr, n_steps=-0.15)
    k = int(sr * 0.022)
    n = len(a)
    ch = a * 0.7
    ch[k:] += up[: n - k] * 0.3
    ch += dn * 0.0
    ch = high_boost(ch, sr, 2.5, 3000)
    return _limit(reverb(ch, sr, rt60=4.0, wet=0.38, damping_hz=7000, pre_delay=0.03))


def ghost(a, sr):
    """Ghostly: tremolo, a cold tone, an echo that stretches out."""
    t = np.arange(len(a)) / sr
    trem = 1 - 0.25 * (0.5 + 0.5 * np.sin(2 * np.pi * 5.5 * t))
    x = a * trem
    x = sosfilt(butter(2, [250, 4800], "band", fs=sr, output="sos"), x)
    x = echo(x, sr, (0.22, 0.44, 0.66), (0.35, 0.22, 0.12))
    return _limit(reverb(x, sr, rt60=2.8, wet=0.35, damping_hz=3000))


def eq_from_profiles(ltas_orig, ltas_dry, bands, max_db=10.0, smooth=1):
    """Correction curve (dB) by third-octave bands: the original minus our synthesis, smoothed and limited."""
    d = np.clip(np.asarray(ltas_orig) - np.asarray(ltas_dry), -max_db, max_db)
    if smooth:
        k = np.array([0.25, 0.5, 0.25])
        pad = np.pad(d, 1, mode="edge")
        d = np.convolve(pad, k, mode="valid")
    return d


def eq_apply(a, sr, gains_db, bands, taps=1025):
    """A linear-phase FIR equalizer following the curve gains_db at the points bands (Hz)."""
    from scipy.signal import firwin2
    f = [0.0] + [float(b) for b in bands] + [sr / 2]
    g = [gains_db[0]] + list(gains_db) + [gains_db[-1]]
    h = firwin2(taps, f, 10 ** (np.asarray(g) / 20), fs=sr)
    y = fftconvolve(a, h)[taps // 2: taps // 2 + len(a)]
    return y.astype(np.float32)


ANGEL = dict(rt60=2.4, wet=0.33, damping_hz=4500)


def angel(a, sr):
    """The heavenly voice of an angel: the reverb is tuned by measurement to the original (tail -32 dB, decay ~-23..-27 dB/s)."""
    return _limit(reverb(a, sr, **ANGEL))


# Parameters of a light room reverb by role: chosen so that the depth of the dips between words matches the original
ROOM = {"overlord": (0.8, 0.10), "thalya": (0.3, 0.10), "brother": (1.2, 0.10), "queen": (0.8, 0.10), "tanos": (0.8, 0.05)}


def room(a, sr, rt60, wet, damping_hz=5000, fade=0.06):
    """A light room reverb; the length stays as the input's (the tail is cut off with a short fade)."""
    y = reverb(a, sr, rt60=rt60, wet=wet, damping_hz=damping_hz)[: len(a)].copy()
    k = int(sr * fade)
    y[-k:] *= np.linspace(1, 0, k)
    return y.astype(np.float32)
