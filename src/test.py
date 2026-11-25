import sys  
# sys module import kiya, error details lene ke liye.

from src.exception import CustomException  
# Tumhari banayi hui CustomException class ko import kiya.

def read_file(file_path):
    try:
        with open(file_path, "r") as f:
            data = f.read()
            return data
    except Exception as e:
        # Agar file nahi milti ya koi aur error aata hai,
        # to CustomException raise hoga.
        raise CustomException(e, sys)

if __name__ == "__main__":
    print("Testing CustomException with FileNotFoundError...")

    try:
        #  Intentionally ek non‑existent file open kar rahe hain.
        content = read_file("non_existing_file.txt")
        print("File Content:", content)
    except CustomException as ce:
        #  Jab CustomException raise hoga, to ye block usko catch karega.
        print("Caught CustomException:")
        print(ce)   #  Ye tumhara detailed error message print karega.
