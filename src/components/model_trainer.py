import os 
import sys 
from dataclasses import dataclass 
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression 
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier 
import pandas as pd 
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__) 
from src.utils import evaluate_models, load_object, save_object 

@dataclass 
class ModelTrainerConfig:
    trained_model_file_path: str = os.path.join("artifacts", "model.pkl") 
    # Dataclass banayi jo trained model ka file path store karegi (default artifacts/model.pkl)

class ModelTrainer:
    def __init__(self):
        self.model_trainer_config = ModelTrainerConfig() # Constructor me config object initialize kiya
    def initiate_model_trainer(self, train_array , test_array):
        try:
            logger.info("Spliting train and test input data") # Log message: ab train aur test data split kar rahe hain
            X_train,y_train, X_test , y_test = (
                train_array[:, :-1], # Train features (last column ke alawa sab)
                train_array[:, -1], ## Train labels (last column)
                test_array[:, :-1], ## Test features
                test_array[:, -1] ## Test labels
            )
            # Different models ka dictionary banaya
            models = {
                "LogisiticRegression": LogisticRegression(max_iter=100),
                "DecisionTree": DecisionTreeClassifier(random_state=42),
                "RandomForest":RandomForestClassifier(random_state=42, n_estimators=50),
                "KNeighboursClassifier":KNeighborsClassifier(n_neighbors=5) 
            }

            # Models evaluate karne ke liye utility function call kiya
            model_report: dict = evaluate_models(
                X_train, y_train , X_test , y_test,models
            )

            # Best model ka score aur naam nikalna
            best_model_score = max(model_report.values()) 
            best_model_name = max(model_report, key= model_report.get) 
            best_model = models[best_model_name] 
            logger.info(f"Best Model saved as model.pkl ::: {best_model_name}")
            # Log message: best model select ho gaya
            # 
            #  Best model ko pickle file me save karna
            save_object(
             file_path=self.model_trainer_config.trained_model_file_path,obj=best_model)
            logger.info(f"Best Model saved: {best_model_name}") 
            # Log message: model successfully save ho gaya


            return best_model_name, best_model_score
        # Best model ka naam aur score return karna

            
        except Exception as e :
            raise CustomException(e,sys)
        # Agar error aaya toh custom exception raise karna 