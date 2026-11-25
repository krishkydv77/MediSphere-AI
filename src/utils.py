import os
import sys
import pickle #ek Python library hai jo objects ko binary format me save/load karne ke liye use hoti hai.
from sklearn.metrics import accuracy_score #ek sklearn function hai jo model ke predictions aur actual labels compare karke accuracy calculate karta hai.
from src.exception import CustomException
from src.logger import get_logger
logger =get_logger(__name__)

def save_object(file_path:str,obj):
    try:
        dir_path=os.path.dirname(file_path) #file_path se directory ka path nikalte hain.
        os.makedirs(dir_path,exist_ok=True) #Agar directory exist nahi karti to create kar dete ha varna skip karo
        with open(file_path,"wb") as file_obj: #Object ko binary mode me file ke andar save kar dete hain using pickle.
            pickle.dump(obj,file_obj)
        logger.info(f"Object saved successfully at: {file_path}")
    except Exception as e:
        raise CustomException(e,sys)

def load_object(file_path:str):
    try:
        with open(file_path,"rb") as file_obj:
            return pickle.load(file_obj)
    except Exception as e:
        raise CustomException (e,sys)

def evaluate_models(x_train,y_train,x_test,y_test,models:dict):
    try:
        report={} #empty dictionary banayi jisme har model ka accuracy store hoga.
        for model_name,model in models.items():
            model.fit(x_train,y_train)
            y_pred=model.predict(x_test)
            test_accuracy=accuracy_score(y_test,y_pred)
            report[model_name] = test_accuracy
            logger.info(f"{model_name} -> test Accuracy :{test_accuracy:.2f}")
        return report #dictionary return hoti hai jisme sab models ki accuracy hogi.
    except Exception as e:
        raise CustomException(e,sys)