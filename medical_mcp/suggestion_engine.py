"""
Suggestion engine used by the MCP tools `health_suggestion` and `web_search`.

* Suggestion text comes from the project's own RAG folder (rag/ -> FAISS index),
  NOT from the LLM's memory.  An optional tiny LLM call only *rewrites* the
  retrieved text into short Hinglish (set SUGGESTION_REWRITE=false to disable).
* Web search (SerpAPI) is used only for current / new medical or project
  related information.

Everything here is plain python, so it can be tested without the MCP server.
"""
import asyncio
import os
import re
import sys
import time
import unicodedata

import httpx

from src.logger import get_logger

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ----------------------------------------------------------------- settings
CANDIDATES = int(os.getenv("SUGGESTION_CANDIDATES", "6"))        # chunks fetched from FAISS
MAX_CONTEXT_CHARS = int(os.getenv("SUGGESTION_CONTEXT_CHARS", "900"))  # tokens sent to LLM (kept small)
REWRITE_DEFAULT = os.getenv("SUGGESTION_REWRITE", "true").lower() == "true"
LLM_TIMEOUT = float(os.getenv("SUGGESTION_LLM_TIMEOUT", "3.0"))
SUGGEST_MODEL = os.getenv("SUGGEST_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b"
CACHE_TTL = int(os.getenv("SUGGESTION_CACHE_TTL", "600"))
SERP_TIMEOUT = float(os.getenv("SERPAPI_TIMEOUT", "4.0"))


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


# ------------------------------------------------- specialty / symptom rules
# (specialty, english hint for TF-IDF retrieval, roman regex pieces, devanagari substrings)
# Order matters: first match wins.
_RULES = [
    ("Pediatrician", "child fever",
     [r"baby", r"child", r"children", r"kids?", r"bachch\w*", r"bacch\w*", r"newborn", r"infant", r"toddler", r"vaccination"],
     ["बच्च", "बेबी", "टीका"]),
    ("Gynecologist", "pregnancy-related concern menstrual",
     [r"pregnan\w*", r"periods", r"period\s*(pain|late|miss\w*|dard|nahi|aa\w*)", r"missed\s*period", r"menstrual\w*", r"delivery", r"pcod", r"pcos", r"garbh\w*", r"ma+hwari"],
     ["पीरियड", "माहवारी", "गर्भ", "प्रेग्नेंसी", "प्रेगनेंसी"]),
    ("Cardiologist", "chest pain palpitations high blood pressure",
     [r"chest\s*pain", r"heart\w*", r"seene", r"seena", r"dil", r"bp", r"blood\s*pressure", r"palpitation\w*", r"dhadkan"],
     ["सीने", "सीना", "दिल", "धड़कन", "हार्ट", "बीपी", "ब्लड प्रेशर"]),
    ("Neurologist", "headache dizziness fainting",
     [r"headache", r"migraine", r"si+r\s*dard", r"sa+r\s*dard", r"sirdard", r"sardard", r"dizz\w*", r"chakkar", r"seizure",
      r"fits", r"nerve", r"numb\w*", r"jhanjhanahat", r"memory", r"brain", r"current\s*lag\w*"],
     ["सिर दर्द", "सिरदर्द", "सरदर्द", "सर दर्द", "माइग्रेन", "चक्कर", "दौरा", "सुन्न", "झनझनाहट"]),
    ("Pulmonologist", "cough sore throat breathing",
     [r"cough\w*", r"khansi", r"khasi", r"asthma", r"breath\w*", r"saans", r"lungs?", r"wheez\w*", r"tb"],
     ["खांसी", "खाँसी", "खासी", "सांस", "साँस", "दमा", "अस्थमा"]),
    ("Gastroenterologist", "abdominal pain diarrhea vomiting",
     [r"pet", r"stomach", r"acidity", r"gas", r"digest\w*", r"constipation", r"kabz", r"vomit\w*", r"ulti",
      r"diarrh\w*", r"dast", r"loose\s*motion", r"liver", r"abdom\w*"],
     ["पेट", "एसिडिटी", "गैस", "उल्टी", "दस्त", "कब्ज", "लूज मोशन", "लिवर"]),
    ("Orthopedic", "back pain joint injury",
     [r"haddi", r"bones?", r"joints?", r"ghutn\w*", r"knee", r"back\s*pain", r"kamar", r"fracture", r"injur\w*",
      r"chot", r"shoulder", r"kandha", r"arthritis", r"sprain", r"moch"],
     ["हड्डी", "जोड़", "घुटन", "कमर", "फ्रैक्चर", "मोच", "कंधे", "चोट"]),
    ("Dermatologist", "skin rash itching",
     [r"skin", r"rash", r"pimples?", r"acne", r"itch\w*", r"khujli", r"allergy", r"fungal", r"da+ne", r"burn"],
     ["त्वचा", "स्किन", "खुजली", "दाने", "एलर्जी", "फंगल"]),
    ("ENT Specialist", "cough sore throat",
     [r"ears?", r"nose", r"throat", r"kaan", r"naak", r"gala", r"gale", r"tonsil\w*", r"sinus"],
     ["कान", "नाक", "गला", "गले", "टॉन्सिल", "साइनस"]),
    ("Ophthalmologist", "eye vision",
     [r"eyes?", r"vision", r"aankh\w*", r"nazar", r"blur\w*", r"glasses"],
     ["आंख", "आँख", "नजर", "नज़र", "धुंधला"]),
    ("Psychiatrist", "anxiety panic symptoms",
     [r"depress\w*", r"anxiety", r"stress", r"mental", r"panic", r"sleep\s*problem", r"neend", r"ghabrahat", r"tension"],
     ["डिप्रेशन", "तनाव", "घबराहट", "चिंता", "नींद"]),
    ("Urologist", "urinary burning frequency",
     [r"urine", r"urin\w*", r"peshab", r"kidney\s*stone", r"pathri", r"bladder", r"prostate"],
     ["पेशाब", "पथरी", "किडनी"]),
    ("Endocrinologist", "diabetes high or low blood sugar",
     [r"diabet\w*", r"thyroid", r"hormone", r"sugar", r"madhumeh"],
     ["शुगर", "डायबिटीज", "थायराइड", "मधुमेह"]),
]

_GENERIC_ROMAN = [
    r"dard", r"pain", r"fever", r"bukha+r", r"tabiyat", r"tabiat", r"taklif", r"takleef", r"dikkat", r"kamzori",
    r"weakness", r"thakan", r"fatigue", r"sardi", r"zukam", r"jukam", r"cold", r"body\s*ache", r"sick", r"ill",
    r"unwell", r"infection", r"sujan", r"swelling", r"bleeding", r"khoon", r"corona", r"nausea", r"jalan", r"cramps?",
]
_GENERIC_DEVA = ["दर्द", "बुखार", "तबियत", "तबीयत", "तकलीफ", "कमजोरी", "थकान", "बीमार", "सर्दी", "जुकाम", "सूजन", "खून", "जलन"]

_HINT_WORDS = [  # specific english words for retrieval (TF-IDF vocabulary is English)
    (r"headache|migraine|si+r\s*dard|sa+r\s*dard|sirdard|sardard|सिर दर्द|सिरदर्द|सरदर्द|सर दर्द|माइग्रेन", "headache"),
    (r"dizz\w*|chakkar|चक्कर", "dizziness fainting"),
    (r"bukha+r|fever|बुखार", "fever"),
    (r"cough\w*|khansi|khasi|खांसी|खाँसी|खासी|throat|gala|गला", "cough sore throat"),
    (r"ulti|vomit\w*|dast|diarrh\w*|loose\s*motion|उल्टी|दस्त", "diarrhea vomiting"),
    (r"pet|stomach|abdom\w*|पेट", "abdominal pain"),
    (r"back\s*pain|kamar|कमर", "back pain"),
    (r"skin|rash|khujli|itch\w*|त्वचा|खुजली|दाने", "skin rash itching"),
    (r"peshab|urine|urin\w*|पेशाब", "urinary burning frequency"),
    (r"dhadkan|palpitation\w*|धड़कन", "palpitations"),
    (r"chest\s*pain|seene|सीने", "chest pain"),
    (r"bp|blood\s*pressure|बीपी|ब्लड प्रेशर", "high blood pressure"),
    (r"sugar|diabet\w*|शुगर|डायबिटीज", "diabetes blood sugar"),
    (r"anxiety|panic|ghabrahat|घबराहट", "anxiety panic"),
    (r"kamzori|weakness|thakan|fatigue|कमजोरी|थकान", "fatigue rest hydration"),
]


def _rx(parts):
    return re.compile(r"(?<![a-z])(?:" + "|".join(parts) + r")(?![a-z])", re.I)


_COMPILED = [(spec, hint, _rx(roman), [_norm(d) for d in deva]) for spec, hint, roman, deva in _RULES]
_GENERIC_RX = _rx(_GENERIC_ROMAN)
_GENERIC_DEVA_N = [_norm(d) for d in _GENERIC_DEVA]
_HINT_RX = [(re.compile(p, re.I), h) for p, h in _HINT_WORDS]

_APPOINTMENT_RX = re.compile(
    r"(?<![a-z])(appointment|apointment|appoinment|booking|book|slot|opd|dikhana|dikhani|dikhwana|milna)(?![a-z])"
    r"|अपॉइंटमेंट|अपॉइन्टमेंट|बुकिंग|बुक|दिखाना|मिलना", re.I)
_QUESTION_RX = re.compile(
    r"\?|^(kya|kaise|kaisa|kitna|kitne|kyun|kyu|kab|kaun|what|how|why|when|can|should|is|are|do|does)(?![a-z])"
    r"|(?<![a-z])(kya|kaise|kitne|kyun|kyu)(?![a-z])|क्या|कैसे|कितने|क्यों", re.I)
_EMERGENCY_RX = re.compile(
    r"heart\s*attack|stroke|lakwa|unconscious|behosh|bebosh|can'?t\s*breathe|cannot\s*breathe|saans\s*(nahi|nhi)"
    r"|(bahut|heavy|severe)\s*(khoon|bleeding)|seizure|daura|zeher|overdose"
    r"|chest\s*pain.*(breath|saans|sweat|paseena|left\s*arm)|(breath|saans|sweat|paseena).*chest\s*pain"
    r"|बेहोश|सांस नहीं|साँस नहीं|लकवा|दौरा|ज़हर|जहर|हार्ट अटैक", re.I)
_SELFHARM_RX = re.compile(r"suicide|khudkushi|marna\s*chah\w*|jaan\s*dena|end\s*my\s*life|आत्महत्या|मरना चाह", re.I)
_WEB_TRIGGER_RX = re.compile(
    r"latest|news|outbreak|advisory|guideline\w*|update\w*|recent\w*|variant|new\s+(strain|cases?|treatment|research|guideline\w*)"
    r"|current(ly)?\s+(situation|trend|cases?|outbreak)|taaza|khabar|ताज़ा|ताजा|खबर|समाचार|नया\s+वेरिएंट", re.I)
_SCOPE_RX = re.compile(
    r"(?<![a-z])(medical|medicine|health\w*|disease|doctor|hospital|clinic|covid|corona\w*|virus|vaccin\w*|treatment|symptom\w*|"
    r"outbreak|dengue|malaria|flu|epidemic|icmr|aiims|ayushman|sanjeevani|mcp|rag|fastapi|sarvam|groq|faiss|llm|chatbot)(?![a-z])"
    r"|स्वास्थ्य|बीमारी|दवा|अस्पताल|डॉक्टर|टीका", re.I)


def analyse_text(text: str, specialty_hint: str = "") -> dict:
    """Cheap rule based analysis (no LLM): intent, specialty, retrieval hint."""
    t = _norm(text)
    specialty, spec_hint = "", ""
    for spec, hint, rx, deva in _COMPILED:
        if rx.search(t) or any(d in t for d in deva):
            specialty, spec_hint = spec, hint
            break
    generic = bool(_GENERIC_RX.search(t)) or any(d in t for d in _GENERIC_DEVA_N)
    hints = [h for rx, h in _HINT_RX if rx.search(t)] or ([spec_hint] if spec_hint else [])
    is_symptom = bool(specialty) or generic
    wants_appt = bool(_APPOINTMENT_RX.search(t))
    if specialty_hint:
        specialty = specialty_hint
        is_symptom = True
    intent = "SYMPTOM" if is_symptom else ("APPOINTMENT" if wants_appt else "OTHER")
    return {
        "intent": intent,
        "specialty": specialty or ("General OPD" if intent != "OTHER" else ""),
        "hint": " ".join(hints),
        "emergency": bool(_EMERGENCY_RX.search(t)),
        "self_harm": bool(_SELFHARM_RX.search(t)),
        "is_question": bool(_QUESTION_RX.search(t.strip())),
        "wants_web": bool(_WEB_TRIGGER_RX.search(t)) and bool(_SCOPE_RX.search(t) or is_symptom),
        "in_scope": bool(_SCOPE_RX.search(t)) or is_symptom or wants_appt,
    }


# ------------------------------------------------------------------- RAG
_retriever = None


def _get_retriever():
    """Load (or build, if artifacts are missing) the project's own RAG index once."""
    global _retriever
    if _retriever is not None:
        return _retriever
    cwd = os.getcwd()
    os.chdir(ROOT)  # rag config uses relative paths
    try:
        from rag.rag_config_loader import load_rag_config
        from rag.retriever import Retriever

        cfg = load_rag_config()
        vs = cfg["vector_store"]
        if not all(os.path.isfile(vs[k]) for k in ("faiss_index_path", "vectorizer_path", "chunks_metadata_path")):
            logger.info("RAG artifacts missing -> building index from rag/knowledge_base ...")
            from rag.document_loader import build_chunks
            from rag.vector_store import VectorStore

            kb = cfg["knowledge_base"]
            VectorStore(cfg).build(build_chunks(kb["source_dir"], kb["chunk_size"], kb["chunk_overlap"]))
        r = Retriever(cfg)
        r.config = {**r.config, "top_k": CANDIDATES}  # fetch a few more, we filter below
        _retriever = r
        return r
    finally:
        os.chdir(cwd)


_LABELS_OBS = ("Possible causes", "Common concerns", "Common reasons for visit")
_LABELS_STEPS = ("General steps", "Precautions", "General precautions")
_LABELS_URGENT = ("Urgent signs", "Urgent escalation")


def _field(text: str, labels) -> str:
    for lab in labels:
        m = re.search(r"\*\*" + re.escape(lab) + r":?\*\*:?\s*(.+)", text)
        if m:
            return re.sub(r"\s+", " ", m.group(1).replace("**", "")).strip()
    return ""


_BOT_RULE_RX = re.compile(r"^(do not|don't|never|avoid giving|avoid strong|use only)", re.I)


def _sentences(text: str, n: int):
    """First n patient-facing sentences (instructions meant for the bot are dropped)."""
    parts = [p.strip() for p in re.split(r"(?<=\.)\s+", text) if p.strip()]
    parts = [p for p in parts if not _BOT_RULE_RX.match(p)]
    short = [p for p in parts if len(p) <= 170]
    return (short or parts)[:n]


def _clinical_chunks(chunks):
    """Keep only chunks that are useful as patient guidance (not product/spec text)."""
    out = []
    for c in chunks:
        txt = c.get("text", "")
        structured = any(f"**{lab}" in txt for lab in _LABELS_STEPS + _LABELS_URGENT)
        small_file = c.get("source") != "hospital_rag_chatbot_knowledge_base.md" and c.get("score", 0) >= 0.12
        if structured or small_file:
            out.append(c)
    return out


def _extractive(chunks) -> dict:
    """Build the suggestion from ONE best section (so text stays consistent), top up from the next one."""
    steps, urgent, obs = [], "", ""
    for c in chunks:
        txt = c["text"]
        part_steps = _field(txt, _LABELS_STEPS)
        if part_steps:
            got = _sentences(part_steps, 3)
        elif c.get("source") != "hospital_rag_chatbot_knowledge_base.md":
            body = re.sub(r"\s+", " ", re.sub(r"^#+.*$", "", txt, flags=re.M)).strip()
            if body[:1].islower() and ". " in body:      # chunk overlap starts mid-sentence
                body = body.split(". ", 1)[1]
            got = _sentences(body, 2)
        else:
            got = []
        if not steps and not got:
            continue                      # chunk with no usable advice, try next
        steps.extend(got)
        obs = obs or _field(txt, _LABELS_OBS)
        urgent = urgent or _field(txt, _LABELS_URGENT)
        break                                 # one consistent section is enough
    urgent_sent = _sentences(urgent, 1)
    obs_sent = _sentences(obs, 1)
    return {
        "observation": ("General info: " + obs_sent[0]) if obs_sent else "",
        "precautions": steps[:3],
        "urgent_note": ("Urgent signs: " + urgent_sent[0]) if urgent_sent else "",
    }


# ------------------------------------------------------------ LLM rewrite
_groq = None


def _get_groq():
    global _groq
    if _groq is None:
        from groq import AsyncGroq

        key = os.getenv("GROQ_API_KEY")
        if not key:
            return None
        _groq = AsyncGroq(api_key=key)
    return _groq


_REWRITE_SYSTEM = (
    "You are Sanjeevani Clinic's assistant. Use ONLY the given context. Reply in simple Hinglish (Roman script).\n"
    "Format exactly:\n"
    "Line 1: one short sentence (max 18 words) of general observation (not a diagnosis).\n"
    "Then 3 numbered precautions, each max 12 words.\n"
    "Last line (only if context lists warning signs): start with 'Turant doctor ko dikhayein agar:' and name 2-3 signs.\n"
    "No medicine names or doses. No extra text."
)


async def _rewrite(query: str, context: str):
    client = _get_groq()
    if client is None:
        return None
    kwargs = dict(
        model=SUGGEST_MODEL,
        messages=[
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": f"Patient said: {query[:300]}\n\nContext:\n{context}"},
        ],
        temperature=0.2,
        max_completion_tokens=450 if "gpt-oss" in SUGGEST_MODEL else 200,
    )
    if "gpt-oss" in SUGGEST_MODEL:
        kwargs["reasoning_effort"] = "low"  # reasoning tokens would eat the latency budget
    resp = await asyncio.wait_for(client.chat.completions.create(**kwargs), LLM_TIMEOUT)
    text = (resp.choices[0].message.content or "").strip()
    lines = [re.sub(r"^[\-\*\u2022\s]+", "", l).strip() for l in text.splitlines() if l.strip()]
    steps = [re.sub(r"^\d+[.)]\s*", "", l) for l in lines if re.match(r"^\d+[.)]", l)]
    obs = next((l for l in lines if not re.match(r"^\d+[.)]", l) and not l.lower().startswith("turant")), "")
    urgent = next((l for l in lines if l.lower().startswith("turant")), "")
    if len(steps) < 2:
        return None
    return {"observation": obs, "precautions": steps[:3], "urgent_note": urgent}


# ------------------------------------------------------------------- cache
_cache = {}


def _cache_get(key):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key, value):
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.time(), value)


