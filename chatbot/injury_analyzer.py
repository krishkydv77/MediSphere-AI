import os
import sys
from PIL import Image
from dotenv import load_dotenv
import google.generativeai as genai
from src.exception import CustomException

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def analyze_injury_image(image_path: str):
    """Photo dekh kar batata hai: injury kya hai, kitni severe hai, kaunsa specialist chahiye."""
    try:
        img = Image.open(image_path).convert("RGB")   # PNG/WEBP bhi chalega
        prompt = """
        Look at this injury/medical photo. Reply in exactly 4 lines:
        1. One short sentence describing the injury.
        2. Severity: exactly one word - Minor, Moderate or Severe.
        3. Specialty: exactly one from - General OPD, Orthopedic, Dermatologist.
           Use Orthopedic for bone/joint/muscle injuries (knee, ankle, fracture, sprain, swelling), even if the skin is also hurt.
           Use Dermatologist for skin problems (rash, burn, infection). Use General OPD only for small cuts and scrapes.
        4. Body part: one or two words (example: knee, hand, eye).
        """

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content([prompt, img])
        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError(f"Gemini ne jawab nahi diya: {response.prompt_feedback}")

        # 3 lines alag-alag karo (kam lines aayi to khaali string se bhar do)
        lines = [l.strip() for l in response.text.splitlines() if l.strip()]
        lines = lines + ["", "", "", ""]

        description = lines[0].removeprefix("1.").strip()
        severity_line = lines[1].lower()
        specialty_line = lines[2].lower()

        body_part = lines[3].split(":")[-1].strip()

        # Severity
        if "severe" in severity_line:
            severity = "Severe"
        elif "moderate" in severity_line:
            severity = "Moderate"
        else:
            severity = "Minor"

        # Specialty (jo LLM ne bataya wahi lo)
        if "orthopedic" in specialty_line:
            specialty = "Orthopedic"
        elif "dermatologist" in specialty_line:
            specialty = "Dermatologist"
        else:
            specialty = "General OPD"

        category = "NORMAL" if specialty == "General OPD" else "SPECIFIC"

        return {
            "status": "success",
            "description": description,
            "severity": severity,
            "body_part": body_part,
            "specialty": specialty,
            "category": category,
        }

    except Exception as e:
        raise CustomException(e, sys)


if __name__ == "__main__":
    test_path = "static/test.jpg"
    if os.path.exists(test_path):
        print(analyze_injury_image(test_path))
    else:
        print(f"File not found: {test_path}")