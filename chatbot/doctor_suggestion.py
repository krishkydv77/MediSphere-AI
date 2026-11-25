import sys
from sqlalchemy.orm import Session
from chatbot.database.db_config import SessionLocal
from chatbot.database.models import Doctor
from src.logger import get_logger
from src.exception import CustomException
logger = get_logger(__name__)

# def get_doctor_recommendation(disease: str):
#     db = SessionLocal()
#     try:
#         # 2. Database mein specialty search karo (ilike matlab matching search)
#         doctor = db.query(Doctor).filter(Doctor.specialty.ilike(f"%{disease}%")).first()
#         if doctor == None:
#             logger.info(f"No specific doctor found for '{disease}'. Fetching General OPD.")
#             doctor = db.query(Doctor).filter(Doctor.specialty.ilike("%General OPD%")).first()

#         if doctor == None:
#             result = {
#                 "status": "not_found",
#                 "message": "No doctor available "
#             }
#             return result

#         logger.info(f"Recommended doctor: {doctor.doctor_name} for specialty: {doctor.specialty}")

#         text = f"According to symptoms {doctor.doctor_name} ({doctor.specialty}) recommend you to consult them.  available slots: 10:00 AM - 11:30 AM, 02:00 PM - 03:30 PM, aur 05:00 PM - 06:30 PM."

#         result = {
#             "status": "success",
#             "doctor_id": doctor.doctor_id,  
#             "doctor_name": doctor.doctor_name,
#             "specialty": doctor.specialty,
#             "recommendation_text": text
#         }
#         return result

#     except Exception as e:
#         raise CustomException(e, sys)
#     finally:
#         db.close()

def get_doctor_recommendation(disease: str):
    db = SessionLocal()
    try:
        doctor = db.query(Doctor).filter(Doctor.specialty.ilike(f"%{disease}%")).all()
        if not doctor:
            doctor = db.query(Doctor).filter(Doctor.specialty.ilike("%General OPD%")).all()

        if not doctor:
            return {"status": "not_found", "message": "No doctor available"}

        doc_list = []
        for doc in doctor:
            doc_list.append({
                "doctor_id": doc.doctor_id,
                "doctor_name": doc.doctor_name,
                "specialty": doc.specialty,
                "timing": doc.timing
            })

        return {
            "status": "success",
            "doctor_id": doctor.doctor_id,  
            "doctor_name": doctor.doctor_name,
            "specialty": doctor.specialty,
            # "recommendation_text": text
        }
    except Exception as e:
        raise CustomException(e, sys)
    finally:
        db.close()

if __name__ == "__main__":
    print("--- Test 1 ---")
    res1 = get_doctor_recommendation("Gastroenterologist")
    print(res1)

    
