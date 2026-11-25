import os
import sys
import json
import time
import uvicorn
import html
import random
from datetime import date
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, Form, Request, File, UploadFile, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from rag.rag_pipeline import RAGPipeline 

# Path Setup: Add current working directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Imports from COVID Prediction & Pretrained NLP App
from src.exception import CustomException
from src.logger import get_logger
from src.pipeline.predict_pipeline import CustomData, PredictPipeline
from nlp_pretrained.ner_tagger import get_pos_tags, extract_entities
from nlp_pretrained.embedding import most_similar_words
from nlp_pretrained.sentiment_analyzer import analyze_sentiment

#MedLens_AI


# Imports from Chatbot Backend & Database Setup
from chatbot.database.db_config import get_db
from chatbot.database.models import User, Doctor, Booking, PatientHistory, init_db
from chatbot.history_handler import get_user_summary
from chatbot.llm_helper import analyze_and_respond, get_llm_response
from chatbot.doctor_suggestion import get_doctor_recommendation
from chatbot.injury_analyzer import analyze_injury_image
from chatbot.suggestion_client import fetch_suggestion, build_intro_html, build_precautions_html  # MCP suggestion tool (RAG)
from chatbot.chat_log import save_chat_message, update_chat_timing  # text/image/voice chats -> same DB
from chatbot import voice_handler as vh  # Sarvam STT/TTS

# Imports from medical_mcp Module
from medical_mcp.ai_agent import ask_agent
from medical_mcp.database import init_db as init_mcp_db

#user handler
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from user_handle import limiter, oauth, create_access_token, require_role, verify_jwt_token

logger = get_logger(__name__)

app = FastAPI(title="Covid Prediction Clinic & Medical MCP Server", version="2.0.0")
app.add_middleware(SessionMiddleware, secret_key="healthcare_secret_key")

# Rate Limiting ko app state me register karein
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- 1. Rate Limited Chat Endpoint --- ye nichhe set kar diya ha 
# @app.post("/api/chat")
# @limiter.limit("15/minute") # Ek user 1 minute me max 15 requests bhej sakta hai
# async def chat_endpoint(request: Request):
#     # Aapka chat logic yahan rahega
#     return {"message": "Chat request processed safely with rate limiting!"}


# --- 2. JWT & Login Test Route (Token lene ke liye) ---
@app.post("/api/login-demo")
async def login_demo(username: str, role: str = "User"):
    # Dummy login jo JWT token generate karke dega
    token = create_access_token({"sub": username, "role": role})
    return {"access_token": token, "token_type": "bearer"}


# --- 3. RBAC Protected Admin Route ---
@app.get("/api/admin/dashboard")
async def admin_dashboard(user_data = Depends(require_role("Admin"))):
    # Yeh route sirf 'Admin' ya 'Super Admin' hi access kar payega
    return {"status": "Success", "message": "Welcome to Admin Dashboard", "admin": user_data.get("sub")}