# ---------------------------------------------------------------- SerpAPI
async def serp_search(query: str, num: int = 4, news: bool = False) -> dict:
    key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
    if not key:
        return {"success": False, "message": "SERPAPI_API_KEY is not set in .env"}
    params = {"engine": "google", "q": query, "api_key": key, "num": num, "hl": "en", "gl": "in"}
    if news:
        params["tbm"] = "nws"
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=SERP_TIMEOUT) as client:
        r = await client.get("https://serpapi.com/search.json", params=params)
        r.raise_for_status()
        data = r.json()
    items = data.get("news_results") if news else data.get("organic_results")
    results = []
    for it in (items or [])[:num]:
        src = it.get("source")
        if isinstance(src, dict):
            src = src.get("name")
        results.append({
            "title": (it.get("title") or "")[:160],
            "snippet": (it.get("snippet") or "")[:300],
            "source": src or it.get("displayed_link") or "",
            "date": it.get("date") or "",
            "link": it.get("link") or "",
        })
    return {"success": True, "query": query, "results": results, "elapsed_ms": int((time.perf_counter() - t0) * 1000)}


async def web_search_guarded(query: str, news: bool = False, num: int = 4) -> dict:
    """Only medical / clinic / this-project related queries are sent to the internet."""
    if not analyse_text(query)["in_scope"]:
        return {"success": False, "message": "Query is not medical / clinic / project related, so web search was skipped."}
    try:
        return await serp_search(query, num=num, news=news)
    except Exception as e:  # network / quota problems must never break the chat
        logger.warning(f"SerpAPI failed: {e}")
        return {"success": False, "message": f"Web search unavailable: {type(e).__name__}"}


