from typing import TypedDict, Any
from langgraph.graph import StateGraph, END
from app.core.logger import get_logger
from app.services.document_service import classify_document, extract_entities, summary_fallback
from app.services.rag_service import rag
from app.services.llm_service import invoke_medical_prompt
logger = get_logger(__name__)

class MedState(TypedDict, total=False):
    text: str
    filename: str
    document_type: str
    entities: dict
    summary: str
    question: str
    age: int | None
    medicine_confirmed: bool
    retrieved: list[dict]
    answer: str
    safety_flags: list[str]
    needs_age: bool
    needs_confirmation: bool
    medicine_intent: bool
    dosage_intent: bool
    document_context: str

def classify_node(state: MedState):
    if state.get("question"):
        return {}
    kind = classify_document(state.get("text", ""), state.get("filename", ""))
    return {"document_type": kind, "entities": extract_entities(state.get("text", ""))}

def summary_node(state: MedState):
    if state.get("question"):
        return {}
    fallback = summary_fallback(state.get("text", ""), state.get("document_type", "unknown"), state.get("entities", {}))
    prompt = ("You are a cautious medical document explainer. Do not diagnose, prescribe, infer missing data, "
              "or invent values. Explain extracted information in simple Hindi-English, note OCR uncertainty, "
              "and remind the user to verify with the original document and clinician.\n\n"
              f"Document type: {state.get('document_type')}\nOCR: {state.get('text', '')[:10000]}\n"
              f"Extracted fields: {state.get('entities', {})}\nFallback: {fallback}")
    llm_summary = invoke_medical_prompt(prompt)
    return {"summary": llm_summary or fallback}

def context_node(state: MedState):
    question = state.get("question", "")
    age = state.get("age")
    flags = []
    lower = question.lower()
    medicine_intent = any(word in lower for word in ["medicine", "medication", "drug", "tablet", "capsule", "दवा", "गोली"])
    dosage_intent = any(word in lower for word in ["dose", "dosage", "how to take", "kitni", "kaise len", "kab len", "din me", "timing"])
    if age is None:
        flags.append("Patient age not provided; age-dependent advice is withheld.")
    return {"safety_flags": flags, "needs_age": bool(age is None and (medicine_intent or dosage_intent)), "needs_confirmation": bool(medicine_intent and age is not None and not state.get("medicine_confirmed", False)), "medicine_intent": medicine_intent, "dosage_intent": dosage_intent}

def route_after_context(state: MedState):
    if state.get("needs_confirmation") or state.get("needs_age"):
        return "answer"
    return "retrieve"

def retrieve_node(state: MedState):
    q = state.get("question", "")
    if not q:
        return {"retrieved": []}
    try:
        hits = rag.search(q, k=4)
        return {"retrieved": hits}
    except Exception as exc:
        logger.exception("Knowledge retrieval unavailable: %s", exc)
        return {"retrieved": [], "safety_flags": state.get("safety_flags", []) + ["Medical knowledge retrieval is unavailable; response limited to general guidance."]}

def answer_node(state: MedState):
    question = state.get("question", "")
    lower = question.lower()
    dosage_intent = any(word in lower for word in ["dose", "dosage", "how to take", "kitni", "kaise len", "kab len", "din me", "timing"])
    if state.get("needs_age", False) or (dosage_intent and state.get("age") is None):
        return {"answer": "Patient ki age batayein. Age ke bina patient-specific medicine information ko personalize nahi kiya jayega. Prescription ke exact instructions follow karein; unclear instructions doctor/pharmacist se confirm karein."}
    if state.get("needs_confirmation", False):
        return {"answer": "Please confirm the medicine name and strength shown on the image/prescription. OCR may misread labels. Reply with the confirmed name and strength; do not use an uncertain identification to take medicine."}
    context = "\n\n".join(h["text"] for h in state.get("retrieved", []))
    uploaded_context = state.get("document_context", "")
    prompt = ("You are MedLens AI, a cautious medical information assistant. Give general educational information only. "
              "Never prescribe, calculate/alter dose, or infer a diagnosis. Do not give timing/frequency unless explicitly "
              "read from a user-provided prescription and clearly label as extracted, not verified. Ask the user to confirm "
              "medicine name/strength. Mention urgent care for emergencies. Use simple Hinglish.\n"
              f"Question: {question}\nAge: {state.get('age')}\nUploaded document OCR context: {uploaded_context[:8000]}\nRetrieved context: {context}\nSafety flags: {state.get('safety_flags', [])}")
    answer = invoke_medical_prompt(prompt) or "I can provide general medicine information, but I cannot prescribe or calculate a dose. Please follow the prescriber's directions and confirm unclear instructions with a pharmacist/doctor."
    if context:
        answer += "\n\nRelevant knowledge-base excerpts (verify source details):\n" + context
    if uploaded_context:
        answer += "\n\nFrom your uploaded document OCR (please check the original):\n" + uploaded_context[:4000]
    if state.get("safety_flags"):
        answer += "\n\nSafety notes:\n- " + "\n- ".join(state["safety_flags"])
    if question:
        answer += "\n\nFor patient-specific dose or treatment, please consult the prescriber. If you share the medicine name and exact strength, I can explain its general purpose and common precautions."
    return {"answer": answer}

def build_graph():
    graph = StateGraph(MedState)
    graph.add_node("classify", classify_node)
    graph.add_node("summarize", summary_node)
    graph.add_node("context", context_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("answer", answer_node)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "summarize")
    graph.add_edge("summarize", "context")
    graph.add_conditional_edges("context", route_after_context, {"answer": "answer", "retrieve": "retrieve"})
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()

workflow = build_graph()

def analyze_document(text: str, filename: str) -> dict:
    logger.info("Graph: analyze document %s", filename)
    return workflow.invoke({"text": text, "filename": filename})

def answer_question(question: str, age: int | None = None, medicine_confirmed: bool = False, document_context: str = "") -> dict:
    logger.info("Graph: medical Q&A started; age_present=%s confirmation=%s", bool(age), medicine_confirmed)
    return workflow.invoke({"question": question, "age": age, "medicine_confirmed": medicine_confirmed, "text": "", "filename": "question", "document_context": document_context})
