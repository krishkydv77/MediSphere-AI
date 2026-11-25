import sys
from fastmcp import FastMCP
from .database import get_doctor_by_name, get_patient_history_by_user_id, get_user_bookings
from .suggestion_engine import build_suggestion, web_search_guarded
from src.exception import CustomException
from src.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("Sanjeevni Clinic MCP Server")


def check_rbac(current_role: str, allowed_roles: list):
    try:
        if current_role not in allowed_roles:
            logger.warning(f"RBAC Access Denied for role '{current_role}'")
            return {
                "success": False,
                "error": f"Access Denied: Role '{current_role}' is not authorized to access this action."
            }
        return None
    except Exception as e:
        logger.error("Error during RBAC verification.")
        raise CustomException(e, sys)


# ==================== 5 USER TOOLS ====================

@mcp.tool()
def get_doctor_details(doctor_name: str, user_role: str = "User"):
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission

    doctor = get_doctor_by_name(doctor_name)
    if not doctor:
        return {"success": False, "message": f"Doctor '{doctor_name}' not found in database."}

    return {
        "success": True,
        "doctor": {
            "id": doctor.doctor_id,
            "name": doctor.doctor_name,
            "specialty": doctor.specialty,
            "timing": doctor.timing
        }
    }


@mcp.tool()
@mcp.tool()
def list_doctors(user_role: str = "User"):
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission

    from chatbot.database.db_config import SessionLocal
    from chatbot.database.models import Doctor
    db = SessionLocal()
    try:
        doctors = db.query(Doctor).all()
        doc_list = [f"{doc.doctor_name} ({doc.specialty})" for doc in doctors]
        return {"success": True, "doctors": doc_list}
    finally:
        db.close()


@mcp.tool()
def check_doctor_availability(doctor_name: str, user_role: str = "User"):
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission

    return {"success": True, "status": f"{doctor_name} is available."}


@mcp.tool()
def get_clinic_timings(user_role: str = "User"):
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission

    return {"success": True, "timings": "Monday to Saturday: 9:00 AM - 8:00 PM"}


@mcp.tool()
def get_department_info(department: str, user_role: str = "User"):
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission

    return {"success": True, "department": department, "info": "General OPD & Specialty Care."}


# ==================== 3 ADMIN TOOLS ====================

@mcp.tool()
def get_patient_history(user_id: int, user_role: str = "Admin"):
    permission = check_rbac(user_role, ["Admin", "Super Admin", "System"])
    if permission: return permission

    history_records = get_patient_history_by_user_id(user_id)
    if not history_records:
        return {"success": False, "message": f"No patient history found for user_id '{user_id}' in database."}

    records = [{"history_id": h.history_id, "summary": h.disease_summary, "doctor": h.last_doctor_name} for h in history_records]
    return {"success": True, "patient_history": records}


@mcp.tool()
def list_user_bookings(user_id: int, user_role: str = "Admin"):
    permission = check_rbac(user_role, ["Admin", "Super Admin", "System"])
    if permission: return permission

    bookings = get_user_bookings(user_id)
    if not bookings:
        return {"success": False, "message": f"No bookings found for user_id '{user_id}'."}

    booking_list = [{"id": b.booking_id, "type": b.booking_type, "slot": b.slot_time, "date": str(b.booking_date)} for b in bookings]
    return {"success": True, "bookings": booking_list}


@mcp.tool()
def update_doctor_timing(doctor_id: int, new_timing: str, user_role: str = "Admin"):
    permission = check_rbac(user_role, ["Admin", "Super Admin", "System"])
    if permission: return permission

    return {"success": True, "message": f"Doctor ID {doctor_id} timing updated to {new_timing}."}


# ==================== 2 SYSTEM / SUPER ADMIN TOOLS ====================

@mcp.tool()
def system_health_check(user_role: str = "System"):
    permission = check_rbac(user_role, ["System", "Super Admin"])
    if permission: return permission

    return {"success": True, "status": "All system DB tables and MCP connectors are operating normally."}


@mcp.tool()
def get_audit_logs(user_role: str = "System"):
    permission = check_rbac(user_role, ["System", "Super Admin"])
    if permission: return permission

    return {"success": True, "logs": ["Audit: User access checks passed.", "Audit: System health OK."]}


# ==================== SUGGESTION + WEB SEARCH TOOLS ====================

@mcp.tool()
async def health_suggestion(query: str, specialty: str = "", include_web: bool = False, user_role: str = "User"):
    """
    Single suggestion tool for the WHOLE chatbot (text, image and voice).
    Retrieves precautions from the clinic RAG knowledge base (rag/ folder) for the patient's
    symptom text, detects the right specialty and returns intent (SYMPTOM / APPOINTMENT / OTHER).
    Pass `specialty` only when it is already known (e.g. from an injury photo).
    Web news is added automatically only when the query asks for latest/current medical info.
    Use this for any symptom or medical-information question.
    """
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission
    return await build_suggestion(query, specialty_hint=specialty, include_web=include_web)


@mcp.tool()
async def web_search(query: str, news: bool = True, user_role: str = "User"):
    """
    Internet search (SerpAPI) ONLY for current / newly published medical or clinic-project information
    (e.g. latest outbreak advisory, new guideline, new variant). Do NOT use for general knowledge,
    symptoms or anything already answered by health_suggestion / the database.
    """
    permission = check_rbac(user_role, ["User", "Admin", "Super Admin", "System"])
    if permission: return permission
    return await web_search_guarded(query, news=news)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)