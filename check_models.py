import os
from google import genai
from dotenv import load_dotenv
load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options={'api_version': 'v1alpha'}
)

for model in client.models.list():
    if "live" in model.name.lower() or "native-audio" in model.name.lower():
        print(model.name)