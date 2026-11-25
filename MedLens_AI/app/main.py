from pathlib import Path
import uuid
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings, ROOT
from app.core.logger import get_logger
from app.services.ocr_service import extract_text
from app.graph.workflow import analyze_document, answer_question
from app.core.exceptions import safe_error
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name, description="Medical report and prescription explainer. Educational only.", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    logger.info("Serving frontend")
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    logger.info("Health check")
    return {"status": "ok", "service": settings.app_name, "authentication": "disabled"}

@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    logger.info("Upload received: %s", file.filename)
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        return JSONResponse(status_code=415, content={"detail": "Allowed file types: PDF, PNG, JPG/JPEG, WEBP, BMP, TIFF."})
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": f"File is larger than {settings.max_upload_mb} MB."})
    upload_dir = settings.path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = upload_dir / f"{uuid.uuid4().hex}{ext}"
    saved.write_bytes(content)
    try:
        ocr = extract_text(saved)
        result = analyze_document(ocr["text"], file.filename or saved.name)
        return {"file_id": saved.stem, "filename": file.filename, "document_type": result.get("document_type"),
                "ocr_text": ocr["text"], "page_count": ocr["page_count"], "pages": ocr["pages"],
                "entities": result.get("entities", {}), "summary": result.get("summary", ""),
                "disclaimer": "OCR can make mistakes. Verify all extracted values and medicine names against the original. This is not a diagnosis or a prescription."}
    except Exception as exc:
        logger.exception("Document analysis failed for %s", file.filename)
        saved.unlink(missing_ok=True)
        raise safe_error("analyze upload", exc)

@app.post("/api/chat")
def chat(question: str = Form(...), age: int | None = Form(None), medicine_confirmed: bool = Form(False), document_context: str = Form("")):
    logger.info("Chat request; age_given=%s confirmed=%s", age is not None, medicine_confirmed)
    if not question.strip():
        return JSONResponse(status_code=422, content={"detail": "Question is required."})
    if age is not None and (age < 0 or age > 120):
        return JSONResponse(status_code=422, content={"detail": "Please enter a valid age from 0 to 120."})
    try:
        result = answer_question(question, age, medicine_confirmed, document_context)
        return {"answer": result.get("answer", ""), "safety_flags": result.get("safety_flags", []), "sources": result.get("retrieved", [])}
    except Exception as exc:
        logger.exception("Chat workflow failed")
        raise safe_error("chat", exc)

@app.get("/api/logs/latest")
def latest_log():
    log_dir = ROOT / "logs"
    files = sorted(log_dir.glob("medlens-*.md"), reverse=True)
    if not files:
        return {"log": "No log file created yet."}
    return {"filename": files[0].name, "log": files[0].read_text(encoding="utf-8")[-12000:]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
