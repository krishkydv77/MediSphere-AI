import sys
from sqlalchemy import text
from chatbot.database.db_config import SessionLocal
from src.exception import CustomException
from src.logger import get_logger
logger = get_logger(__name__)

def insert_dummy_data():
    db = SessionLocal()
    try:
        queries = [
            """
            INSERT INTO users (user_id, name, email, password) 
            VALUES (1, 'abhi', 'abhi@gmail.com', 'password123')
            ON DUPLICATE KEY UPDATE name=VALUES(name);
            """,
            """
            INSERT INTO patient_history (user_id, disease_summary, last_doctor_name)
            VALUES (1, 'Stomach Ulcer (Severe acidity & stomach pain)', 'Dr. Mehta')
            ON DUPLICATE KEY UPDATE disease_summary=VALUES(disease_summary);
            """,
            """
            
            INSERT INTO doctors (doctor_id, doctor_name, specialty, timing)VALUES
    (1, 'Dr. Mehta', 'Gastroenterologist', '09:00 AM - 01:00 PM'),
    (2, 'Dr. Rajesh Sharma', 'Neurologist', '10:00 AM - 02:00 PM'),
    (3, 'Dr. Anjali Mehta', 'General OPD', '09:00 AM - 05:00 PM'),
    (4, 'Dr. Vikram Verma', 'General OPD', '11:00 AM - 07:00 PM'),
    (5, 'Dr. Priya Nair', 'Orthopedic', '08:00 AM - 12:00 PM'),
    (6, 'Dr. Rohan Gupta', 'Dermatologist', '02:00 PM - 06:00 PM'),
    (7, 'Dr. Amit Patel', 'Cardiologist', '09:00 AM - 01:00 PM'),
    (8, 'Dr. Neha Kapoor', 'Gynecologist', '10:00 AM - 02:00 PM'),
    (9, 'Dr. Suresh Reddy', 'ENT Specialist', '11:00 AM - 03:00 PM'),
    (10, 'Dr. Kavita Joshi', 'Pediatrician', '09:00 AM - 01:00 PM'),
    (11, 'Dr. Manoj Singh', 'Urologist', '02:00 PM - 06:00 PM'),
    (12, 'Dr. Pooja Agarwal', 'Ophthalmologist', '10:00 AM - 02:00 PM'),
    (13, 'Dr. Arvind Saxena', 'Psychiatrist', '01:00 PM - 05:00 PM'),
    (14, 'Dr. Sneha Khanna', 'Endocrinologist', '09:00 AM - 01:00 PM'),
    (15, 'Dr. Nitin Bansal', 'Pulmonologist', '03:00 PM - 07:00 PM'),
    (16, 'Dr. Rashmi Iyer', 'Nephrologist', '10:00 AM - 02:00 PM'),
    (17, 'Dr. Sanjay Chawla', 'Oncologist', '01:00 PM - 05:00 PM'),
    (18, 'Dr. Deepak Malhotra', 'Rheumatologist', '11:00 AM - 03:00 PM'),
    (19, 'Dr. Shalini Desai', 'Hematologist', '09:00 AM - 01:00 PM'),
    (20, 'Dr. Vivek Arora', 'General Physician', '09:00 AM - 05:00 PM'),
    (21, 'Dr. Harish Kumar', 'Cardiologist', '09:00 AM - 01:00 PM'),
    (22, 'Dr. Reena Malhotra', 'Gynecologist', '10:00 AM - 02:00 PM'),
    (23, 'Dr. Aditya Sharma', 'Pediatrician', '09:00 AM - 01:00 PM'),
    (24, 'Dr. Kiran Patel', 'Dermatologist', '02:00 PM - 06:00 PM'),
    (25, 'Dr. Mohit Verma', 'Orthopedic', '11:00 AM - 03:00 PM'),
    (26, 'Dr. Snehal Deshmukh', 'Neurologist', '01:00 PM - 05:00 PM'),
    (27, 'Dr. Rakesh Gupta', 'ENT Specialist', '10:00 AM - 02:00 PM'),
    (28, 'Dr. Sonali Kapoor', 'General OPD', '09:00 AM - 05:00 PM'),
    (29, 'Dr. Vivek Sinha', 'Psychiatrist', '12:00 PM - 04:00 PM'),
    (30, 'Dr. Nidhi Jain', 'Ophthalmologist', '08:00 AM - 12:00 PM'),
    (31, 'Dr. Ashok Bansal', 'Urologist', '03:00 PM - 07:00 PM'),
    (32, 'Dr. Pankaj Arora', 'Nephrologist', '09:00 AM - 01:00 PM'),
    (33, 'Dr. Meenal Joshi', 'Endocrinologist', '10:00 AM - 02:00 PM'),
    (34, 'Dr. Rohit Chawla', 'Pulmonologist', '01:00 PM - 05:00 PM'),
    (35, 'Dr. Aarti Singh', 'Oncologist', '11:00 AM - 03:00 PM'),
    (36, 'Dr. Kapil Aggarwal', 'General Physician', '09:00 AM - 05:00 PM'),
    (37, 'Dr. Swati Nair', 'Rheumatologist', '02:00 PM - 06:00 PM'),
    (38, 'Dr. Manish Yadav', 'Hematologist', '10:00 AM - 02:00 PM'),
    (39, 'Dr. Charu Mehta', 'Gastroenterologist', '03:00 PM - 07:00 PM'),
    (40, 'Dr. Anupam Saxena', 'Cardiologist', '08:00 AM - 12:00 PM')

ON DUPLICATE KEY UPDATE
    specialty = VALUES(specialty),
    timing = VALUES(timing);
            """
        ]
        for query in queries:
            db.execute(text(query))
        db.commit()
        logger.info("Dummy data inserted into database successfully.")
        
    except Exception as e:
        db.rollback() 
        raise CustomException(e, sys)
    finally:
        db.close()

if __name__ == "__main__":
    insert_dummy_data()