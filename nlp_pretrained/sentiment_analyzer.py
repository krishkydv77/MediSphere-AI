# Text ---> polarity score ---> decide setence behaviour(po,neg, neutral) 
#  Matlab: Text ko analyze karke ek polarity score nikala jata hai.
# Compound score ke basis pe decide hota hai ki sentence positive, negative ya neutral hai.
import sys 
from nltk.sentiment import SentimentIntensityAnalyzer # NLTK ka VADER sentiment analyzer import kiya -> text ke sentiment (positive/negative/neutral) detect karne ke liye.
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__) 
_analyzer = None # Global variable `_analyzer` -> initially None, baad me SentimentIntensityAnalyzer object store karega.

def _get_analyzer():
    global _analyzer # Global variable `_analyzer` ko access karne ke liye declare kiya.
    if _analyzer is None: # Agar analyzer abhi load nahi hua hai (None hai)
        _analyzer = SentimentIntensityAnalyzer() 
    return _analyzer 

def analyze_sentiment(text: str):
    try:
        sia = _get_analyzer() # Pretrained sentiment analyzer ko load kiya.
        scores = sia.polarity_scores(text)  # Text ka sentiment score nikala (dictionary return hoti hai: pos, neg, neu, compound)
        if scores["compound"] <= -0.5: # Agar compound score -0.5 ya usse kam hai -> bahut negative -> High urgency.
            urgency_hint = "High" 
        elif scores["compound"] <=  -0.15: # Agar compound score -0.15 tak hai -> thoda negative -> Medium urgency.
            urgency_hint = "Medium"
        else: # Agar compound score -0.15 se upar hai -> neutral ya positive -> Low urgency.
            urgency_hint = "Low" 

        result = {**scores , "urgency_hint": urgency_hint} #Ye ek dictionary unpacking syntax
        logger.info(f"VADER sentiment for '{text}' : {result}") 
        return result 
    except Exception as e :
        raise CustomException(e,sys)  
 