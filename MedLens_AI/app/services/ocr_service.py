from pathlib import Path
import io
import fitz
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
from app.core.config import settings
from app.core.logger import get_logger
logger = get_logger(__name__)

if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

def _prep_image(image: Image.Image) -> Image.Image:
    """Light preprocessing to improve OCR; preserves original orientation where possible."""
    image = ImageOps.grayscale(image)
    image = ImageEnhance.Contrast(image).enhance(1.5)
    return image

def extract_text(file_path: str | Path) -> dict:
    """Extract text from PDF or raster image using Tesseract OCR."""
    path = Path(file_path)
    ext = path.suffix.lower()
    logger.info("OCR started: file=%s extension=%s", path.name, ext)
    pages = []
    if ext == ".pdf":
        doc = fitz.open(path)
        for idx, page in enumerate(doc):
            native = page.get_text("text").strip()
            if len(native) >= 40:
                text = native
                source = "pdf_text"
            else:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(_prep_image(image), config="--psm 6")
                source = "tesseract"
            pages.append({"page": idx + 1, "text": text.strip(), "source": source})
        doc.close()
    elif ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        image = Image.open(path).convert("RGB")
        pages.append({"page": 1, "text": pytesseract.image_to_string(_prep_image(image), config="--psm 6").strip(), "source": "tesseract"})
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    text = "\n\n".join(f"[Page {p['page']}]\n{p['text']}" for p in pages)
    logger.info("OCR complete: %s pages, %s characters", len(pages), len(text))
    return {"text": text, "pages": pages, "page_count": len(pages)}
