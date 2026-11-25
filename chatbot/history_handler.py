import sys
from sqlalchemy.orm import Session
from chatbot.database.db_config import SessionLocal
from chatbot.database.models import User, PatientHistory
from src.logger import get_logger
from src.exception import CustomException

logger = get_logger(__name__)

def get_user_summary(user_id: int):
    # 1. Database connection chalu karo
    db = SessionLocal()
    
    try:
        # 2. Database se User ko dhoondho uski ID se
        user = db.query(User).filter(User.user_id == user_id).first()
        
        # Agar user nahi mila toh yahin se bahar nikal jao (Guest data dekar)
        if user == None:
            logger.warning(f"No user found with user_id: {user_id}")
            return {"user_name": "Guest", "history_context": "No past medical history available."}

        # 3. Agar user mil gaya, toh uski sabse nayi (latest) medical history dhoondho
        history = db.query(PatientHistory).filter(PatientHistory.user_id == user_id).order_by(PatientHistory.history_id.desc()).first()

        # 4. Check karo ki history mili ya nahi, aur text taiyar karo
        if history != None:
            # Agar history mili toh details daal do
            context = f"Patient Name: {user.name}. Past Disease: {history.disease_summary}. Doctor: {history.last_doctor_name}."
        else:
            # Agar history nahi mili toh simple text daal do
            context = f"Patient Name: {user.name}. No previous medical history recorded."

        # 5. Log print karo aur final result return karo
        logger.info(f"Successfully retrieved history for user_id {user_id}")
        
        result = {
            "user_id": user.user_id,
            "user_name": user.name,
            "history_context": context
        }
        return result

    except Exception as e:
        raise CustomException(e, sys)
        
    finally:
        db.close()

# --- CODE KO CHALAKAR DEKHNE KE LIYE ---
if __name__ == "__main__":
    data = get_user_summary(user_id=1)
    print(data)
