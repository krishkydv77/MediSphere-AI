from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    app_name: str = "MedLens AI"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    max_upload_mb: int = 15
    tesseract_cmd: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    enable_llm: bool = False
    chroma_path: str = "./data/chroma"
    upload_dir: str = "./uploads"
    kb_dir: str = "./knowledge_base"
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    def path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else ROOT / p

settings = Settings()
