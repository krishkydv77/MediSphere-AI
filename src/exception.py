import sys #error traceback (exc_info),# exc_info() se ham error type, error object or traceback milta hai.
from src.logger import get_logger
logger= get_logger(__name__) # __name__ se logger ka naam current module ke naam ke equal ho jata hai.

def error_message_detail(error,error_detail:sys):
    # error → actual exception object
    # error_detail → sys module (jisse hum exc_info() call karte hain)
    _,_,exc_tb=error_detail.exc_info() #exc_info() ek tuple deta hai (type, value, traceback). ham traceback (exc_tb) extract karte hain jo error ke location batata hai.
    file_name= exc_tb.tb_frame.f_code.co_filename # traceback object se us file ka naam milta hai jisme error hua.
    line_number = exc_tb.tb_lineno #traceback object se us line number ka pata chalta hai jahan error hua.
    error_message = ( #Ek formatted string banayi hai jisme file name, line number aur error ka text hoga.
        f"Error occure in python script:[{file_name}]"
        f"at line number:[{line_number}]"
        f"with error message: [{str(error)}]"
    )
    return error_message #detailed error message return karega.
class CustomException(Exception): #project me error handling ko professional aur detailed banane ke liye hota hai.
    def __init__(self,error_message,error_detail:sys):
        super().__init__(error_message) #Base Exception class ko initialize kiya.(atribute form)
        self.error_message=error_message_detail(error_message, error_detail=error_detail) #error_message_detail function call karke detailed error message generate kiya.
        logger.error(self.error_message) #Logger ke through error message ko console/file me log kar diya.

    def __str__(self):
        return self.error_message #Jab tum exception ko print karoge to ye detailed error message return karega.
    
