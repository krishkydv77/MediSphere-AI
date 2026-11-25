import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from src.logger import get_logger
from src.exception import CustomException

load_dotenv()
logger = get_logger(__name__)

# Fetch database credentials from .env
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD").replace("@", "%40")
DB_NAME = os.getenv("DB_NAME")

# Construct MySQL SQLAlchemy Connection URL
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    logger.info("SQLAlchemy Engine successfully connected.")
except Exception as e:
    logger.error("Failed to initialize Database Engine.")
    raise CustomException(e, sys)


def get_db():
    """
    Dependency helper function to get DB sessions in FastAPI routes
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT DATABASE();"))
            db_name = result.scalar()
            logger.info(f"Database connection verified! Connected to database: {db_name}")
            print(f" Successfully connected to database: {db_name}")
            return db_name
    except Exception as e:
        logger.error("Database connection test failed.")
        print(" Database Connection Failed!")
        raise CustomException(e, sys)


if __name__ == "__main__":
    test_connection()