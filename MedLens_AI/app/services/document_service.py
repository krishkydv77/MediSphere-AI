import re
from app.core.logger import get_logger
logger = get_logger(__name__)

MEDICAL_TERMS = re.compile(r"prescription|rx|tablet|capsule|mg|ml|doctor|dose|medicine|medication|drug|दवा|गोली", re.I)
REPORT_TERMS = re.compile(r"hemoglobin|haemoglobin|cbc|wbc|rbc|platelet|glucose|sugar|cholesterol|report|reference range|test result", re.I)

def classify_document(text: str, filename: str = "") -> str:
    logger.info("Classifying document %s", filename)
    t = text or ""
    if MEDICAL_TERMS.search(t):
        if re.search(r"prescription|\brx\b|\b1-0-1\b|\b1-1-1\b|doctor|दवा", t, re.I):
            return "prescription"
    if REPORT_TERMS.search(t):
        return "medical_report"
    return "unknown_medical_document"

def extract_entities(text: str) -> dict:
    """Basic transparent extraction. LLM can enrich it, but OCR output is never treated as verified."""
    medicine_lines = []
    for line in (text or "").splitlines():
        if re.search(r"\b(mg|mcg|g|ml|tablet|tab\.?|cap\.?|capsule|syrup|\bOD\b|\bBD\b|\bTDS\b|\bSOS\b)\b", line, re.I):
            medicine_lines.append(line.strip())
    values = []
    for line in (text or "").splitlines():
        match = re.search(r"([A-Za-z][A-Za-z /()-]{1,35})\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mg/dL|g/dL|%|mmol/L|/µL|/uL|IU/L|mIU/L)?", line, re.I)
        if match:
            values.append({"name": match.group(1).strip(), "value": match.group(2), "unit": match.group(3) or "", "raw": line.strip()})
    return {"medicine_lines": medicine_lines, "report_values": values}

def summary_fallback(text: str, doc_type: str, entities: dict) -> str:
    if not text.strip():
        return "OCR text could not be extracted reliably. Please upload a clearer image or PDF."
    if doc_type == "prescription":
        meds = entities.get("medicine_lines", [])
        bullets = "\n".join(f"- {m}" for m in meds) if meds else "- No medicine instruction was confidently detected."
        return "Prescription text extracted (not a verified interpretation):\n" + bullets + "\n\nPlease confirm unclear medicine names, strengths, and timing with your prescriber or pharmacist. This system will not guess unreadable dosage instructions."
    if doc_type == "medical_report":
        vals = entities.get("report_values", [])
        bullets = "\n".join(f"- {v['name']}: {v['value']} {v['unit']} (OCR text: {v['raw']})" for v in vals[:30])
        if not bullets:
            bullets = "- No numeric test values were confidently extracted."
        return "Extracted report items (please verify against the original report):\n" + bullets + "\n\nValues cannot be interpreted safely without the laboratory's reference ranges and patient context. This is not a diagnosis."
    return "Document text was extracted, but its type could not be determined reliably. Please review the OCR text and upload a clearer file if needed."
