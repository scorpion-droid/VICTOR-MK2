import os
from google import genai
from google.genai import types
from google.genai.errors import APIError  
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def clean_image(image_path: str) -> str:
    img = Image.open(image_path)
    
    prompt = """You are a literal image-to-text transcription tool. 
Look at the handwritten image and write down exactly the mathematical symbols you see on each line.

CRITICAL RULES:
1. Do NOT solve a different math problem. 
2. Do NOT change the numbers to make the math "correct".
3. If the handwritten steps contain bad math, broken math, or illogical logic, you MUST transcribe that exact bad math.
4. Output EXACTLY what is written on the page, row by row.

Output format example:
line 1
line 2
line 3

Do not include any conversational text or markdown code fences."""

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[img, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
            )
        )
        return response.text
    
    except APIError as e:
        print (f"API Error: {e}")
        raise e