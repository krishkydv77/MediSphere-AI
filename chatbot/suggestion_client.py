"""
Bridge between the chatbot (text / image / voice) and the MCP `health_suggestion` tool.

fetch_suggestion()      -> calls the MCP tool (RAG suggestion, optional web news)
build_intro_html()      -> turns the tool result into the HTML intro used by suggest_doctor_reply()

If the MCP server is down / slow, fetch_suggestion() returns None and main.py falls back to the
old behaviour, so the chatbot never breaks because of this module.
"""
import html
import os

from src.logger import get_logger

logger = get_logger(__name__)

SUGGESTION_TIMEOUT = float(os.getenv("SUGGESTION_TOOL_TIMEOUT", "6"))


async def fetch_suggestion(query: str, specialty: str = ""):
    try:
        from medical_mcp.ai_agent import call_mcp_tool

        data = await call_mcp_tool(
            "health_suggestion",
            {"query": query, "specialty": specialty},
            timeout=SUGGESTION_TIMEOUT,
        )
        if isinstance(data, dict) and data.get("success"):
            logger.info(
                f"MCP health_suggestion -> intent={data.get('intent')} spec={data.get('specialty')} "
                f"mode={data.get('mode')} {data.get('elapsed_ms')}ms"
            )
            return data
        logger.warning(f"health_suggestion returned unexpected data: {str(data)[:200]}")
    except Exception as e:
        logger.warning(f"health_suggestion MCP call failed ({type(e).__name__}: {e}); using fallback flow.")
    return None


def _esc(text: str) -> str:
    return html.escape(text or "")


def build_precautions_html(sug: dict) -> str:
    """Emergency banner + observation + precautions + urgent note + (optional) latest web info."""
    out = ""
    if sug.get("self_harm"):
        out += ("💙 <b>Aap akele nahi hain.</b> Abhi kisi apne se baat karein ya 112 / Tele-MANAS 14416 par call karein. "
                "Agar aap khud ko nuksaan pahunchane ke baare me soch rahe hain to turant madad lein.<br><br>")
    elif sug.get("emergency"):
        out += ("🚨 <b>Yeh emergency ho sakti hai. Turant 112 / 108 par call karein ya nazdeeki hospital ke "
                "emergency me jayein.</b> Doctor appointment ka intezaar na karein.<br><br>")

    pre = sug.get("precautions") or []
    if pre:
        if sug.get("observation"):
            out += f"{_esc(sug['observation'])}<br><br>"
        out += "<b>Immediate Precautions:</b><br>"
        for i, p in enumerate(pre[:3], 1):
            out += f"{i}. {_esc(p)}<br>"
        out += "<br>"
        if sug.get("urgent_note"):
            out += f"⚠️ {_esc(sug['urgent_note'])}<br><br>"

    web = sug.get("web") or []
    if web:
        out += "🌐 <b>Latest (internet):</b><br>"
        for w in web[:2]:
            line = w.get("title", "")
            if w.get("snippet"):
                line += f" - {w['snippet']}"
            out += f"• {_esc(line[:220])}"
            if w.get("source"):
                out += f" <i>({_esc(w['source'])})</i>"
            out += "<br>"
        out += "<br>"
    return out


def build_intro_html(sug: dict) -> str:
    """
    Full intro for suggest_doctor_reply().  Returns "" when RAG found nothing for a SYMPTOM
    (suggest_doctor_reply then uses its own built-in intro).
    """
    spec = sug.get("specialty") or "General OPD"
    if sug.get("intent") == "APPOINTMENT":
        return "Theek hai, appointment ke liye yeh doctors available hain:<br><br>"

    body = build_precautions_html(sug)
    if not (sug.get("precautions") or sug.get("emergency") or sug.get("self_harm")):
        return ""
    return body + f"Aapko <b>{_esc(spec)}</b> specialist ko dikhana chahiye. Yeh doctors available hain:<br><br>"
