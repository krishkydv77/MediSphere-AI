from fastapi import HTTPException
from app.core.logger import get_logger
logger = get_logger(__name__)

def safe_error(where: str, exc: Exception, status_code: int = 500):
    logger.exception("Unhandled error at %s: %s", where, exc)
    return HTTPException(status_code=status_code, detail="Something went wrong. Check application logs for details.")
