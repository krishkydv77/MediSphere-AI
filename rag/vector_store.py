import os 
import sys 
import faiss # FAISS (Facebook AI Similarity Search) Large vector search aur similarity matching ke liye use hoti hai
import numpy as np 
from sklearn.feature_extraction.text import TfidfVectorizer # Text ko numerical vectors me convert karne ke liye TF-IDF use karte hain

from src.exception import CustomException 
from src.logger import get_logger 
from src.utils import load_object, save_object 
logger = get_logger(__name__) 

class VectorStore:
     """
    Ye class vector database build aur load karne ke liye hai.
    RAG pipeline me chunks ko vector me convert karke
    FAISS index me store karti hai.
    """
     def __init__(self, config:dict):
        """
        Constructor

        config dictionary receive karta hai
        aur vector_store section ko store karta hai.
        """
        self.config = config['vector_store'] 

     def build(self, chunks:list):
         """
        Chunks ko vector me convert karke
        FAISS index build karta hai.
        """
         logger.info("RAG STAGE: VECTOR STORE BUILD STARTED....") 

         try:
            texts = [c['text'] for c in chunks] # Har chunk dictionary se text extract kar rahe hain
            vectorizer = TfidfVectorizer(max_features=1000, stop_words='english') # Sirf top 1000 important words consider honge # stop_words='english' a, an, the, is jaise common words ignore honge
            tfidf_matrix = vectorizer.fit_transform(texts).toarray().astype('float32') # toarray() sparse matrix ko dense numpy array me badalta hai ,astype('float32') FAISS float32 format expect karta hai
            faiss.normalize_L2(tfidf_matrix)  # Vectors ko normalize kar rahe hain , Taaki cosine similarity effectively work kare
            dimension = tfidf_matrix.shape[1]  # Vector dimension nikal rahe hain (feature=1000=dimension)
            index = faiss.IndexFlatIP(dimension) # Inner Product ≈ Cosine Similarity
            index.add(tfidf_matrix) # Saare vectors index me add kar do

            os.makedirs(os.path.dirname(self.config['faiss_index_path']), exist_ok=True) 
            faiss.write_index(index, self.config['faiss_index_path']) # FAISS index disk par save karo
            save_object(self.config['vectorizer_path'], vectorizer)  # TF-IDF vectorizer save karo
            save_object(self.config['chunks_metadata_path'], chunks) # Chunks metadata save karo
            logger.info(
                f"Vector store built: {len(chunks)} chunks," 
                f"{dimension}--dim TF-IDF vectors"
                f"FAISS IndexFlatIP saved at"
                f"{self.config['faiss_index_path']}"
            )
            logger.info(f"-----------RAG STAGE: VECTOR STORE BUILD COMPLETED----------") 

         except Exception as e:
            raise CustomException(e,sys) 

     def load(self):
        """
        Saved vector store ko load karta hai.
        """
        try:
            vectorizer = load_object(self.config['vectorizer_path']) # Saved vectorizer load karo 
            index = faiss.read_index(self.config['faiss_index_path']) # Saved FAISS index load karo
            chunks = load_object(self.config['chunks_metadata_path']) # Saved chunks metadata load karo
            return vectorizer, index, chunks # Teeno objects return kar do
        except  Exception as e:
            raise CustomException(e,sys) 



