import google.genai as genai
import os
from dotenv import load_dotenv
from .llm_interface import LLMInterface
from app.services.slots import get_available_slots
from app.services.bookings import hold_slot, confirm_appointment      

load_dotenv()

RECEPTIONIST_INSTRUCTIONS = """
You are a professional appointment scheduling assistant.
Your goal is to help users with the following intents: 
BOOK, CONFIRM, CANCEL, and ASK_AVAILABILITY.

Rules:
1. To check availability, call 'get_available_slots'.
2. To start a booking, call 'hold_slot'.
3. To finalize, call 'confirm_appointment'.
4. If a user's intent is UNKNOWN, ask clarifying questions politely.
5. Do not make up information; always use the provided tools.
"""

class GeminiService(LLMInterface):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
            
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"

    def generate_response(self, prompt: str) -> str:
        # The calling syntax is also slightly different in the new SDK
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config={
                'tools': [get_available_slots, hold_slot, confirm_appointment],
                'system_instruction': "You are a professional receptionist for The Tech Clinic. Use the tools provided to manage bookings."
            }
        )
        return response.text