# --- 4. OAuth Google Login Routes ---
@app.get('/auth/google')
async def google_login(request: Request):
    redirect_uri = request.url_for('google_auth_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get('/auth/google/callback')
async def google_auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    
    # Yahan user ko database me check/register kar sakte hain
    email = user_info.get("email")
    
    # User ke liye apna JWT token generate karke bhej sakte hain
    app_jwt_token = create_access_token({"sub": email, "role": "User"})
    
    return {
        "status": "Login successful via Google",
        "email": email,
        "jwt_access_token": app_jwt_token
    }
#=========================================================

# In-Memory storage for System Users created by Admin & Audit Logs
db_system_users = {}
db_audit_logs = [
    {"timestamp": "2026-10-08 03:50:00", "user_role": "Admin", "tool": "GenerateSystemUser", "rbac_status": "SUCCESS"},
    {"timestamp": "2026-10-08 03:52:10", "user_role": "System", "tool": "FastMCP_HealthCheck", "rbac_status": "SUCCESS"}
]

## mounting the css file
app.mount("/static", StaticFiles(directory="static"), name="static")

# --------------------------------------------------------------------------
# MedLens AI (sub-application) -> available at /medlens/
# Poora MedLens app alag sub-app me mount hota hai, isliye iske routes
# (/api/chat, /static, /) main project ke routes se kabhi clash nahi karte.
# Agar MedLens load na ho paye to bhi main project normal chalega.
# --------------------------------------------------------------------------
try:
    _MEDLENS_DIR = os.path.join(BASE_DIR, "MedLens_AI")
    if _MEDLENS_DIR not in sys.path:
        sys.path.append(_MEDLENS_DIR)
    from app.main import app as medlens_app
    app.mount("/medlens", medlens_app, name="medlens")
    logger.info("MedLens AI mounted at /medlens")
except Exception as e:
    logger.warning(f"MedLens AI could not be loaded (main project unaffected): {e}")

## Set the template folder
templates = Jinja2Templates(directory="templates")

try:
    init_db()        # Chatbot Main SQL DB Init
    init_mcp_db()    # Medical MCP Clinic DB Init
    logger.info("FastAPI App initialized and all Database tables synchronized.")
except Exception as e:
    raise CustomException(e, sys)


# --------------------------------------------------------------------------
# MEDICAL MCP CHAT ENDPOINT & SCHEMAS
# --------------------------------------------------------------------------

class MCPChatRequest(BaseModel):
    message: str
    role: Optional[str] = "User"  # Roles: User, Admin, Super Admin, System


@app.post("/chat")
@app.post("/api/mcp-chat")
async def mcp_chat_endpoint(request: MCPChatRequest):
    """
    Direct MCP Agent chat endpoint with RBAC & FastMCP support.
    """
    try:
        valid_roles = ["User", "Admin", "Super Admin", "System"]
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail="Invalid role specified.")

        result = await ask_agent(request.message, user_role=request.role)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing MCP chat request.")
        raise CustomException(e, sys)


# --------------------------------------------------------------------------
# HOME PAGE ROUTE
# --------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    logger.info("Home page accessed...")
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user_name": request.session.get("user_name")}
    )


# --------------------------------------------------------------------------
# ADMIN & SYSTEM PAGE ROUTES
# --------------------------------------------------------------------------

@app.get("/admin.html", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request):
    logger.info("Admin page accessed...")
    return templates.TemplateResponse(request=request, name="admin.html")


@app.get("/system.html", response_class=HTMLResponse)
@app.get("/system", response_class=HTMLResponse)
async def read_system(request: Request):
    logger.info("System page accessed...")
    return templates.TemplateResponse(request=request, name="system.html")


# --------------------------------------------------------------------------
# ADMIN & SYSTEM BACKEND APIS
# --------------------------------------------------------------------------

class AdminLoginSchema(BaseModel):
    email: str
    password: str

@app.post("/api/admin/login")
async def admin_login(data: AdminLoginSchema):
    if data.email == "admin@sanjeevani.com" and data.password == "admin123":
        return {"status": "success", "message": "Admin authentication successful", "token": "mock-admin-jwt-token"}
    raise HTTPException(status_code=401, detail="Invalid Admin credentials")


class SystemCredentialSchema(BaseModel):
    system_user_id: str
    password: str

@app.post("/api/admin/generate-system-credentials")
async def generate_system_credentials(credentials: SystemCredentialSchema):
    db_system_users[credentials.system_user_id] = credentials.password
    db_audit_logs.append({
        "timestamp": "2026-10-08 03:54:00",
        "user_role": "Admin",
        "tool": "GenerateSystemCredentials",
        "rbac_status": "SUCCESS"
    })
    return {
        "status": "success",
        "message": f"Credentials generated for system user: {credentials.system_user_id}"
    }


class SystemLoginSchema(BaseModel):
    system_user_id: str
    password: str

@app.post("/api/system/login")
async def system_login(data: SystemLoginSchema):
    stored_password = db_system_users.get(data.system_user_id)
    if data.system_user_id == "SYS_MONITOR_01" and data.password == "syspass123":
        return {"status": "success", "message": "System Access Granted", "token": "mock-sys-jwt-token"}
        
    if stored_password and stored_password == data.password:
        return {"status": "success", "message": "System Access Granted", "token": "mock-sys-jwt-token"}
        
    raise HTTPException(status_code=401, detail="Invalid System User ID or Password")


