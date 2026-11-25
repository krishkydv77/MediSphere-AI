"""
Voice layer for the chatbot (Sarvam AI STT + TTS).

Flow (see /api/chat-voice in main.py):
    mic audio -> speech_to_text() -> canonicalize() -> SAME text chat logic -> html_to_speech()
              -> split_for_tts() -> tts_stream()  (chunks are synthesised in parallel, first chunk is short)

Low-latency choices
  * one shared keep-alive httpx client (no TLS handshake per request)
  * spoken reply is a SHORT version of the screen reply (VOICE_MAX_CHARS) - fewer tokens/characters to synthesise
  * first TTS chunk is small (FIRST_CHUNK_CHARS) so the user hears audio early; rest is synthesised in parallel
  * booking / cancel / confirm turns never touch an LLM (see canonicalize)

.env settings (all optional except SARVAM_API_KEY):
    SARVAM_API_KEY, SARVAM_STT_MODEL=saarika:v2.5, SARVAM_STT_LANG=unknown, SARVAM_STT_MODE (only for saaras models)
    SARVAM_TTS_MODEL=bulbul:v2, SARVAM_TTS_SPEAKER=anushka, SARVAM_TTS_LANG=hi-IN
    SARVAM_TTS_PACE, SARVAM_TTS_SAMPLE_RATE, VOICE_MAX_CHARS=450, SAVE_VOICE_AUDIO=false, VOICE_DATA_DIR=voice_data
"""
import asyncio
import difflib
import html
import os
import re
import time
import unicodedata

import httpx

from src.logger import get_logger

logger = get_logger(__name__)

SARVAM_BASE = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai")
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")
STT_LANG = os.getenv("SARVAM_STT_LANG", "unknown")          # "unknown" = auto detect (Hindi / English / Hinglish)
STT_MODE = os.getenv("SARVAM_STT_MODE", "")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "anushka")
TTS_DEFAULT_LANG = os.getenv("SARVAM_TTS_LANG", "hi-IN")
TTS_PACE = os.getenv("SARVAM_TTS_PACE", "")
TTS_SAMPLE_RATE = os.getenv("SARVAM_TTS_SAMPLE_RATE", "")
VOICE_MAX_CHARS = int(os.getenv("VOICE_MAX_CHARS", "450"))
FIRST_CHUNK_CHARS = int(os.getenv("VOICE_FIRST_CHUNK_CHARS", "120"))
TTS_CHUNK_CHARS = int(os.getenv("VOICE_TTS_CHUNK_CHARS", "220"))     # Sarvam v2 limit is 500, stay far below
TTS_PARALLEL = int(os.getenv("VOICE_TTS_PARALLEL", "3"))
SAVE_AUDIO = os.getenv("SAVE_VOICE_AUDIO", "false").lower() == "true"
AUDIO_DIR = os.getenv("VOICE_DATA_DIR", "voice_data")
TTS_LANGS = {"hi-IN", "en-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "pa-IN", "od-IN"}

_client = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=4.0),
            limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=60),
        )
    return _client


def _key() -> str:
    key = os.getenv("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY is not set in .env")
    return key


