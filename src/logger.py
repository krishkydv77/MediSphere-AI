##logger library inbuit hoti ha 
import logging
import os # logs every file ke respect nikalege to hame system ka configration dena hoga iske OS
from datetime import datetime

# folder creation 
LOGS_DIR=os.path.join(os.getcwd(),"logs") #os.path.join(...) path add karna, and  kha os.getcwd() → Current Working Directory 
os.makedirs(LOGS_DIR,exist_ok=True) #exist_ok=True → if folder ha to skip ,nhi ha to bana dega but error nhi dega 


# log file creation
LOG_FILE = f"{datetime.now().strftime('%m_%d_%Y_%H_%M_%S')}.log"
LOG_FILE_PATH = os.path.join(LOGS_DIR,LOG_FILE)


logging.basicConfig(
    filename = LOG_FILE_PATH,
    format="[%(asctime)s] %(lineno)d %(name)s -%(levelname)s -%(message)s",
    level=logging.INFO #to INFO aur usse upar ke levels (WARNING, ERROR, CRITICAL) capture honge. DEBUG level ke logs ignore ho jaenge.
)

def get_logger(name:str= __name__):
    logger=logging.getLogger(name) # logging module se ek logger object banaya jata hai, jiska naam 'name' hoga,function call karte ho get_logger(__name__), to logger ka naam us file ka module name hoga

    if not logger.handlers:  # agar is logger ke paas abhi koi handler nahi hai, tab naya handler add karenge
        console_handler=logging.StreamHandler()  # ek StreamHandler banaya jo console (terminal) par log print karega
        console_handler.setLevel(logging.INFO) # handler ka level INFO set kiya, matlab INFO aur usse upar ke logs (WARNING, ERROR, CRITICAL) console par print honge.
        formatter=logging.Formatter(
           "[%(asctime)s] %(lineno)d %(name)s -%(levelname)s -%(message)s" 
        # ek formatter banaya jo log ka format define karega:
        # asctime = time stamp, lineno = line number, name = logger ka naam,
        # levelname = log level (INFO, ERROR, etc.), message = actual log message
        )
        console_handler.setFormatter(formatter) # formatter ko handler ke saath attach kiya,Ab handler jab log print karega to ye format follow karega.
        logger.addHandler(console_handler) # handler ko logger ke saath attach kiya, ab logger console par output dega,Matlab ab logger ke through jo bhi log generate hoga, wo console par formatted output dega.
    return logger

if __name__=="__main__":
      # Ye condition check karti hai ki file direct run ho rahi hai ya import ki gayi hai.
    # Agar file ko direct run karoge (python logger.py), to __name__ ka value "__main__" hoga.
    # Agar file ko kisi aur module me import karoge, to __name__ us module ka naam hoga.
    # Iska fayda: test code ya initialization sirf tab chalega jab file direct run ho, 
    # import karne par nahi chalega.
    log=get_logger(__name__)
    # Yaha tum apna custom logger object bana rahe ho.
    # get_logger function ko call kiya gaya jisme __name__ pass kiya.
    # Matlab logger ka naam us module/file ke naam ke equal hoga.
    # Agar file direct run ho rahi hai to logger ka naam "__main__" set hoga.
    log.info("logger test message- logs start successfully")
    # Ye ek INFO level ka log message generate karega.
    # Message console par print hoga (agar console handler attached hai) 
    # aur file me bhi save hoga (agar file handler attached hai).
    # Output me tumhe timestamp, line number, logger name, log level aur message sab dikhega.


