import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from .database import init_db
from .ai_agent import ask_agent
from src.exception import CustomException
from src.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Medical Clinic MCP Server", version="2.0.0")


class ChatRequest(BaseModel):
    message: str
    role: Optional[str] = "User"  # Roles: User, Admin, Super Admin, System


@app.on_event("startup")
def startup():
    try:
        init_db()
        logger.info("Application startup completed successfully.")
    except Exception as e:
        logger.error("Error during application startup.")
        raise CustomException(e, sys)


@app.get("/")
def root():
    return {"message": "Clinic AI Assistant active with RBAC & Anti-Hallucination."}


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        valid_roles = ["User", "Admin", "Super Admin", "System"]
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail="Invalid role specified.")

        result = await ask_agent(request.message, user_role=request.role)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing chat request.")
        raise CustomException(e, sys)