@app.get("/api/system/metrics")
async def get_system_metrics():
    return {
        "fastmcp_status": "RUNNING",
        "fastmcp_port": 8001,
        "database_status": "CONNECTED",
        "groq_llm_status": "ONLINE",
        "active_connections": 12
    }


@app.get("/api/system/audit-logs")
async def get_audit_logs():
    return {"logs": db_audit_logs}


# --------------------------------------------------------------------------
# USER AUTHENTICATION
# --------------------------------------------------------------------------

@app.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    clean_email = email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()

    if not user:
        default_name = clean_email.split("@")[0].capitalize()
        new_user = User(
            name=default_name,
            email=clean_email,
            password=password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
    else:
        if user.password != password:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Sahi password daalein! Yeh email pehle se registered hai."}
            )

    request.session.clear()
    request.session["user_id"] = user.user_id
    request.session["user_name"] = user.name

    return {"status": "success", "message": "Login successful", "user_name": user.name}


@app.get("/logout")
async def logout(request: Request):
    user_name = request.session.get("user_name", "User")
    request.session.clear()
    logger.info(f"User '{user_name}' logged out.")
    return RedirectResponse(url="/")


@app.get("/predict", response_class=HTMLResponse)
async def predict_form(request: Request):
    logger.info("Predict form page accessed.....") 
    return templates.TemplateResponse(request, "predict.html", {"result": None}) 


@app.post("/predict", response_class=HTMLResponse)
async def predict_result(
    request: Request,
    age: int = Form(...),
    gender: str = Form(...),
    fever: float = Form(...),
    cough: str = Form(...),
    city: str = Form(...) 
):
    try:
        logger.info(f"Prediction request received :: age{age}, gender{gender}, fever{fever}, cough{cough},city{city}")
        custom_data = CustomData(age=age, gender=gender, fever=fever, cough=cough, city=city)
        data_df = custom_data.get_data_as_dataframe() 
        predict_pipeline = PredictPipeline() 
        result, probability = predict_pipeline.predict(data_df) 
        return templates.TemplateResponse(
            request,
            "predict.html",
            {
                "result": result,
                "probability": probability,
                "form_data": {
                    "age": age,
                    "gender": gender,
                    "fever": fever,
                    "cough": cough,
                    "city": city
                }
            }
        )
    except Exception as e:
        raise CustomException(e, sys) 


@app.get("/pretrained-nlp", response_class=HTMLResponse) 
async def pretrained_nlp_form(request: Request):
    return templates.TemplateResponse(request, 
                                      "pretrained_nlp.html",
                                      {
                                          "result": None,
                                          "form_data": {"query": ""},
                                          "error": None 
                                      })


@app.post("/pretrained-nlp", response_class=HTMLResponse) 
async def pretrained_nlp_analysis(
    request: Request,
    query: str = Form(...)
):
    try:
        query = query.strip() 
        if not query:
            return templates.TemplateResponse(
                request,
                "pretrained_nlp.html",
                {
                    "result": None,
                    "form_data": {"query": ""},
                    "error": "Please enter some text..." 
                }
            )

        pos_tags = get_pos_tags(query) 
        entities = extract_entities(query) 
        sentiment = analyze_sentiment(query) 

        similar_words = [] 
        words = query.split() 
        first_word = words[0].lower() 
        if words:
            try:
                similar_words = most_similar_words(first_word, topn=5) 
            except Exception as e:
                logger.warning(f"Glove similarity failed for: {first_word} and the error is: {e}") 
                similar_words = [] 

        result = {
            "query": query,
            "pos_tags": pos_tags,
            "entities": entities,
            "similar_words": similar_words,
            "sentiment": sentiment
        }

        return templates.TemplateResponse(
            request,
            "pretrained_nlp.html",
            {
                "result": result,
                "form_data": {"query": query},
                "error": None
            }
        )

    except Exception as e:
        logger.info("Error occured in pretrained nlp analysis")
        return templates.TemplateResponse(
            request,
            "pretrained_nlp.html",
            {
                "result": None,
                "form_data": {"query": query},
                "error": str(e)
            }
        )

