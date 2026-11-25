import sys  
import faiss  
import numpy as np  
from src.exception import CustomException  
from src.logger import get_logger  
from rag.vector_store import VectorStore  
logger = get_logger(__name__)  

class Retriever:    
    def __init__(self, config:dict):        
      try:
        self.config = config['retrieval']  
        self.vector_store = VectorStore(config)  
        self.vectorizer , self.index, self.chunks = self.vector_store.load()  
        logger.info(f"Retriever ready with {len(self.chunks)} indexed chunks")  
      except Exception as e :
          raise CustomException(e,sys)
    def retrieve(self, query:str):        
        try:           
            top_k = self.config['top_k']  
            min_similarity = self.config['min_similarity']  
            top_k = min(top_k, len(self.chunks))
            query_vec = self.vectorizer.transform([query]).toarray().astype('float32')  
            if np.count_nonzero(query_vec) == 0:
                logger.warning(
                    f"No vocabulary match found for query: {query}")
            faiss.normalize_L2(query_vec)  
            scores, indices = self.index.search(query_vec, top_k)  # FAISS index par search run kar rahe hain jo query vector ke sabse close top-k vectors ke 'scores' (similarity distance) aur unke 'indices' (positions) return karta hai.
            logger.info(f"Scores: {scores}")
            logger.info(f"Indices: {indices}")
            results = []  # Ek empty list bana rahe hain jisme final filtered aur formatted retrieved chunks ko store kiya jayega.
            
            for score, idx in zip(scores[0], indices[0]):  
                if idx == -1 or score < min_similarity:  
                    continue  
                
                chunk = self.chunks[idx]  
                logger.info(f"Retrieved Chunk Keys: {list(chunk.keys())}")
                results.append({  
                    "text": chunk['text'],  
                    "source": chunk['source'],  
                    "chunkid": chunk['chunk_id'],  
                    "score": round(float(score),4)  
                 })  
            logger.info(f"Retrieved {len(results)} chunks for query: '{query}' ")  
            return results  
                
        except Exception as e: 
            raise CustomException(e,sys)  