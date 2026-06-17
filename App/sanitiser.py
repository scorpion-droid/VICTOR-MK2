import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / '.env'

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    raise FileNotFoundError(f"Could not find your .env file at: {ENV_PATH}")

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        f"Found .env at {ENV_PATH}, but 'GEMINI_API_KEY' is missing or empty inside it!"
    )

client = genai.Client(api_key=api_key)

def clean_noisy_ocr(raw_ocr_lines: list[str]) -> str:
    """
    Sends raw OCR lines to Gemini to sanitize math and handle unreadable areas.
    """
    raw_text = "\n".join(raw_ocr_lines)
    
    prompt = f"""
    You are a mathematical text analyzer. I have raw, messy OCR output from a 
    student's handwritten math homework. 
    
    Your task:
    1. Reconstruct the intended math equations.
    2. If a line terminates or contains a '?', it means the physical writing was blurry or unreadable. 
       Preserve the '?' symbol exactly in your output line. Do NOT try to guess or fill in the blanks.
    3. Output ONLY the clean, standard algebraic equations (one per line).
    4. Do not solve the equations.
    
    Raw OCR Output:
    {raw_text}
    """
    
    response = client.models.generate_content(
        model="gemini-3.5-flash", 
        contents=prompt
    )
    
    return response.text


