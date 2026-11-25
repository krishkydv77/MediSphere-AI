import os  
import sys 
from dataclasses import dataclass #ek shortcut hai class banane ke liye jisme automatic constructor milta hai. Config store karne ke liye use kiya. 
import numpy as np 
import pandas as pd 
from sklearn.compose import ColumnTransformer #alag-alag columns par alag preprocessing apply karne ke liye.
from sklearn.impute import SimpleImputer #missing values fill karne ke liye.
from sklearn.pipeline import Pipeline #steps ko chain karne ke liye.
from sklearn.preprocessing import OneHotEncoder , OrdinalEncoder 
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__) 
from src.utils import save_object #pickle file save karne ke liye.

@dataclass
class DataTransformationConfig: #Config class jisme preprocessor pickle file ka path store hai.
    preprocessor_obj_file_path: str =os.path.join("artifacts","preprocessor.pkl")

class DataTransformation:  #Ye main class hai jo preprocessing handle karegi. Constructor me config load ho raha hai.
    def __init__(self):
        self.data_transformation_config= DataTransformationConfig()

    def get_data_transformer_object(self):
        try:
            numerical_column = ['age','fever']
            ordinal_column = ['cough']
            onehot_columns= ['gender','city']
            #for fill numerical data
            num_pipeline= Pipeline(steps=[('impiter',SimpleImputer(strategy='mean'))]) #Numerical columns ke missing values ko mean se fill karega.
            #for categorical data
            ordinal_pipeline = Pipeline(steps=[
                (
                    "ordinal_encoder",
                    OrdinalEncoder(categories=[['Mild','Strong']])
                )
            ])
            ##gender,city-->onehot encoding
            onehot_pipeline=Pipeline(
                steps=[("onehot",OneHotEncoder(handle_unknown='ignore',sparse_output=False))]
            )
            preprocessor = ColumnTransformer(  #ColumnTransformer sab pipelines ko ek saath combine karta hai.
                transformers=[
                    ('num_pipeline',num_pipeline,numerical_column),
                    ('ordinal_pipeline',ordinal_pipeline,ordinal_column),
                    ('onehot_pipeline',onehot_pipeline,onehot_columns)
                ]
            )
            logger.info("preprocessor object created successfully!")
            return preprocessor
        except Exception as e:
            raise CustomException(e,sys)

    def initiate_data_transformation(self,train_path:str,test_path:str):
        try:
            train_df=pd.read_csv(train_path)
            test_df=pd.read_csv(test_path)
            logger.info("train and test data loaded for transformation")
            target_column="has_covid"
            input_feature_train_df = train_df.drop(columns=[target_column]) 
            target_feature_train_df = train_df[target_column].map({"Yes":1 , "No":0}) 

            input_feature_test_df = test_df.drop(columns=[target_column]) 
            target_feature_test_df = test_df[target_column].map({"Yes":1 , "No":0})

            preprocessor_obj = self.get_data_transformer_object()
            logger.info("Applying preprocessing on train and test data")
            input_feature_train_arr = preprocessor_obj.fit_transform(input_feature_train_df)
            input_feature_test_arr = preprocessor_obj.transform(input_feature_test_df)

            #Input features aur target ko combine karke final arrays banaye.
            train_arr = np.c_[input_feature_train_arr, np.array(target_feature_train_df)]
            test_arr = np.c_[input_feature_test_arr, np.array(target_feature_test_df)]

            save_object( #Preprocessor ko pickle file me save kiya.
                file_path=self.data_transformation_config.preprocessor_obj_file_path,
                obj = preprocessor_obj
                )
            logger.info("Preprcoessor object saved as preprocessor.pkl")

            #Final output return kiya: train array, test array, aur pickle path.
            return(train_arr,test_arr,self.data_transformation_config.preprocessor_obj_file_path)

    
        except Exception as e:
            raise CustomException(e,sys)


if __name__ == "__main__":  #Agar script direct run ho to DataTransformation object banega aur train/test data transform hoga.
    obj = DataTransformation()   #Access methods and configs
    obj.initiate_data_transformation('artifacts/train.csv', 'artifacts/test.csv')



'''
#dynamic:-
def get_data_transformer_object(self, df: pd.DataFrame):
    try:
        # Auto detect columns
        numerical_columns = df.select_dtypes(include=['int64','float64']).columns.tolist()
        categorical_columns = df.select_dtypes(include=['object']).columns.tolist()

        # Agar cough ko ordinal treat karna hai
        ordinal_columns = ['cough'] if 'cough' in categorical_columns else []
        onehot_columns = [col for col in categorical_columns if col not in ordinal_columns]

        # Pipelines
        num_pipeline = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='mean'))
        ])

        ordinal_pipeline = Pipeline(steps=[
            ('ordinal_encoder', OrdinalEncoder(categories=[['Mild','Strong']]))
        ])

        onehot_pipeline = Pipeline(steps=[
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
        ])

        # ColumnTransformer
        preprocessor = ColumnTransformer(
            transformers=[
                ('num_pipeline', num_pipeline, numerical_columns),
                ('ordinal_pipeline', ordinal_pipeline, ordinal_columns),
                ('onehot_pipeline', onehot_pipeline, onehot_columns)
            ]
        )

        logger.info("Dynamic preprocessor object created successfully!")
        return preprocessor

    except Exception as e:
        raise CustomException(e, sys)
        '''