# --------------------------------------------------------- main entrypoint
async def build_suggestion(query: str, specialty_hint: str = "", include_web: bool = False, rewrite=None) -> dict:
    t0 = time.perf_counter()
    rewrite = REWRITE_DEFAULT if rewrite is None else rewrite
    info = analyse_text(query, specialty_hint)
    out = {
        "success": True,
        "intent": info["intent"],
        "is_health_query": info["intent"] == "SYMPTOM",
        "specialty": info["specialty"],
        "emergency": info["emergency"],
        "self_harm": info["self_harm"],
        "is_question": info["is_question"],
        "observation": "", "precautions": [], "urgent_note": "",
        "sources": [], "web": [], "mode": "none",
    }

    if info["intent"] == "SYMPTOM":
        key = (info["specialty"], _norm(query).strip()[:120], rewrite)
        cached = _cache_get(key)
        if cached:
            out.update(cached)
            out["mode"] += "+cache"
        else:
            try:
                retriever = _get_retriever()
                rq = f"{query} {info['hint']}".strip()
                chunks = _clinical_chunks(retriever.retrieve(rq))
                if chunks:
                    out["sources"] = sorted({c["source"] for c in chunks})
                    base = _extractive(chunks)
                    out.update(base)
                    out["mode"] = "rag-extractive"
                    if rewrite:
                        ctx = "\n\n".join(c["text"] for c in chunks[:3])[:MAX_CONTEXT_CHARS]
                        try:
                            rew = await _rewrite(query, ctx)
                            if rew:
                                out.update({k: v for k, v in rew.items() if v})
                                out["mode"] = "rag-llm"
                        except Exception as e:
                            logger.warning(f"Suggestion rewrite skipped: {type(e).__name__}: {e}")
                    _cache_put(key, {k: out[k] for k in ("observation", "precautions", "urgent_note", "sources", "mode")})
            except Exception as e:
                logger.error(f"RAG suggestion failed: {e}")

    if (include_web or info["wants_web"]) and info["in_scope"]:
        web = await web_search_guarded(query, news=True, num=3)
        if web.get("success"):
            out["web"] = web["results"]
            out["mode"] += "+web"

    out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return out
