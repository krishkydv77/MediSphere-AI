import os 
import sys 
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__)  

def load_documents(source_dir: str):
    """
    Given directory se saari markdown (.md) files load karega
    aur documents list return karega.
    """
    try:
        documents = [] 
        for filename in sorted(os.listdir(source_dir)):
        
            if filename.endswith(".md"): 
                filepath = os.path.join(source_dir, filename) 
                with open(filepath, 'r', encoding='utf-8')as f: 
                    text = f.read()  
                documents.append({"source": filename, "text": text}) 
        logger.info(f"Laded {len(documents)} documents from {source_dir}")
        return documents 
    except Exception as e:
        raise CustomException(e,sys) 

def chunk_text(text:str, chunk_size: int , chunk_overlap:int):
    """
    Large text ko small chunks me break karega.
    """
    paragraphs = [p.strip() for p in text.split("\n\n")if p.strip()]
    chunks = [] 
    current_chunk = "" 
    for para in paragraphs: # Har paragraph ke liye loop
        if len(current_chunk) + len(para) <= chunk_size:
            current_chunk += ('\n\n' if current_chunk else "") + para 
        else:
            if current_chunk:
                chunks.append(current_chunk) 
            overlap_text = current_chunk[-chunk_overlap:] if current_chunk else "" # Overlap generate karo
            current_chunk = (overlap_text + "\n\n" + para).strip() # Naya chunk banao

    if current_chunk: # Last chunk chhoot na jaye
        chunks.append(current_chunk) 
    return chunks 


def build_chunks(source_dir: str , chunk_size: int , chunk_overlap:int):
    """
    Documents load karega
    aur unke chunks create karega.
    """
    try:
        documents = load_documents(source_dir)  # Saare documents load karo
        all_chunks = [] # Final chunks store honge
        for doc in documents:
            doc_chunks = chunk_text(doc['text'], chunk_size, chunk_overlap) # Chunk generation
            for i, chunk in enumerate(doc_chunks): # index + value return karta hai chunk ki
                all_chunks.append({
                    "source": doc['source'],
                    "chunk_id": i,
                    "text": chunk
                }) 

        logger.info(f"Built {len(all_chunks)} chunks from {len(documents)} documents.")
        return all_chunks 

    except Exception as e:
        raise CustomException(e,sys) 


if __name__ == "__main__":
    
    source_directory = "rag/knowledge_base"  
    chunks = build_chunks(source_directory, chunk_size=400, chunk_overlap=80)
    print(f"Total chunks built: {len(chunks)}")


