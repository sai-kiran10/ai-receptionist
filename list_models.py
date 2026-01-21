from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Checking available models...")
try:
    for model in client.models.list():
        # Just print the name for now to see the exact string
        print(f" - {model.name}")
except Exception as e:
    print(f"Error: {e}")