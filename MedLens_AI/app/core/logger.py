"""Project-wide logger: console + daily Markdown log file, including module/function context."""
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

class MarkdownFormatter(logging.Formatter):
    def format(self, record):
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        msg = record.getMessage().replace("\n", "\\n")
        return f"| {ts} | {record.levelname} | `{record.name}` | `{record.funcName}` | {msg} |"

class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        return f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} | {record.levelname:<8} | {record.name}.{record.funcName} | {record.getMessage()}"

_logfile = LOG_DIR / f"medlens-{datetime.now():%Y-%m-%d}.md"
root_logger = logging.getLogger("medlens")
root_logger.setLevel(logging.INFO)
root_logger.propagate = False
if not root_logger.handlers:
    file_handler = RotatingFileHandler(_logfile, maxBytes=3_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(MarkdownFormatter())
    console = logging.StreamHandler()
    console.setFormatter(ConsoleFormatter())
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console)
    # Markdown header (once per newly created daily file)
    if _logfile.stat().st_size == 0:
        with open(_logfile, "a", encoding="utf-8") as f:
            f.write("# MedLens AI logs\n\n| Timestamp | Level | Logger / File | Function | Message |\n|---|---|---|---|---|\n")

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"medlens.{name}")
