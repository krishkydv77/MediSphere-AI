from app.services.document_service import classify_document, extract_entities, summary_fallback

def test_classifies_prescription():
    assert classify_document("Rx Tab paracetamol 500 mg 1-0-1") == "prescription"

def test_classifies_report():
    assert classify_document("CBC report Hemoglobin 11 g/dL reference range") == "medical_report"

def test_extract_medicine_lines():
    result = extract_entities("Tab ABC 500 mg\nTake 1 tablet BD")
    assert result["medicine_lines"]

def test_empty_summary():
    assert "clearer" in summary_fallback("", "unknown", {}).lower()
