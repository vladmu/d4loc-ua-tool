"""Text -> phonemes for HolosTTS with custom stress corrections and splitting into sentences."""
import os
import re

import numpy as np
from ipa_uk import ipa
from ukrainian_word_stress import Disambiguation, OnAmbiguity, Stressifier

from tools import paths
VOWELS = "аеєиіїоуюяАЕЄИІЇОУЮЯ"
WORD = re.compile(r"[А-Яа-яІіЇїЄєҐґ'’]+")
SENT = re.compile(r"(?<=[.!?])\s+")
_stress = None
_overrides = None


def stressifier():
    global _stress
    if _stress is None:
        _stress = Stressifier(disambiguation=Disambiguation.Stanza, on_ambiguity=OnAmbiguity.Skip)
    return _stress


def load_overrides(path=paths.STRESS_OVERRIDES):
    """word (without stress, lowercase) -> the word with ´ after the stressed vowel."""
    res = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.split("#", 1)[0].strip()
            if "=" not in line:
                continue
            _, rhs = (x.strip() for x in line.split("=", 1))
            caps = [i for i, c in enumerate(rhs) if c in VOWELS and c.isupper()]
            if len(caps) != 1:
                continue
            i = caps[0]
            low = rhs.lower()
            res[low] = low[:i + 1] + "´" + low[i + 1:]
    return res


def apply_overrides(stressed):
    global _overrides
    if _overrides is None:
        _overrides = load_overrides()

    def fix(m):
        w = m.group(0)
        base = w.replace("´", "").lower()
        if base in _overrides:
            new = _overrides[base]
            return new[0].upper() + new[1:] if w[0].isupper() else new
        return w

    return re.sub(r"[А-Яа-яІіЇїЄєҐґ'’]+´?[А-Яа-яІіЇїЄєҐґ'’]*", fix, stressed)


def soften_ellipsis(text):
    """"…" is kept only directly after a word: there the word's last vowel is stretched (drawl_before_ellipsis), without a pause.
    All other "…" (after punctuation, standalone) are removed."""
    ell = chr(0x2026)
    text = text.replace("...", ell)
    text = re.sub(r"(?<![А-Яа-яІіЇїЄєҐґ'’])" + ell + r"+", "", text)
    return re.sub(ell + r"{2,}", ell, text)


def sentences(text):
    text = soften_ellipsis(text)
    parts = [p.strip() for p in SENT.split(text) if p.strip()]
    return parts or [text]


def to_phonemes(sentence):
    """Phonemes for the model. We pass the stress to ipa-uk as a combining mark (U+0301): then it gets the standard
    IPA position "ˈ" at the start of the stressed syllable ("nɐˈreʃtʲi"). This gave correct stress in almost all voices;
    the "ˈ" mark between a consonant and a vowel ("rˈe") gave a stutter on "г" and a burred "р"."""
    stressed = apply_overrides(fix_vocative(stressifier()(prepare(sentence)))).replace(chr(0xB4), chr(0x301))
    stressed = re.sub(r"[А-Яа-яІіЇїЄєҐґ'’´́]+", lambda m: one_stress(m.group(0)), stressed)
    return drawl_before_ellipsis(ipa(stressed))


NUMBERS = {"0": "нуль", "1": "один", "2": "два", "3": "три", "4": "чотири", "5": "п'ять", "6": "шість", "7": "сім",
           "8": "вісім", "9": "дев'ять", "10": "десять", "11": "одинадцять", "12": "дванадцять", "13": "тринадцять",
           "15": "п'ятнадцять", "20": "двадцять", "25": "двадцять п'ять", "30": "тридцять", "40": "сорок",
           "50": "п'ятдесят", "60": "шістдесят", "100": "сто"}


