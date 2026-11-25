import sys
from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey, TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from chatbot.database.db_config import Base, engine
from src.logger import get_logger
from src.exception import CustomException

logger = get_logger(__name__)


# 1. User Table (Login & Session ke liye)
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)

    # Relationships
    history = relationship("PatientHistory", back_populates="user")
    bookings = relationship("Booking", back_populates="user")


# 2. Patient History Table (Mohit ka Stomach pain & Doctor Suresh Summary)
class PatientHistory(Base):
    __tablename__ = "patient_history"

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    disease_summary = Column(Text, nullable=False)
    last_doctor_name = Column(String(100), nullable=True)

    user = relationship("User", back_populates="history")


# 3. Doctor Table (Doctor Selection & Availability)
class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_name = Column(String(100), nullable=False)
    specialty = Column(String(100), nullable=False)  # e.g., Neurologist, Gastroenterologist, General OPD
    timing = Column(String(100), nullable=True)

    bookings = relationship("Booking", back_populates="doctor")


# 4. Booking Table (Slot Booking Details)
class Booking(Base):
    __tablename__ = "bookings"

    booking_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.doctor_id"), nullable=False)
    booking_type = Column(String(50), nullable=False)  # 'OPD' ya 'Specialist'
    slot_time = Column(String(50), nullable=False)
    booking_date = Column(Date, nullable=False)

    user = relationship("User", back_populates="bookings")
    doctor = relationship("Doctor", back_populates="bookings")

# 5. Admin Table (Super Admin / Admin users details)
class Admin(Base):
    __tablename__ = "admins"

    admin_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), default="Admin", nullable=False)  # FIXED NAME
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(50), default="Admin", nullable=False)  # 'Admin' or 'Super Admin'
    created_at = Column(TIMESTAMP, server_default=func.now())


# 6. System User / Agent Credentials Table (Admin dvara create kiye gaye System Accounts)
class SystemUser(Base):
    __tablename__ = "system_users"

    system_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id_code = Column(String(50), unique=True, nullable=False)  # e.g., SYS_MONITOR_01
    password = Column(String(255), nullable=False)
    description = Column(String(255), nullable=True)  # e.g., MCP Connector / Health Monitor
    created_by_admin_id = Column(Integer, ForeignKey("admins.admin_id"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


# 7. Chat Messages (text / image / voice - ek hi table me, taaki sab data saath rahe)
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    channel = Column(String(10), nullable=False)       # 'text' | 'image' | 'voice'
    user_text = Column(Text, nullable=True)            # typed text / voice transcript / "[injury photo] ..."
    bot_reply = Column(Text, nullable=True)            # plain-text reply
    language = Column(String(16), nullable=True)       # voice: detected language (hi-IN, en-IN ...)
    audio_path = Column(String(255), nullable=True)    # voice: saved audio file (only if SAVE_VOICE_AUDIO=true)
    stt_ms = Column(Integer, nullable=True)            # voice latency breakdown
    chat_ms = Column(Integer, nullable=True)
    tts_ms = Column(Integer, nullable=True)            # time to FIRST audio chunk
    total_ms = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Db tables initialized successfully")
    except Exception as e:
        logger.error("Error creating database tables.")
        raise CustomException(e, sys)


if __name__ == "__main__":
    init_db()