# --------------------------------------------------------------------------
# CHATBOT BACKEND & APPOINTMENT FLOW
# --------------------------------------------------------------------------
AVAILABLE_SLOTS = ["10:00 AM", "11:30 AM", "02:00 PM", "04:30 PM", "06:00 PM"]
CONFIRM_WORDS = ["yes", "haan", "ha", "haa", "ok", "okay", "confirm", "book kardo", "book kar do"]
NO_WORDS = ["no", "nahi", "na"]


def get_free_slots(db: Session, doctor_id: int):
    booked = db.query(Booking.slot_time).filter(
        Booking.doctor_id == doctor_id,
        Booking.booking_date == date.today()
    ).all()
    booked_slots = [b[0] for b in booked]
    return [slot for slot in AVAILABLE_SLOTS if slot not in booked_slots]


def match_slot(text: str, slots: list):
    text = text.lower().replace(" ", "")
    for slot in slots:
        time_part, ampm = slot.lower().split()
        hour, minute = time_part.split(":")
        h = str(int(hour))
        options = [h, h + ampm, f"{h}:{minute}", f"{h}:{minute}{ampm}", f"{hour}:{minute}{ampm}", f"{hour}:{minute}"]
        if text in options:
            return slot
    return None


def save_history(request: Request, user_message: str, reply: str):
    recent = request.session.get("recent_chat", "") + f"\nUser: {user_message}\nBot: {reply}"
    request.session["recent_chat"] = recent[-600:]



def suggest_doctor_reply(request: Request, db: Session, specialty: str, intro: str = "", user_message: str = ""):
    from chatbot.database.models import Doctor
    
    # Database se us specialty ke saare doctors nikalein
    doctors = db.query(Doctor).filter(Doctor.specialty.ilike(f"%{specialty}%")).all()
    
    # Agar specific doctor na mile, toh General OPD ke doctors le aayein
    if not doctors:
        doctors = db.query(Doctor).filter(Doctor.specialty.ilike("%General OPD%")).all()

    if not doctors:
        return "Abhi is specialty ke liye koi doctor available nahi hai."

    # Session me dynamic target doctors save karein (taaki 'ja' bolne par wahi Dermatologist/Specialist book ho)
    request.session["suggested_specialty"] = specialty
    request.session["suggested_doctors"] = [
        {"id": doc.doctor_id, "name": doc.doctor_name, "specialty": doc.specialty} 
        for doc in doctors
    ]

    # Dynamic Intro Logic (Symptom ke hisab se intro)
    if not intro:
        if "skin" in specialty.lower() or "derma" in specialty.lower():
            intro = (
                f"Skin allergy ya rash ke kaaran seasonal allergy, contact dermatitis, ya mild infection ho sakte hain.<br><br>"
                f"<b>Immediate Precautions:</b><br>"
                f"1. Affected area ko saaf aur dry rakhein, khujli karne se bachein.<br>"
                f"2. Kisi bhi harsh chemical ya scented soap ka use na karein.<br>"
                f"3. Halka thanda paani use karein aur doctor ki salah lein.<br><br>"
                f"Aapko <b>{specialty}</b> specialist ko dikhana chahiye. Yeh doctors available hain:<br><br>"
            )
        elif "gastro" in specialty.lower() or "stomach" in specialty.lower():
            intro = (
                f"Pet dard ya acidity ke kaaran indigestion, food infection, ya gas issue ho sakta hai.<br><br>"
                f"<b>Immediate Precautions:</b><br>"
                f"1. Halka aur kam masala wala khana khayein.<br>"
                f"2. Koshish karein ki zyada se zyada paani aur ORS peeyein.<br>"
                f"3. Oily aur fried khane se bachein.<br><br>"
                f"Aapko <b>{specialty}</b> specialist ko dikhana chahiye. Yeh doctors available hain:<br><br>"
            )
        else:
            intro = (
                f"In symptoms ke kaaran mild viral, dehydration ya seasonal issue ho sakta hai.<br><br>"
                f"<b>Immediate Precautions:</b><br>"
                f"1. Khoob paani peeyein aur hydration maintain karein.<br>"
                f"2. Aaram karein aur heavy physical exertion se bachein.<br>"
                f"3. Lakshan badhne par doctor ki salah se dawai lein.<br><br>"
                f"Aapko <b>{specialty}</b> specialist ko dikhana chahiye. Yeh doctors available hain:<br><br>"
            )

    response_html = intro
    for idx, doc in enumerate(doctors, 1):
        free_slots = get_free_slots(db, doc.doctor_id)
        slots_str = ', '.join(free_slots) if free_slots else "Saare slots book ho chuke hain"
        response_html += (
            f"<b>{idx}. {doc.doctor_name}</b> ({doc.specialty})<br>"
            f"🕒 Timing: {doc.timing}<br>"
            f"🟢 Free Slots: {slots_str}<br><br>"
        )
    
    response_html += "Appointment ke liye doctor ka naam aur upar diye gaye free slots me se time batayein."
    
    return response_html


