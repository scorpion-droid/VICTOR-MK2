import os
from google import genai
from google.genai.errors import APIError  # <-- Make sure this is imported exactly like this
from dotenv import load_dotenv

load_dotenv()

# Setup your client using the correct environment variable
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def clean_noisy_ocr(raw_ocr_lines: list[str]) -> str:
    raw_text = "\n".join(raw_ocr_lines)
    
    prompt = f"""You are an advanced mathematical OCR data cleaner. Your task is to clean noisy, fragmented, or out-of-order text lines produced by an OCR engine reading handwritten algebra problem steps. Output ONLY valid, cleaned, logical math lines in standard format, with one step per line. Do not include markdown code block syntax (like ```), and do not include explanatory text.
    
Noisy OCR lines to clean:
{raw_text}"""

    # First attempt: Use the flagship model
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )
        return response.text
    except APIError as e:
        # If it's a 503 or any other API breakdown, swap to a highly available fallback
        print(f"Primary model hit a snag (Status {e.code}). Shifting to fallback...")
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text
        except Exception as fallback_error:
            # Pass it back up to the UI if even the backup fails
            raise fallback_error