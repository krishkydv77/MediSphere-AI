import sys
from sqlalchemy.orm import Session
from chatbot.database.db_config import SessionLocal, engine
from chatbot.database.models import Base, User, PatientHistory, Doctor, Booking
from src.exception import CustomException
from src.logger import get_logger

logger = get_logger(__name__)


def init_db():
    try:
        logger.info("Initializing database tables using SQLAlchemy models...")
        Base.metadata.create_all(bind=engine)
        
        session = SessionLocal()
        # Initial Doctors sample data
        if session.query(Doctor).count() == 0:
            logger.info("Inserting initial sample data for doctors...")
            session.add_all([
                Doctor(doctor_id=1, doctor_name="Dr. Sharma", specialty="General OPD", timing="10 AM - 2 PM"),
                Doctor(doctor_id=2, doctor_name="Dr. Mehta", specialty="Gastroenterologist", timing="4 PM - 8 PM"),
                Doctor(doctor_id=3, doctor_name="Dr. Sharma", specialty="Cardiologist", timing="9 AM - 1 PM"),
                Doctor(doctor_id=4, doctor_name="Dr. Gupta", specialty="Dermatologist", timing="10 AM - 2 PM"),
                Doctor(doctor_id=5, doctor_name="Dr. Verma", specialty="Orthopedic", timing="11 AM - 3 PM"),
                Doctor(doctor_id=6, doctor_name="Dr. Singh", specialty="Neurologist", timing="2 PM - 6 PM"),
                Doctor(doctor_id=7, doctor_name="Dr. Patel", specialty="Pediatrician", timing="9 AM - 12 PM"),
                Doctor(doctor_id=8, doctor_name="Dr. Reddy", specialty="ENT Specialist", timing="3 PM - 7 PM"),
                Doctor(doctor_id=9, doctor_name="Dr. Nair", specialty="Ophthalmologist", timing="10 AM - 4 PM"),
                Doctor(doctor_id=10, doctor_name="Dr. Joshi", specialty="Psychiatrist", timing="1 PM - 5 PM"),
                Doctor(doctor_id=11, doctor_name="Dr. Chawla", specialty="Urologist", timing="4 PM - 8 PM"),
                Doctor(doctor_id=12, doctor_name="Dr. Kapoor", specialty="Gynecologist", timing="9 AM - 1 PM"),
                Doctor(doctor_id=13, doctor_name="Dr. Malhotra", specialty="Endocrinologist", timing="11 AM - 4 PM"),
                Doctor(doctor_id=14, doctor_name="Dr. Iyer", specialty="Nephrologist", timing="2 PM - 6 PM"),
                Doctor(doctor_id=15, doctor_name="Dr. Saxena", specialty="Pulmonologist", timing="10 AM - 2 PM"),
                Doctor(doctor_id=16, doctor_name="Dr. Khanna", specialty="Oncologist", timing="1 PM - 5 PM"),
                Doctor(doctor_id=17, doctor_name="Dr. Arora", specialty="Rheumatologist", timing="3 PM - 7 PM"),
                Doctor(doctor_id=18, doctor_name="Dr. Bansal", specialty="General Physician", timing="9 AM - 5 PM"),
                Doctor(doctor_id=19, doctor_name="Dr. Aggarwal", specialty="Radiologist", timing="10 AM - 3 PM"),
                Doctor(doctor_id=20, doctor_name="Dr. Sethi", specialty="Physiotherapist", timing="8 AM - 12 PM"),
                Doctor(doctor_id=21, doctor_name="Dr. Desai", specialty="Hematologist", timing="2 PM - 6 PM")
            ])
            session.commit()

        # Initial Users sample data
        if session.query(User).count() == 0:
            logger.info("Inserting initial sample data for users...")
            session.add_all([
                User(user_id=1, name="Mohit", email="mohit@example.com", password="hashed_password_1"),
                User(user_id=2, name="Priya Verma", email="priya@example.com", password="hashed_password_2")
            ])
            session.commit()

        session.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error("Error occurred while initializing database.")
        raise CustomException(e, sys)


def get_doctor_by_name(name: str):
    session = SessionLocal()
    try:
        doctor = session.query(Doctor).filter(Doctor.doctor_name.ilike(f"%{name}%")).first()
        return doctor
    except Exception as e:
        logger.error(f"Error fetching doctor details for {name}")
        raise CustomException(e, sys)
    finally:
        session.close()


def get_patient_history_by_user_id(user_id: int):
    session = SessionLocal()
    try:
        history = session.query(PatientHistory).filter(PatientHistory.user_id == user_id).all()
        return history
    except Exception as e:
        logger.error(f"Error fetching patient history for user_id: {user_id}")
        raise CustomException(e, sys)
    finally:
        session.close()


def get_user_bookings(user_id: int):
    session = SessionLocal()
    try:
        bookings = session.query(Booking).filter(Booking.user_id == user_id).all()
        return bookings
    except Exception as e:
        logger.error(f"Error fetching bookings for user_id: {user_id}")
        raise CustomException(e, sys)
    finally:
        session.close()