async def ai_reply(request: Request, user_message: str, history: str):
    llm_data = await analyze_and_respond(user_message, history, already_booked=request.session.get("booked", False))
    return html.escape(llm_data.get("reply_text", "")).replace("\n", "<br>")


async def booking_step(request: Request, db: Session, user_id: int, user_message: str, pending: dict, history: str = ""):
    text = user_message.strip().lower()

    # FIX: Yahan exact match ki jagah 'in' check lagayein taaki 'booking cancel karo' bhi pakda jaye
    if "cancel" in text or "stop" in text:
        request.session.pop("pending_booking", None)
        request.session["booked"] = False
        
        # Optional: Agar database se bhi confirmed booking delete karni hai
        from chatbot.database.models import Booking
        last_booking = db.query(Booking).filter(Booking.user_id == user_id).order_by(Booking.booking_id.desc()).first()
        if last_booking:
            db.delete(last_booking)
            db.commit()
            
        return "Aapki appointment/booking cancel kar di gayi hai. Aapko aur kya sahayta chahiye?"

    if pending["stage"] == "ASK_TIME":
        free_slots = get_free_slots(db, pending["doctor_id"])
        slot = match_slot(text, free_slots)
        if not slot:
            reply_text = await ai_reply(request, user_message, history)
            # FIX: Yahan ai_reply ki jagah 'reply_text' variable use karein
            return f"{reply_text}<br><br>Appointment ke liye in free slots me se time batayein: {', '.join(free_slots)}"
        
        pending["stage"] = "ASK_CONFIRM"
        pending["slot"] = slot
        request.session["pending_booking"] = pending
        return f"<b>{pending['doctor_name']}</b> ke saath <b>{slot}</b> pe appointment book kar doon? (Yes / No)"

    if text in CONFIRM_WORDS:
        from chatbot.database.models import Booking
        if pending["slot"] not in get_free_slots(db, pending["doctor_id"]):
            pending["stage"] = "ASK_TIME"
            request.session["pending_booking"] = pending
            return f"Sorry, ye slot abhi kisi aur ne book kar liya. Free slots: {', '.join(get_free_slots(db, pending['doctor_id']))}. Dusra time batayein."
        db.add(Booking(
            user_id=user_id,
            doctor_id=pending["doctor_id"],
            booking_type=pending["booking_type"],
            slot_time=pending["slot"],
            booking_date=date.today()
        ))
        db.commit()
        request.session.pop("pending_booking", None)
        request.session["booked"] = True
        return (
            f" <b>Appointment Confirmed!</b><br>"
            f"<b>Doctor:</b> {pending['doctor_name']}<br>"
            f"<b>Slot:</b> {pending['slot']} ({date.today()})"
        )
    if text in NO_WORDS:
        pending["stage"] = "ASK_TIME"
        request.session["pending_booking"] = pending
        return "Theek hai, aapko kaunsa time chahiye?"

    reply_text = await ai_reply(request, user_message, history)
    # FIX: Yahan bhi ai_reply ki jagah 'reply_text' variable use karein
    return f"{reply_text}<br><br>Appointment book karne ke liye <b>Yes</b> ya <b>No</b> likhein."