# ----------------------------------------------------------------- Sarvam
async def speech_to_text(audio_bytes: bytes, filename: str = "voice.wav", content_type: str = "audio/wav") -> dict:
    data = {"model": STT_MODEL, "language_code": STT_LANG}
    if STT_MODE:
        data["mode"] = STT_MODE
    r = await _http().post(
        f"{SARVAM_BASE}/speech-to-text",
        headers={"api-subscription-key": _key()},
        files={"file": (filename, audio_bytes, content_type)},
        data=data,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Sarvam STT {r.status_code}: {r.text[:200]}")
    j = r.json()
    return {"transcript": (j.get("transcript") or "").strip(), "language": j.get("language_code")}


def tts_language(stt_language) -> str:
    if stt_language and str(stt_language).lower().startswith("en"):
        return "en-IN"
    return TTS_DEFAULT_LANG if TTS_DEFAULT_LANG in TTS_LANGS else "hi-IN"


async def text_to_speech(text: str, lang: str) -> str:
    """Returns base64 WAV."""
    payload = {
        "text": text,
        "target_language_code": lang,
        "speaker": TTS_SPEAKER,
        "model": TTS_MODEL,
        "enable_preprocessing": True,
    }
    if TTS_PACE:
        payload["pace"] = float(TTS_PACE)
    if TTS_SAMPLE_RATE:
        payload["speech_sample_rate"] = int(TTS_SAMPLE_RATE)
    last = None
    for attempt in range(2):                       # one quick retry for transient errors
        try:
            r = await _http().post(
                f"{SARVAM_BASE}/text-to-speech",
                headers={"api-subscription-key": _key(), "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                await asyncio.sleep(0.2)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Sarvam TTS {r.status_code}: {r.text[:200]}")
            audios = r.json().get("audios") or []
            if not audios:
                raise RuntimeError("Sarvam TTS returned no audio")
            return audios[0]
        except httpx.TransportError as e:
            last = e
            await asyncio.sleep(0.2)
    raise RuntimeError(f"Sarvam TTS network error: {last}")


async def tts_stream(text: str, lang: str):
    """Async generator -> (index, base64_wav) strictly in order; chunks are synthesised in parallel."""
    chunks = split_for_tts(text)
    sem = asyncio.Semaphore(TTS_PARALLEL)

    async def one(c):
        async with sem:
            return await text_to_speech(c, lang)

    tasks = [asyncio.create_task(one(c)) for c in chunks]
    try:
        for i, t in enumerate(tasks):
            yield i, await t
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


# --------------------------------------------------- reply -> spoken text
_EMOJI_RX = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]")
_SLOT_LINE_RX = re.compile(r"free slots?\s*:|timing\s*:|🕒|🟢", re.I)


def html_to_speech(reply_html: str, max_chars: int = None) -> str:
    """Short, listenable version of the on-screen reply (no timings/slot lists, no emoji, no numbering)."""
    max_chars = max_chars or VOICE_MAX_CHARS
    items, dropped_slots = [], False
    for part in re.split(r"<br\s*/?>", reply_html or "", flags=re.I):
        txt = html.unescape(re.sub(r"<[^>]+>", "", part)).strip()
        if not txt:
            continue
        if _SLOT_LINE_RX.search(txt):
            dropped_slots = True
            continue
        txt = _EMOJI_RX.sub("", txt)
        txt = re.sub(r"^\s*\d+[.)]\s*", "", txt)
        txt = re.sub(r"\bdr\.", "Doctor", txt, flags=re.I)
        txt = re.sub(r"\s+", " ", txt).strip()
        if not txt or (txt.endswith(":") and len(txt) < 40):      # drop bare labels like "Immediate Precautions:"
            continue
        items.append(txt if txt[-1] in ".!?" else txt.rstrip(".:;,") + ".")
    if dropped_slots and items:
        items.insert(max(len(items) - 1, 0), "Doctors ke free slots screen par dikh rahe hain.")

    text = " ".join(items)
    if len(text) <= max_chars:
        return text
    tail = items[-1]
    kept, used = [], len(tail) + 1
    for s in items[:-1]:
        if used + len(s) + 1 > max_chars:
            break
        kept.append(s)
        used += len(s) + 1
    text = " ".join(kept + [tail])
    return text[:max_chars].rsplit(" ", 1)[0] if len(text) > max_chars else text


def _hard_split(s: str, n: int):
    out = []
    while len(s) > n:
        cut = max(s.rfind(", ", 0, n), s.rfind(" ", 0, n))
        cut = cut if cut > n // 3 else n
        out.append(s[:cut].strip())
        s = s[cut:].lstrip(", ")
    if s.strip():
        out.append(s.strip())
    return out


def split_for_tts(text: str, first_max: int = None, max_len: int = None):
    first_max = first_max or FIRST_CHUNK_CHARS
    max_len = max_len or TTS_CHUNK_CHARS
    chunks, cur = [], ""
    for sent in re.split(r"(?<=[.!?।])\s+", (text or "").strip()):
        if not sent:
            continue
        limit = first_max if not chunks else max_len
        if cur and len(cur) + 1 + len(sent) > limit:
            chunks.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
        while len(cur) > (first_max if not chunks else max_len):
            parts = _hard_split(cur, first_max if not chunks else max_len)
            chunks.append(parts[0])
            cur = " ".join(parts[1:])
    if cur:
        chunks.append(cur)
    return chunks


def save_voice_audio(user_id, audio_bytes: bytes, filename: str):
    if not SAVE_AUDIO:
        return None
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        ext = re.sub(r"[^a-z0-9.]", "", os.path.splitext(filename or "")[1].lower())[:6] or ".wav"
        path = os.path.join(AUDIO_DIR, f"{user_id}_{int(time.time() * 1000)}{ext}")
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path
    except Exception as e:
        logger.error(f"save_voice_audio failed: {e}")
        return None


# ---------------------------------------- transcript -> text the flow understands
# Sarvam usually answers in Devanagari for Hindi ("हाँ", "दस बजे", "डॉक्टर रोहन गुप्ता"), while the
# booking flow in main.py matches Roman words ("yes", "10:00 AM", "Dr. Rohan Gupta").
# canonicalize() converts ONLY the booking-relevant turns (yes/no/cancel/time/doctor) and returns every
# other transcript unchanged (symptoms, questions ...).
def _n(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def normalize_text(s: str) -> str:
    s = _n(s or "").lower().translate(_DEV_DIGITS)
    s = re.sub(r"[।॥]", " ", s)
    s = re.sub(r"\b([ap])\s?\.\s?m\b\.?", r"\1m", s)
    s = re.sub(r"(?<=\d)\.(?=\d)", ":", s)
    s = re.sub(r"[^\w\s:\u0900-\u097F]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_YES_TOK = {_n(x) for x in ("yes", "yeah", "yep", "haan", "han", "haa", "ha", "haanji", "ok", "okay", "confirm", "kardo",
                            "bilkul", "sure", "done", "theek", "thik", "sahi", "हाँ", "हां", "हा", "जी", "ठीक", "सही",
                            "बिल्कुल", "ओके", "कन्फर्म", "हाँजी", "हांजी", "कर्दो")}
_YES_PHRASE = [_n(x) for x in ("kar do", "kar dijiye", "book kar", "कर दो", "कर दीजिए", "बुक कर")]
_NO_TOK = {_n(x) for x in ("no", "nahi", "nahin", "nhi", "na", "nope", "mat", "नहीं", "नही", "ना", "मत")}
_CANCEL_RX = re.compile(r"(?<![a-z])(cancel\w*|radd|raddh|hata\s*do|hatao)(?![a-z])|कैंसिल|केंसिल|कैन्सल|कैंसल|कैन्सिल|रद्द|हटा\s*दो", re.I)


def _has_yes(norm: str, toks) -> bool:
    return any(t in _YES_TOK for t in toks) or any(p in norm for p in _YES_PHRASE)


def _has_no(toks) -> bool:
    return any(t in _NO_TOK for t in toks)


_NUM_WORDS = {}
for _w, _v in [("ek one एक", 1), ("do two दो", 2), ("teen three तीन", 3), ("char chaar four चार", 4),
               ("panch paanch five पांच पाँच", 5), ("chhe che chhah chah six छह छः छे छ", 6), ("saat seven सात", 7),
               ("aath eight आठ", 8), ("nau nine नौ", 9), ("das ten दस", 10), ("gyarah eleven ग्यारह", 11),
               ("barah twelve बारह", 12)]:
    for _x in _w.split():
        _NUM_WORDS[_n(_x)] = _v
_TIME_MARK = {_n(x) for x in ("baje", "bje", "bajke", "am", "pm", "oclock", "बजे", "बजकर")}
_SADHE = {_n(x) for x in ("sadhe", "saadhe", "sade", "साढ़े", "साढे", "साड़े")}
_PM_WORDS = {_n(x) for x in ("pm", "shaam", "sham", "dopahar", "raat", "शाम", "दोपहर", "रात")}
_AM_WORDS = {_n(x) for x in ("am", "subah", "savere", "सुबह", "सवेरे")}


def _parse_slot(slot: str):
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*(AM|PM)", slot, re.I)
    return (int(m.group(1)), int(m.group(2)), m.group(3).lower()) if m else None


def extract_slot(norm: str, free_slots) -> str:
    """'दस बजे', '10 am', 'saadhe gyarah', '2 baje', 'pehla slot' -> '10:00 AM' (must be one of free_slots)."""
    toks = norm.split()
    if not toks or not free_slots:
        return ""
    if any(t in {_n(x) for x in ("pehla", "pehle", "first", "पहला", "पहले")} for t in toks) and any(
            t in {"slot", _n("स्लॉट")} for t in toks):
        return free_slots[0]
    if any(t in {_n(x) for x in ("last", "aakhri", "akhri", "आखिरी")} for t in toks) and any(
            t in {"slot", _n("स्लॉट")} for t in toks):
        return free_slots[-1]

    spoken = "pm" if any(t in _PM_WORDS for t in toks) else ("am" if any(t in _AM_WORDS for t in toks) else None)
    cands = []                                   # (hour, minute)
    for m in re.finditer(r"(?<!\d)(\d{1,2})(?::(\d{2}))?(?!\d)", norm):
        cands.append((int(m.group(1)), int(m.group(2) or 0)))
    for i, t in enumerate(toks):                 # number words only next to a time marker, so "book kar do" != 2 o'clock
        if t in _NUM_WORDS:
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            prev = toks[i - 1] if i else ""
            if nxt in _TIME_MARK or prev in _SADHE or len(toks) == 1:
                cands.append((_NUM_WORDS[t], 30 if prev in _SADHE else 0))
    for h, mi in cands:
        for slot in free_slots:
            p = _parse_slot(slot)
            if p and h % 12 == p[0] % 12 and mi == p[1] and (h > 12 or not spoken or spoken == p[2]):
                return slot
    return ""


_CONS = {}
for _group, _lat in [("कखघ", "k"), ("ग", "g"), ("चछ", "c"), ("जझ", "j"), ("टठत थ".replace(" ", ""), "t"),
                     ("डढदध", "d"), ("णनङञ", "n"), ("पफ", "p"), ("बभ", "b"), ("म", "m"), ("य", "y"), ("र", "r"),
                     ("ल", "l"), ("व", "v"), ("शषस", "s"), ("ह", "h")]:
    for _ch in _group:
        _CONS[_ch] = _lat
_CONS.update({"ड़": "d", "ढ़": "d", "क़": "k", "ख़": "k", "ग़": "g", "ज़": "j", "फ़": "p"})


def _skeleton(word: str) -> str:
    """Language-neutral consonant skeleton, so 'रोहन' and 'Rohan' compare equal."""
    out = []
    for ch in _n(word).lower():
        if ch in _CONS:
            out.append(_CONS[ch])
        elif ch == "ं":
            out.append("n")
        elif "a" <= ch <= "z":
            out.append(ch)
    s = re.sub(r"[aeiouyh]", "", "".join(out)).translate(str.maketrans("ckqzfwx", "kkkjpvs"))
    return re.sub(r"(.)\1+", r"\1", s)


def _tok_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 3 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


_ORD = {_n(x): i for i, group in enumerate([("pehla", "pehle", "first", "1st", "पहला", "पहले"),
                                             ("doosra", "dusra", "doosre", "second", "2nd", "दूसरा", "दूसरे"),
                                             ("teesra", "third", "3rd", "तीसरा", "तीसरे")]) for x in group}
_DOC_WORDS = {_n(x) for x in ("doctor", "dr", "wale", "wala", "number", "डॉक्टर", "डॉ", "वाले", "वाला", "नंबर")}


_STOP = {_n(x) for x in ("karna", "karne", "karni", "krna", "krne", "karo", "kro", "kar", "kare", "karen", "kariye", "kijiye",
                         "hona", "hone", "hota", "hoti", "dena", "dene", "lena", "jana", "aana", "book", "booking",
                         "appointment", "please", "chahiye", "chahie", "chahta", "chahti", "mujhe", "mera", "meri", "mere")}


def match_doctor(norm: str, suggested, doctors, is_symptom: bool):
    """suggested: [{'id','name',..}] from session; doctors: [(id, name)] all doctors. Returns doctor name or ''."""
    toks = norm.split()
    if not toks or len(toks) > 9:
        return ""
    has_title = any(t in _DOC_WORDS for t in toks)
    if is_symptom and not has_title:
        return ""
    if suggested and has_title:
        for t in toks:
            if t in _ORD and _ORD[t] < len(suggested):
                return suggested[_ORD[t]]["name"]
    sk = [s for s in (_skeleton(t) for t in toks if t not in _STOP) if s]
    suggested_ids = {d["id"] for d in (suggested or [])}
    scored = []
    for did, name in doctors:
        name_sk = [s for s in (_skeleton(p) for p in name.replace(".", " ").split() if p.lower() not in ("dr", "dr.")) if s]
        score = sum(1 for ns in name_sk if any(_tok_match(ns, u) for u in sk))
        if score:
            scored.append((score, did in suggested_ids, len(name_sk), did, name))
    if not scored:
        return ""
    scored.sort(reverse=True)
    best = scored[0]
    tied = [x for x in scored if x[:2] == best[:2]]
    if len(tied) > 1:
        return ""                                   # ambiguous ("Mehta" x3) -> let the normal flow ask
    # one matching name-part is enough only when the person clearly means a doctor
    if best[0] >= 2 or (best[0] == 1 and best[1] and (has_title or len(toks) <= 2)):
        return best[4]
    return ""


def canonicalize(transcript: str, pending, suggested, doctors, free_slots) -> str:
    """Convert a spoken transcript into the exact text the existing booking flow expects."""
    norm = normalize_text(transcript)
    if not norm:
        return transcript
    toks = norm.split()
    if _CANCEL_RX.search(_n(transcript).lower()):
        return "cancel"
    stage = pending.get("stage") if pending else None
    if stage == "ASK_TIME":
        return extract_slot(norm, free_slots) or transcript
    if stage == "ASK_CONFIRM":
        yes, no = _has_yes(norm, toks), _has_no(toks)
        return "yes" if yes and not no else ("no" if no and not yes else transcript)
    if pending:
        return transcript
    try:
        from medical_mcp.suggestion_engine import analyse_text
        is_symptom = analyse_text(transcript)["intent"] == "SYMPTOM"
    except Exception:
        is_symptom = False
    doc = match_doctor(norm, suggested or [], doctors or [], is_symptom)
    if doc:
        return doc
    if suggested and len(toks) <= 4 and _has_yes(norm, toks) and not _has_no(toks):
        return "haan"
    return transcript
