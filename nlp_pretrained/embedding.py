# Text ---> Machine understand Numbers ---> (TF-IDF, GLOVE, GENSIM, FASTTEXT), Advance(huggingface transformer(All-minilm-l6-v2), googlegenerativeembeddings, openaiembeddings) 

# Text ---> Machine understand Numbers ---> (TF-IDF, GLOVE, GENSIM, FASTTEXT), 
# Advance(huggingface transformer(All-minilm-l6-v2), googlegenerativeembeddings, openaiembeddings) 
#  Comment: Text ko machine samajhne ke liye usse numbers (embeddings/vectors) me convert karna padta hai.
# Basic methods: TF-IDF, GloVe, FastText, Gensim
# Advanced methods: HuggingFace Transformers, Google Generative Embeddings, OpenAI Embeddings
import sys 
import gensim.downloader as api # Gensim ka downloader import kiya → pretrained models (jaise GloVe, Word2Vec) ko load karne ke liye.
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__) 

_model = None # Global variable `_model` → initially None, baad me pretrained embeddings model store karega.
MODEL_NAME = "glove-wiki-gigaword-50" # Pretrained model ka naam define kiya → GloVe embeddings (50 dimensions).

def _get_model():
    global _model  # Global variable `_model` ko access karne ke liye declare kiya.
    if _model is None: # Agar model abhi load nahi hua hai (None hai)
        logger.info(f"Loading pretrained Model for Embeddings: {MODEL_NAME}") 
        _model= api.load(MODEL_NAME) # Gensim downloader se pretrained GloVe model load kar liya.
        logger.info(f"Embeddings Loaded , Vocabulary size: {len(_model.index_to_key)}") # Log message: embeddings load ho gaye + vocabulary size print kiya.
    return _model 

def most_similar_words(word:str , topn: int=5):
    try:
        model = _get_model() # Pretrained model ko load kiya.
        word = word.lower() # Word ko lowercase me convert kiya (case-insensitive matching ke liye).
        if word not in model: # Agar word vocabulary me nahi hai
            logger.info(f" '{word}' was not found in voucabulary.")
            return []
        results = model.most_similar(word, topn=topn)  # Gensim ka function -> given word ke topn most similar words return karta hai.
        logger.info(f"Most Similar to '{word}' : '{results}'")
        return results 
    except Exception as e:
        raise CustomException(e,sys)  

def word_similarity(word1:str , word2: str):
    try:
        model = _get_model() 
        score = float(model.similarity(word1.lower() , word2.lower())) # Do words ke beech similarity score calculate kiya (cosine similarity).
        logger.info(f"Similarity('{word1}', '{word2}') = {score:.3f}") 
        return score 
    except Exception as e :
        raise CustomException(e,sys) 