async def smart_reply(request: Request, db: Session, user_message: str, history: str):
    """
    Suggestion-first reply for text AND voice:
      symptom      -> RAG suggestion (MCP tool) + doctor list + free slots
      appointment  -> doctor list + free slots
      anything else-> normal LLM answer (LLM can use the RAG / web_search MCP tools)
    If the MCP suggestion tool is unavailable, the old flow below runs unchanged.
    """
    sug = await fetch_suggestion(user_message)
    if sug:
        same_complaint = sug.get("specialty") == request.session.get("suggested_specialty")
        follow_up_question = bool(request.session.get("suggested_doctors")) and sug.get("is_question") and same_complaint
        if sug.get("intent") in ("SYMPTOM", "APPOINTMENT") and not follow_up_question:
            request.session["booked"] = False
            return suggest_doctor_reply(request, db, sug.get("specialty") or "General OPD", build_intro_html(sug))

    llm_data = await analyze_and_respond(user_message, history, already_booked=request.session.get("booked", False))
    if sug is None and llm_data.get("intent") == "SYMPTOM_CONSULT":   # old behaviour (MCP suggestion tool down)
        request.session["booked"] = False
        spec = llm_data.get("detected_specialty") or "General OPD"
        return suggest_doctor_reply(request, db, spec)
    return html.escape(llm_data.get("reply_text", "Namaste! Aapko kya problem ho rahi hai?")).replace("\n", "<br>")


def log_text_chat(request: Request, db: Session, user_id: int, user_message: str, reply: str):
    """Typed chats are saved here. Voice saves its own row (transcript, language, latency)."""
    if getattr(request.state, "channel", "text") == "text":
        save_chat_message(db, user_id, "text", user_message, reply)


@app.post("/api/chat")
@limiter.limit("15/minute")
async def chat_endpoint(request: Request, user_message: str = Form(...), db: Session = Depends(get_db)):
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"status": "error", "reply": "Pehle login kijiye."}

        msg_lower = user_message.strip().lower()

        # --- GLOBAL CANCELLATION FIX ---
        if "cancel" in msg_lower or "stop" in msg_lower or "booking cancel karo" in msg_lower:
            request.session.pop("pending_booking", None)
            request.session["booked"] = False
            
            # Database se user ki latest active booking delete karna optional hai
            from chatbot.database.models import Booking
            last_booking = db.query(Booking).filter(Booking.user_id == user_id).order_by(Booking.booking_id.desc()).first()
            if last_booking:
                db.delete(last_booking)
                db.commit()
                
            reply = "Aapki appointment/booking cancel kar di gayi hai. Aapko aur kya sahayta chahiye?"
            save_history(request, user_message, reply)
            log_text_chat(request, db, user_id, user_message, reply)
            return {"status": "success", "reply": reply}
        # -------------------------------

        if "history_context" not in request.session:
            summary = get_user_summary(user_id)
            request.session["history_context"] = summary.get("history_context", "")
        history = request.session["history_context"] + "\n" + request.session.get("recent_chat", "")

        pending = request.session.get("pending_booking")
        msg_lower = user_message.strip().lower()

        if pending:
            reply = await booking_step(request, db, user_id, user_message, pending, history)
        else:
            from chatbot.database.models import Doctor
            all_doctors = db.query(Doctor).all()
            matched_doc = None
            
            # Check if user typed a specific doctor's name
            for doc in all_doctors:
                if doc.doctor_name.lower() in msg_lower or (len(msg_lower) >= 4 and msg_lower in doc.doctor_name.lower()):
                    matched_doc = doc
                    break
            
            if matched_doc:
                free_slots = get_free_slots(db, matched_doc.doctor_id)
                request.session["pending_booking"] = {
                    "stage": "ASK_TIME",
                    "doctor_id": matched_doc.doctor_id,
                    "doctor_name": matched_doc.doctor_name,
                    "specialty": matched_doc.specialty,
                    "booking_type": "Consultation"
                }
                reply = f"Aapne <b>{matched_doc.doctor_name}</b> ({matched_doc.specialty}) ko chuna hai.<br>Appointment ke liye in free slots me se time batayein: {', '.join(free_slots)}"
            elif msg_lower in ["ja", "yes", "haan", "ha", "ok", "okay"]:
                # User agreed ('ja'), pick the first doctor from the suggested specialty list stored in session
                suggested_docs = request.session.get("suggested_doctors", [])
                if suggested_docs:
                    target_doc = suggested_docs[0] # Pehla doctor utha lo (jaise Dr. Rohan Gupta)
                    doc_obj = db.query(Doctor).filter(Doctor.doctor_id == target_doc["id"]).first()
                else:
                    doc_obj = db.query(Doctor).first()

                free_slots = get_free_slots(db, doc_obj.doctor_id)
                request.session["pending_booking"] = {
                    "stage": "ASK_TIME",
                    "doctor_id": doc_obj.doctor_id,
                    "doctor_name": doc_obj.doctor_name,
                    "specialty": doc_obj.specialty,
                    "booking_type": "Consultation"
                }
                reply = f"Aapne <b>{doc_obj.doctor_name}</b> ({doc_obj.specialty}) ko chuna hai.<br>Appointment ke liye in free slots me se time batayein: {', '.join(free_slots)}"
            else:
                reply = await smart_reply(request, db, user_message, history)

        save_history(request, user_message, reply)
        log_text_chat(request, db, user_id, user_message, reply)
        return {"status": "success", "reply": reply}

    except Exception as e:
        db.rollback()
        raise CustomException(e, sys)


