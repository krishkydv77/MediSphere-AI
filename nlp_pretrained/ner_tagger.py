import sys 
from nltk import ne_chunk, pos_tag , word_tokenize
# word_tokenize → text ko words me todta hai (tokenization)
# pos_tag → har token ka Part-of-Speech (noun, verb, etc.) assign karta hai
# ne_chunk → POS tagged words se Named Entity Recognition (NER) karta hai 
from src.exception import CustomException 
from src.logger import get_logger 
logger = get_logger(__name__) 

# Apple is in London ---> if I perform NER ---> (Apple= 'Orgam=nization') , ('London' = GPE (Location))

def get_pos_tags(text:str):
    try:
        tokens = word_tokenize(text) #  Input text ko tokenize karte hain → words ki list ban jaati hai.         
        return pos_tag(tokens) ## Har token ka POS tag assign karke return karte hain.
    except Exception as e :
        raise CustomException(e, sys) 

def extract_entities(text:str):
    try:
        tagged = get_pos_tags(text) # Pehle text ke tokens ke POS tags nikalte hain.
        tree = ne_chunk(tagged) # POS tagged words se NER tree banate hain (chunked parse tree). 
        entities = {"GPE":[] , "PERSON": [] , "ORGANIZATION":[]} # Ek dictionary banayi jisme teen categories store karenge
        for i in tree:
            if hasattr(i, "label"):
                #hasattr(object, attribute) → Python ka built‑in function hai jo check karta hai ki kisi object ke andar given attribute exist karta hai ya nahi.
                label = i.label() # Entity ka type (PERSON, GPE, ORGANIZATION)
                entity_text = " ".join(word for word, _ in i) # Entity ke words ko join karke ek string banayi
                #_ ka use kiya gaya hai POS tag ko ignore karne ke liye
                if label in entities:
                    entities[label].append(entity_text) # Agar label dictionary me hai to us list me entity add kar di.
        logger.info(f"NLTK pretrained NER extracted from '{text}' : {entities}") ## Logging: extracted entities ko info level pe log karte hain.
        return entities  # Entities dictionary return karte hain.

    except Exception as e :
        raise CustomException(e,sys) 