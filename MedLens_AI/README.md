# MedLens AI — Medical Report and Prescription Assistant

A local-first educational prototype for reading medical documents and explaining OCR-extracted information in simple language. Uses FastAPI, plain HTML/CSS/JavaScript, Tesseract OCR, LangChain (optional Gemini LLM), LangGraph workflow, ChromaDB and Sentence Transformers embeddings.

> **Medical safety:** This application is not a doctor, does not diagnose, prescribe, or calculate doses. OCR can misread names, decimal points, strengths, and instructions. Verify everything against the original document. For medicine-specific or patient-specific treatment decisions, contact a qualified doctor/pharmacist. Do not use the demo for emergencies.

## Features
- Upload PDF, PNG, JPG/JPEG, WEBP, BMP, TIFF (maximum file size configurable).
- PDF text extraction first; image pages are OCR'd with Tesseract. Images are OCR'd using Tesseract.
- Lightweight document classification and transparent OCR extraction of candidate medication lines/report values.
- LangGraph graph for classification, summary, context/safety flags, retrieval and response.
- Optional LangChain + Gemini summarization (disabled by default; enable only after adding an API key).
- Chroma persistent vector DB + Sentence Transformers (`all-MiniLM-L6-v2`) embeddings, ingests local Markdown/TXT knowledge base.
- Simple responsive frontend (no React/Node build needed).
- No authentication by design (as requested); local prototype only.
- Logging: terminal plus daily Markdown file under `logs/`, with timestamp, logger/module and function name. Exceptions include tracebacks in terminal/file.

## Windows setup

### 1. Install prerequisites
- Python 3.11 recommended.
- Tesseract OCR for Windows: install it from the official Tesseract project distribution and remember the executable path (often `C:\Program Files\Tesseract-OCR\tesseract.exe`).
- For scanned PDF OCR, PyMuPDF renders pages for Tesseract; Poppler is not required.

### 2. Clone/extract, create virtual environment
```powershell
cd MedLens_AI
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment
```powershell
copy .env.example .env
```
Edit `.env` and set the Tesseract path if not automatically detected:
```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```
LLM is off by default. To enable Gemini-powered natural-language document summaries:
```env
ENABLE_LLM=true
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash
```
Never commit `.env` or real patient data. Gemini is an external service; consider privacy and consent before sending medical data.

### 4. Run
```powershell
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000. API docs: http://127.0.0.1:8000/docs.

## OCR setup validation
```powershell
tesseract --version
```
If command is not found, set `TESSERACT_CMD` in `.env` to the installed executable path.

## Tests
```powershell
pytest -q
```
Tests are unit/API smoke tests and do not validate OCR accuracy, LLM medical correctness, clinical safety, or every file format. Test the app with sample files that contain no personal data.

## API
- `GET /api/health`
- `POST /api/analyze` — multipart file
- `POST /api/chat` — form fields: `question`, optional `age`, `medicine_confirmed`
- `GET /api/logs/latest` — returns recent log text for local debugging

## Project layout
```text
MedLens_AI/
├── app/
│   ├── core/        config, logger, exception handling
│   ├── services/    OCR, document extraction, RAG, optional LLM
│   ├── graph/       LangGraph workflow
│   └── main.py      FastAPI app and endpoints
├── static/          HTML, CSS, vanilla JavaScript frontend
├── knowledge_base/  starter medical safety knowledge documents
├── uploads/         temporary uploaded files
├── data/chroma/     persistent ChromaDB data (created at runtime)
├── logs/            daily Markdown log files (created at runtime)
└── tests/           smoke tests
```

## Known limitations / next steps
- OCR extraction/classification is intentionally heuristic; handwriting and complex tables need stronger OCR/document models and a reviewer.
- General medical retrieval corpus is only starter safety content. Add licensed, reputable, reviewed reference materials before presenting medicine facts.
- LLM is optional and currently used to rewrite document summaries; question answering remains conservative and retrieves local context. The default is no external LLM call.
- The checkbox in the chat UI is a user confirmation of a medicine identification, **not a clinician's approval**.
- No authentication or access controls are included, per request. Do not deploy publicly or process sensitive patient records until access controls, encryption, consent, retention/deletion, audit and security review are implemented.
- Age is collected only if supplied; it is not a substitute for medical history or professional review.