@app.post("/api/chat-image")
async def chat_image_endpoint(request: Request, injury_image: UploadFile = File(...), db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        return {"status": "error", "reply": "Pehle login kijiye."}

    temp_path = None
    try:
        os.makedirs("temp", exist_ok=True)
        temp_path = os.path.join("temp", os.path.basename(injury_image.filename or "photo.jpg"))
        with open(temp_path, "wb") as f:
            f.write(await injury_image.read())

        data = analyze_injury_image(temp_path)

        intro = (
            f"📷 <b>Injury:</b> {html.escape(data['description'])}<br>"
            f"<b>Severity:</b> {data['severity']}<br>"
        )
        if data["category"] == "NORMAL":
            intro += "Ye normal injury hai, isliye General OPD doctor assign kiya gaya hai.<br>"
        else:
            intro += f"Ye specific injury hai, aapko <b>{data['specialty']}</b> ko dikhana chahiye.<br>"

        # Same MCP suggestion tool as text/voice: precautions from the RAG knowledge base
        sug = await fetch_suggestion(f"{data['description']} {data['body_part']}", specialty=data["specialty"])
        if sug:
            intro += "<br>" + build_precautions_html(sug)

        reply = suggest_doctor_reply(request, db, data["specialty"], intro)
        save_history(request, "[injury photo]", reply)
        save_chat_message(db, request.session.get("user_id"), "image", f"[injury photo] {data['description']}", reply)
        return {"status": "success", "reply": reply}

    except Exception as e:
        logger.error(f"Injury photo error: {e}")
        return {"status": "error", "reply": "Photo check nahi ho payi. Thodi der baad dobara try karein."}
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _ndjson(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


@app.post("/api/chat-voice")
@limiter.limit("15/minute")
async def chat_voice_endpoint(request: Request, audio: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Voice chat = same brain as /api/chat (suggestion -> doctors+slots -> Q&A -> book -> cancel).
    Only input (Sarvam STT) and output (Sarvam TTS) differ.
    Response is NDJSON stream: {"type":"text"} first (screen updates at once), then {"type":"audio"} chunks, then {"type":"done"}.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return {"status": "error", "reply": "Pehle login kijiye."}

    t0 = time.perf_counter()
    try:
        audio_bytes = await audio.read()
        if len(audio_bytes) < 1500:
            return {"status": "error", "reply": "Awaaz record nahi hui, kripya dobara bolein."}

        stt = await vh.speech_to_text(audio_bytes, audio.filename or "voice.wav", audio.content_type or "audio/wav")
        transcript = stt["transcript"]
        t_stt = time.perf_counter()
        if not transcript:
            return {"status": "error", "reply": "Awaaz samajh nahi aayi, kripya dobara bolein."}

        # Spoken words -> words the booking flow understands (yes/no/cancel/time/doctor name)
        pending = request.session.get("pending_booking")
        free = get_free_slots(db, pending["doctor_id"]) if pending and pending.get("stage") == "ASK_TIME" else []
        doctors = [(d.doctor_id, d.doctor_name) for d in db.query(Doctor).all()]
        flow_text = vh.canonicalize(transcript, pending, request.session.get("suggested_doctors", []), doctors, free)

        request.state.channel = "voice"   # chat_endpoint must not log this as a typed message
        result = await getattr(chat_endpoint, "__wrapped__", chat_endpoint)(request, user_message=flow_text, db=db)
        reply_html = result.get("reply", "")
        t_chat = time.perf_counter()

        lang = vh.tts_language(stt.get("language"))
        speech_text = vh.html_to_speech(reply_html)
        msg_id = save_chat_message(
            db, user_id, "voice", transcript, reply_html,
            language=stt.get("language"),
            audio_path=vh.save_voice_audio(user_id, audio_bytes, audio.filename),
            stt_ms=int((t_stt - t0) * 1000), chat_ms=int((t_chat - t_stt) * 1000),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Voice chat error: {e}")
        return {"status": "error", "reply": "Voice abhi kaam nahi kar raha, kripya text me likhiye."}

    async def stream():
        yield _ndjson({"type": "text", "status": "success", "transcript": transcript, "reply": reply_html, "language": lang})
        t_tts, first_ms = time.perf_counter(), None
        try:
            async for idx, b64 in vh.tts_stream(speech_text, lang):
                if first_ms is None:
                    first_ms = int((time.perf_counter() - t_tts) * 1000)
                yield _ndjson({"type": "audio", "index": idx, "mime": "audio/wav", "b64": b64})
        except Exception as e:
            logger.error(f"Voice TTS error: {e}")
            yield _ndjson({"type": "audio_error", "message": "Awaaz generate nahi ho payi, jawab screen par padh lijiye."})
        timing = {
            "stt_ms": int((t_stt - t0) * 1000),
            "chat_ms": int((t_chat - t_stt) * 1000),
            "tts_first_ms": first_ms,
            "total_to_first_audio_ms": int((t_chat - t0) * 1000) + (first_ms or 0),
        }
        logger.info(f"Voice timing: {timing}")
        yield _ndjson({"type": "done", "timing": timing})
        update_chat_timing(msg_id, tts_ms=first_ms, total_ms=timing["total_to_first_audio_ms"])

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/suggest-doctor")
async def doctor_suggestion_endpoint(symptom: str = Form(...)):
    try:
        return get_doctor_recommendation(disease=symptom)
    except Exception as e:
        print(f"Doctor Suggestion Error: {e}")
        return {"status": "error", "message": str(e)}


class BookingRequest(BaseModel):
    patient_name: str
    specialty: str
    doctor_details: str
    slot: str


@app.post("/book-appointment")
async def book_appointment(booking: BookingRequest):
    print(
        f"Booking Confirmed: {booking.patient_name} -> {booking.specialty} at"
        f" {booking.slot}"
    )
    return {
        "status": "success",
        "message": (
            f"Appointment Confirmed for {booking.patient_name}! Slot:"
            f" {booking.slot} ({booking.specialty})"
        ),
    }



###RAG Pipeline 
rag_pipeline = RAGPipeline() 

@app.get("/ask", response_class=HTMLResponse)
async def clinic_assistant_form(request:Request):
    logger.info("Clinic assistant(RAG) FORM page accessed...") 
    return templates.TemplateResponse(request, "clinic_assistant.html", {"result":None}) 

@app.post("/ask", response_class=HTMLResponse)
async def clinic_assitant_answer(request:Request, question:str=Form(...)):
    logger.info(f"Clinic assistant questino received: '{question}' ") 
    try:
        result = rag_pipeline.answer(question) 
        return templates.TemplateResponse(
            request,
            "clinic_assistant.html",
            {"result":result, 
             "form_data": {"question":question}, "error":None} 
        )
    except Exception as e:
        raise CustomException(e,sys) 


@app.get("/health")
async def health_check():
    logger.info("Health check endpoint accessed.")
    return {"status": "ok", "message": "Sanjeevani AI Clinic API active with MCP Server Integration."}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


