import os
import sys
from dataclasses import dataclass #decorator hai jo simple classes banane me help karta hai.automatically __init__, __repr__ jaise methods generate kar deta hai.
import pandas as pd
from sklearn.model_selection import train_test_split
from src.exception import CustomException
from src.logger import get_logger
logger=get_logger(__name__)

@dataclass
class DataIngestionConfig:
    raw_data_path: str = os.path.join("artifacts","raw.csv") #Raw data ko save karne ka path define
    train_data_path: str = os.path.join("artifacts","train.csv") #Train dataset save karne ka path.
    test_data_path: str = os.path.join("artifacts","test.csv") #Test dataset save karne ka path.
    source_csv_path: str = os.path.join("notebook","data","covid_toy.csv") #Source CSV file ka path jahan se data read hoga.

class DataIngestion:
    def __init__(self):
        self.ingestion_config=DataIngestionConfig() #Config object initialize kiya jisme paths defined h


    def initiate_data_ingestion(self):
         # initiate_data_ingestion() method call kiya jo:
    # 1. CSV read karega
    # 2. raw.csv save karega
    # 3. train-test split karega
    # 4. train.csv aur test.csv save karega
    # 5. aur unke paths return karega
        logger.info("data Ingestion start---->")
        try:
            df=pd.read_csv(self.ingestion_config.source_csv_path)
            logger.info(f"data read successfull with shape: {df.shape}")
            os.makedirs( #Raw data ke directory ko create kiya agar exist nahi karti.
                os.path.dirname(self.ingestion_config.raw_data_path),exist_ok=True
            )
            df.to_csv(self.ingestion_config.raw_data_path,index=False,header=True) #Raw data ko artifacts/raw.csv me save
            logger.info("Performing train-test-split")
            train_set, test_set = train_test_split(
                df , test_size=0.2, random_state=42 , stratify=df['has_covid']
            )
            
            train_set.to_csv(self.ingestion_config.train_data_path, index=False, header=True) 
            test_set.to_csv(self.ingestion_config.test_data_path, index=False, header=True) 
            logger.info("Data Ingestion completed successfully...")
            return { #Function train aur test file paths return karta h
                self.ingestion_config.train_data_path,
                self.ingestion_config.test_data_path
            }
        except Exception as e:
            raise CustomException(e,sys)

if __name__ == "__main__":
    obj = DataIngestion()  #DataIngestion class ka object
    obj.initiate_data_ingestion() #Data ingestion process start kiya
    

