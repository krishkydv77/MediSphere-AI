import os
import sys
import asyncio

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from src.logger import get_logger
from src.exception import CustomException

logger = get_logger(__name__)

try:
    from medical_mcp.ai_agent import ask_agent
    logger.info("Successfully imported ask_agent from medical_mcp.ai_agent")
except Exception as e:
    logger.error(f"Failed to import ask_agent: {e}")
    raise CustomException(e, sys)


async def analyze_and_respond(user_message: str, history: str = "", already_booked: bool = False) -> dict:
    """
    Async implementation with enhanced dynamic specialty detection.
    """
    logger.info(f"analyze_and_respond called :: Message: '{user_message}' | Already Booked: {already_booked}")
    try:
        prompt = f"Chat History:\n{history}\n\nUser Question: {user_message}"
        
        logger.info("Executing ask_agent from medical_mcp...")
        res = await ask_agent(prompt, user_role="User")

        response_text = ""
        if res is None:
            response_text = "Namaste! Main aapki kya madad kar sakta hoon?"
        elif isinstance(res, dict):
            # Check for 'answer' key safely
            response_text = res.get("answer")
            if not response_text:
                # Agar 'answer' key nahi hai, toh dictionary ke kisi bhi text value ko utha lo ya string bana do
                response_text = str(res)
        else:
            response_text = str(res)

        logger.info(f"Response received from ask_agent: {response_text[:100]}...")

        # 1. Symptom & Health Keywords
        symptom_keywords = [
            "dard", "pain", "fever", "bukhar", "pet", "stomach", "headache", 
            "cough", "khansi", "infection", "vomiting", "symptoms", "sick", "ill", "current", "gardan"
        ]
        
        # 2. Specialty Mapping Keywords
        specialties = [
            "Neurologist", "Orthopedic", "Cardiologist", "Dermatologist", 
            "General OPD", "Pediatrician", "Gastroenterologist", "Psychiatrist"
        ]
        
        has_symptom = any(kw in user_message.lower() for kw in symptom_keywords)
        detected_specialty = None

        # Pehle agent ke response me check karein ki kaunsi specialty mention ki gayi hai
        for spec in specialties:
            if spec.lower() in response_text.lower():
                detected_specialty = spec
                break

        # Agar response me nahi mili, toh user message ke keywords ke hisab se set karein
        # Agar response me specialty nahi mili, toh user message ke keywords ke hisab se set karein
        if not detected_specialty:
            user_msg_lower = user_message.lower()

            # Cardiology
            if any(word in user_msg_lower for word in [
                "heart", "chest pain", "seene", "dil", "bp",
                "blood pressure", "palpitation", "heartbeat"
            ]):
                detected_specialty = "Cardiologist"

            # Neurology
            elif any(word in user_msg_lower for word in [
                "headache", "migraine", "dizziness", "seizure",
                "fits", "nerve", "current", "gardan",
                "numbness", "memory", "brain"
            ]):
                detected_specialty = "Neurologist"

            # Gastroenterology
            elif any(word in user_msg_lower for word in [
                "pet", "stomach", "acidity", "gas",
                "digestion", "constipation", "vomiting",
                "diarrhea", "liver"
            ]):
                detected_specialty = "Gastroenterologist"

            # Orthopedic
            elif any(word in user_msg_lower for word in [
                "haddi", "bone", "joint", "knee",
                "back pain", "fracture", "injury",
                "shoulder", "arthritis"
            ]):
                detected_specialty = "Orthopedic"

            # Dermatology
            elif any(word in user_msg_lower for word in [
                "skin", "rash", "pimple", "acne",
                "itching", "allergy", "fungal"
            ]):
                detected_specialty = "Dermatologist"

            # ENT
            elif any(word in user_msg_lower for word in [
                "ear", "nose", "throat", "kaan",
                "naak", "gala", "tonsil", "sinus"
            ]):
                detected_specialty = "ENT Specialist"

            # Eye
            elif any(word in user_msg_lower for word in [
                "eye", "vision", "aankh",
                "blur", "glasses"
            ]):
                detected_specialty = "Ophthalmologist"

            # Gynecology
            elif any(word in user_msg_lower for word in [
                "pregnancy", "period", "menstrual",
                "women", "delivery", "pcod", "pcos"
            ]):
                detected_specialty = "Gynecologist"

            # Pediatrics
            elif any(word in user_msg_lower for word in [
                "baby", "child", "kid", "vaccination",
                "newborn", "infant"
            ]):
                detected_specialty = "Pediatrician"

            # Psychiatry
            elif any(word in user_msg_lower for word in [
                "depression", "anxiety", "stress",
                "mental", "panic", "sleep problem"
            ]):
                detected_specialty = "Psychiatrist"

            # Pulmonology
            elif any(word in user_msg_lower for word in [
                "cough", "asthma", "breathing",
                "lungs", "saans", "tb"
            ]):
                detected_specialty = "Pulmonologist"

            # Urology
            elif any(word in user_msg_lower for word in [
                "urine", "kidney stone", "bladder",
                "prostate", "burning urine"
            ]):
                detected_specialty = "Urologist"

            # Endocrinology
            elif any(word in user_msg_lower for word in [
                "diabetes", "thyroid", "hormone",
                "sugar"
            ]):
                detected_specialty = "Endocrinologist"

            else:
                specialties = ["General OPD","General Physician","Cardiologist","Neurologist","Gastroenterologist","Orthopedic","Dermatologist","ENT Specialist","Ophthalmologist","Gynecologist","Pediatrician","Psychiatrist","Pulmonologist","Urologist","Endocrinologist","Nephrologist","Oncologist","Rheumatologist","Hematologist","Radiologist","Physiotherapist"]
                for spec in specialties:
                    if spec.lower() in response_text.lower():
                        detected_specialty = spec
                        break
                if not detected_specialty:
                        detected_specialty = "General OPD"

        # Trigger SYMPTOM_CONSULT agar booking nahi hui hai
        if not already_booked:
            logger.info(f"Detected Specialty: '{detected_specialty}'. Intent set to SYMPTOM_CONSULT.")
            return {
                "intent": "SYMPTOM_CONSULT",
                "detected_specialty": detected_specialty,
                "reply_text": response_text
            }
        
        logger.info("Intent set to CASUAL.")
        return {
            "intent": "CASUAL",
            "reply_text": response_text
        }

    except Exception as e:
        logger.error(f"Error in analyze_and_respond: {str(e)}")
        custom_exc = CustomException(e, sys)
        logger.error(f"CustomException Details: {custom_exc}")
        return {
            "intent": "CASUAL",
            "reply_text": f"Namaste! Main aapki kya madad kar sakta hoon? (Note: {str(e)})"
        }

async def get_llm_response(prompt: str) -> str:
    logger.info("get_llm_response called.")
    try:
        res = await ask_agent(prompt, user_role="User")
        return res.get("answer", str(res)) if isinstance(res, dict) else str(res)
    except Exception as e:
        logger.error(f"Error in get_llm_response: {str(e)}")
        raise CustomException(e, sys)