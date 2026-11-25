"""Optional LangChain Gemini wrapper. The app remains usable without an API key."""
from app.core.config import settings
from app.core.logger import get_logger
logger = get_logger(__name__)

def invoke_medical_prompt(prompt: str) -> str | None:
    if not settings.enable_llm or not settings.gemini_api_key:
        logger.info("LLM disabled or API key absent; deterministic fallback used")
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = ChatGoogleGenerativeAI(model=settings.gemini_model, google_api_key=settings.gemini_api_key, temperature=0.1)
        result = model.invoke(prompt)
        return str(result.content)
    except Exception:
        logger.exception("LangChain Gemini call failed")
        return None