def prepare(text):
    """Text to phonemes: removes marks that are not in the model's vocabulary (* « » ( ) –), digits -> words, hyphenated words
    are split (otherwise the stress lands only on the second part), extra "?!" are squeezed into a single mark."""
    t = re.sub(r"(?<![а-яіїєґ'’-])([а-яіїєґ]*?)([аеєиіїоуюя])(?:-\2)+(?![а-яіїєґ-])", lambda m: m.group(1) + m.group(2) + chr(0x2026), text, flags=re.I)
    t = re.sub(r"[*«»“”\"()]", "", t)
    t = re.sub(r"\s*[–—]\s*", ", ", t)
    t = re.sub(r"(?<=[А-Яа-яІіЇїЄєҐґ])-(?=[А-Яа-яІіЇїЄєҐґ])", " ", t)
    t = re.sub(r"(?<!\d)\d+(?!\d)", lambda m: NUMBERS.get(m.group(0), m.group(0)), t)
    t = re.sub(r"[!?]{2,}", lambda m: m.group(0)[0], t)
    t = re.sub(r"([,.:;])\1+", r"\1", t)
    t = re.sub(r",\s*([.!?…])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


GOOD_NOUN = {"Добра": "Добра´", "Добро": "Добро´", "Добру": "Добру´", "Добром": "Добром´"}


def fix_good(text):
    """"Сил Добра", "Добро переможе!", "служити Добру": Добро with a capital letter = a noun (добра́, добро́, добру́), not
    the adjective (до́бра); the exception is "Добру Істоту", "Добру Талію", where it is an adjective."""
    def fix(m):
        w = m.group(1).replace(chr(0xB4), "")
        return GOOD_NOUN.get(w, m.group(0))
    return re.sub(r"(До´?бр(?:а|о|у|ом)´?)(?![а-яіїєґ´])(?!\s+(?:[Іі]ст|Талі))", fix, text)


HINTS = {}  # the English original of the current line (gen_holos sets HINTS["source"]); the rules are in stress_hints.txt
_hint_rules = None


def load_hints(path=paths.STRESS_HINTS):
    rules = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.split("#", 1)[0].strip()
            if "~" not in line:
                continue
            form, rx = (x.strip() for x in line.split("~", 1))
            if form.count("´") != 1 or not rx:
                continue
            rules.append((form.replace("´", ""), form, re.compile(rx, re.I)))
    return rules


def apply_hints(text):
    """Homonyms that the English original disambiguates (замок/замок, брати/брати, потяг/потяг ...): if exactly one
    rule fires for a word, its form is forced. The rules are in stress_hints.txt (a word with ´ ~ a regular expression)."""
    global _hint_rules
    src = HINTS.get("source")
    if not src:
        return text
    if _hint_rules is None:
        _hint_rules = load_hints()
    hits = {}
    for base, form, rx in _hint_rules:
        if rx.search(src):
            hits.setdefault(base, set()).add(form)
    for base, forms in hits.items():
        if len(forms) != 1:
            continue
        form = next(iter(forms))

        pat = "´?".join(re.escape(c) for c in base)
        text = re.sub(r"(?<![А-Яа-яІіЇїЄєҐґ'’´])(?i:" + pat + r")(?![А-Яа-яІіЇїЄєҐґ'’´])",
                      lambda m, f=form: f[0].upper() + f[1:] if m.group(0)[0].isupper() else f, text)
    return text


_dict = None


def default_stress(text):
    """Words with several stress variants that Stanza could not choose (they stand without "´"): we take the variant with the earliest
    stress (as in the list I reviewed), not the first in the dictionary, where the order is arbitrary."""
    global _dict
    from ukrainian_word_stress.stressify_ import _load_dictionary, _trie_value, _parse_dictionary_value
    if _dict is None:
        _dict = _load_dictionary()

    def fix(m):
        w = m.group(0)
        if "´" in w or len(re.findall("[аеєиіїоуюяАЕЄИІЇОУЮЯ]", w)) < 2:
            return w
        v = _trie_value(_dict, w)
        if v is None:
            return w
        accs = sorted({tuple(a) for _, a in _parse_dictionary_value(v[0]) if len(a) == 1})
        if len(accs) < 2:
            if accs:
                return w[:accs[0][0]] + "´" + w[accs[0][0]:]
            return w
        a = accs[0][0]
        return w[:a] + "´" + w[a:]
    return re.sub(r"(?<![А-Яа-яІіЇїЄєҐґ'’´])[А-Яа-яІіЇїЄєҐґ'’]+(?![А-Яа-яІіЇїЄєҐґ'’´])", fix, text)


def fix_vocative(text):
    text = apply_hints(fix_good(default_stress(text)))
    """«Брати мої», «Брати, ходімо!»: Stanza тут часто бачить дієслово; звертання/іменник = брати́ (братів), дієслово = бра́ти."""
    text = re.sub(r"\b(Бра)(?:´)?(ти)(?=\s+(?:мої|наші|ваші|та|і)\b|[,!])", lambda m: m.group(1) + m.group(2) + "´", text)
    text = re.sub(r"(?<=[а-яіїєґ´,]\s)(Бра)(?:´)?(ти)(?![а-яіїєґ´])", lambda m: m.group(1) + m.group(2) + "´", text)
    text = re.sub(r"(?<=,\s)(бра)(?:´)?(ти)(?![а-яіїєґ])", lambda m: m.group(1) + m.group(2) + "´", text)
    text = re.sub(r"(?<![а-яіїєґ´])(Бра)(?:´)?(ти)(?=[,!.?]|\s+(?:та|і|й)\s)", lambda m: m.group(1) + m.group(2) + "´", text)
    return re.sub(r"\b(бра)(?:´)?(ти)(?=\s+(?:мої|наші|ваші)\b)", lambda m: m.group(1) + m.group(2) + "´", text)


def one_stress(w):
    """A word with two stresses (a dictionary ambiguity) -> keep the first one."""
    n = w.count(chr(0xB4)) + w.count(chr(0x301))
    if n < 2:
        return w
    seen = False
    out = []
    for c in w:
        if c in (chr(0xB4), chr(0x301)):
            if seen:
                continue
            seen = True
        out.append(c)
    return "".join(out)


def drawl_before_ellipsis(ph):
    """"так…", "у…", "хвилин…": the last vowel of the word before three dots is drawn out (vowel + "ːː") without a pause;
    the "…" mark is removed, and at the end of a sentence a full stop is kept."""
    ell = chr(0x2026)
    ends = ph.rstrip().endswith(ell)
    out = []
    for w in ph.split(" "):
        m = re.match(r"^(.*?)" + ell + r"+([!?,.:;]*)$", w)
        if m and m.group(1):
            core, tail = m.group(1), m.group(2)
            idx = [i for i, c in enumerate(core) if c in VOWEL_PH]
            if idx and chr(0x2D0) not in core:
                i = idx[-1] + 1
                core = core[:i] + chr(0x2D0) * 2 + core[i:]
            w = core + tail
        out.append(w)
    res = " ".join(out)
    return res + "." if ends else res


VOWEL_PH = set('aɐɔeɪiʊuɛɑyɨoə')
DRAWL_FRAMES = 0  # the frame-based method is disabled (it gave a quiet vowel); the drawl is made with length marks in the phonemes
FIRST_CAP = 999  # the limit is disabled: it clipped genuine first sounds ("мої" -> "ї"); the model reads them long but correctly
PITCH_GAIN = 1.0  # multiplier of the voice pitch range (1 = as predicted by the model)
STRESS_DUR, STRESS_F0, STRESS_EN = 1.0, 1.0, 0.0  # the artificial boost is disabled: with ˈ in the syllable it is not needed


STRESS_F0BOOST = 1.0  # multiplier of the pitch of the word's stressed vowel (on top of the leveling)
STRESS_ENERGY = 0.0  # +/- to the energy of the word's stressed/unstressed vowels
STRESS_PEAK = 0.95  # in a word the pitch of the stressed vowel is not lower than the other vowels (otherwise "мої брати" sounds like "брати" stressed on "бра")


def _peak_on_stress(syms, f2t, f0, energy=None):
    """A word with the "ˈ" mark: unstressed vowels higher than the stressed one are lowered to STRESS_PEAK of its pitch."""
    stress = chr(0x2C8)
    words, cur = [], []
    for k, sy in enumerate(syms):
        if sy.strip() == "" or sy in "$,.!?:;":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(k)
    if cur:
        words.append(cur)
    for w in words:
        sk = [k for k in w if syms[k] == stress]
        vow = [k for k in w if any(c in VOWEL_PH for c in syms[k])]
        if not sk or len(vow) < 2:
            continue
        sv = next((k for k in vow if k > sk[0]), None)
        if sv is None:
            continue
        fs = f0[np.where(f2t == sv)[0]]
        fs = fs[fs > 50]
        if not len(fs):
            continue
        ref = float(fs.mean())
        if STRESS_F0BOOST != 1.0:
            sfr = np.where(f2t == sv)[0]
            f0[sfr[f0[sfr] > 50]] *= STRESS_F0BOOST
            ref *= STRESS_F0BOOST
        if energy is not None and STRESS_ENERGY:
            energy[np.where(f2t == sv)[0]] += STRESS_ENERGY
        for k in vow:
            if k == sv:
                continue
            if energy is not None and STRESS_ENERGY:
                energy[np.where(f2t == k)[0]] -= STRESS_ENERGY
            fr = np.where(f2t == k)[0]
            v = f0[fr] > 50
            if v.sum() and float(f0[fr][v].mean()) > ref * STRESS_PEAK:
                f0[fr[v]] *= ref * STRESS_PEAK / float(f0[fr][v].mean())


def encode_stressed(model, phonemes, voice, speed=1.0, dur=None, f0_gain=None, en_gain=None, pitch_gain=None):
    """Model stages with stress boosting: lengthening the stressed vowel and raising F0 and energy on it.

    It was measured that the model conveys stress mainly through the length of the vowel, and the "´" mark by itself lengthens it
    only in some voices; substituting the mark ("ˈ") gave a stutter on "г" and a burred "р".
    Returns (_Encoded, token symbols, indices of the stressed vowels)."""
    from holos_onnx.inference import _Encoded

    pitch_gain = PITCH_GAIN if pitch_gain is None else pitch_gain
    dur = STRESS_DUR if dur is None else dur
    f0_gain = STRESS_F0 if f0_gain is None else f0_gain
    en_gain = STRESS_EN if en_gain is None else en_gain
    m = model
    token_values = m.tokenizer.encode_with_boundaries(phonemes)
    tokens = np.ascontiguousarray(token_values[None, :])
    voice_array = m._voice_array(voice)
    acoustic, prosodic, durations = m.encoder_session.run(
        ["acoustic_tokens", "prosodic_tokens", "durations"],
        {"tokens": tokens, "voice": voice_array, "speed": np.asarray([speed], dtype=np.float32)})
    durations = np.asarray(durations, dtype=np.int64)
    vocab = list(m.tokenizer.vocab)
    syms = [vocab[t] for t in token_values]
    mark = chr(0xB4)
    stressed = [k - 1 for k, sy in enumerate(syms) if sy == mark and k > 0]
    for k in stressed:
        d = int(durations[0, k])
        durations[0, k] = max(d + 1, int(round(d * dur)))
    # "у…", "ой…", "ну…": three dots after a one-syllable word mean a drawn-out word, not silence.
    DRAWL = []
    ell = chr(0x2026)
    for k, sy in enumerate(syms):
        if sy == ell:
            j = k - 1
            while j >= 0 and syms[j] in (chr(0x2C8), mark_ := chr(0xB4)):
                j -= 1
            # the word before "…": tokens back to the space/start
            w = j
            while w >= 0 and syms[w].strip() != "" and syms[w] not in "$,.!?":
                w -= 1
            vows = [x for x in range(w + 1, j + 1) if any(c in VOWEL_PH for c in syms[x])]
            if DRAWL_FRAMES and len(vows) == 1:
                kv = vows[0]
                durations[0, kv] = max(int(durations[0, kv]), DRAWL_FRAMES)
                durations[0, k] = 1
                if k + 1 < len(syms) and syms[k + 1].strip() == "":
                    durations[0, k + 1] = 1
                DRAWL.append(kv)
    # The model stretches the first sound of a sentence by 200-400 ms (a lead-in before the phrase), which is heard as an extra pause.
    syms_all = syms
    for k in range(len(syms_all)):
        if syms_all[k].strip() not in ("", "$") and k > 0:
            if durations[0, k] > FIRST_CAP:
                durations[0, k] = FIRST_CAP
            break
    m._validate_frame_count(int(durations.sum()))
    frame_to_token = m._build_frame_to_token(durations)
    f0, energy = m.prosody_session.run(
        ["f0", "energy"],
        {"prosodic_tokens": np.asarray(prosodic, dtype=np.float32), "frame_to_token": frame_to_token,
         "voice": voice_array})
    f0 = np.array(f0, dtype=np.float32)
    energy = np.array(energy, dtype=np.float32)
    f2t = np.asarray(frame_to_token).reshape(-1)
    for k in stressed:
        fr = np.where(f2t == k)[0]
        if len(fr):
            f0.reshape(-1)[fr] *= np.where(f0.reshape(-1)[fr] > 50, f0_gain, 1.0)
            energy.reshape(-1)[fr] += en_gain
    if STRESS_PEAK:
        _peak_on_stress(syms, f2t, f0.reshape(-1), energy.reshape(-1))
    if DRAWL:
        f2d = np.asarray(frame_to_token).reshape(-1)
        fl = f0.reshape(-1)
        en = energy.reshape(-1)
        sp = fl > 50
        ref_en = float(np.percentile(en[sp], 60)) if sp.any() else float(en.mean())
        for kv in DRAWL:
            fr = np.where(f2d == kv)[0]
            nxt = np.where(f2d == kv + 1)[0]
            if len(fr):
                en[fr] = np.maximum(en[fr], ref_en)
                base = fl[fr[0]] if fl[fr[0]] > 50 else (np.median(fl[sp]) if sp.any() else 120.0)
                fl[fr] = base
            if len(nxt):
                en[nxt] = np.maximum(en[nxt], ref_en * 0.5)
    if pitch_gain != 1.0:  # pitch range around the sentence's mean log F0 (over voiced frames)
        flat = f0.reshape(-1)
        voiced = flat > 50
        if voiced.sum() > 5:
            lm = np.log(flat[voiced]).mean()
            flat[voiced] = np.exp(lm + pitch_gain * (np.log(flat[voiced]) - lm))
    enc = _Encoded(voice=voice_array, acoustic_tokens=np.asarray(acoustic, dtype=np.float32),
                   frame_to_token=frame_to_token, f0=f0, energy=energy,
                   durations=np.ascontiguousarray(durations[0]))
    return enc, syms, stressed


def generate_stressed(model, phonemes, voice, speed=1.0, **kw):
    enc, _, _ = encode_stressed(model, phonemes, voice, speed, **kw)
    return np.asarray(model._decode_exact(enc)).reshape(-1)


FINAL_TAIL = True  # append ", а" for sentences that end in a word stressed on the last syllable
STOP_MARK = chr(0x2C8)


def final_stress(ph):
    """Does the sentence end in a multi-syllable word stressed on the last syllable (and is not a question)."""
    core = ph.rstrip()
    if core.endswith("?"):
        return False
    core = core.rstrip("!?.,:;" + chr(0x2026))
    word = core.split(" ")[-1]
    if STOP_MARK not in word or chr(0x2D0) in word:
        return False
    vow = [i for i, c in enumerate(word) if c in VOWEL_PH]
    if len(vow) < 2:
        return False
    after = [i for i in vow if i > word.index(STOP_MARK)]
    return bool(after) and after[0] == vow[-1]


def generate_final_stress(model, ph, voice, speed=1.0, pitch_gain=None):
    """The model mutes the last syllable of a phrase (the stressed "брати́!" sounds like "бра́ти(т)"). We append a continuation word and cut off
    the sound 20 ms before the comma starts: then the last syllable sounds as if speech continues after it."""
    core = ph.rstrip().rstrip("!.,:;" + chr(0x2026))
    enc, syms, _ = encode_stressed(model, core + ", " + chr(0x250), voice, speed, pitch_gain=pitch_gain)
    audio = np.asarray(model._decode_exact(enc)).reshape(-1)
    f2t = np.asarray(enc.frame_to_token).reshape(-1)
    kc = max(k for k, sy in enumerate(syms) if sy == ",")
    fr = np.where(f2t == kc)[0]
    if not len(fr):
        return audio
    sr = model.sample_rate
    end = max(1000, min(len(audio), int(fr[0] * model.samples_per_frame - 0.02 * sr)))
    out = audio[:end].copy()
    k = min(len(out), int(0.05 * sr))
    out[-k:] *= np.linspace(1, 0, k)
    return out


def synthesize(model, text, voice, speed=1.0, pause=0.22, pitch_gain=None):
    """Sentence by sentence, with a short pause between them. Returns float32 mono at model.sample_rate."""
    sr = model.sample_rate
    chunks = []
    for s in sentences(text):
        ph = to_phonemes(s)
        if FINAL_TAIL and final_stress(ph):
            a = generate_final_stress(model, ph, voice, speed, pitch_gain=pitch_gain)
        else:
            a = generate_stressed(model, ph, voice, speed, pitch_gain=pitch_gain)
        chunks.append(a)
        chunks.append(np.zeros(int(pause * sr), dtype=np.float32))
    return np.concatenate(chunks[:-1]).astype(np.float32)
