import os
import google.genai as genai
from dotenv import load_dotenv
from .llm_interface import LLMInterface
from app.services.slots import get_available_slots
from app.services.bookings import hold_slot, confirm_appointment, cancel_appointment, reschedule_appointment, get_appointments_by_phone     

load_dotenv()

class GeminiService(LLMInterface):
    # CLASS-LEVEL ATTRIBUTE: This persists in the server's memory across all API calls.
    # It allows the AI to "remember" Sid and the previous context.
    _chat_history = []

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
            
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"

    def generate_response(self, prompt: str) -> str:
        # 1. Create a chat session using the persistent class history
        # Using start_chat (or chats.create) is what enables "memory"
        chat = self.client.chats.create(
            model=self.model_id,
            config={
                'tools': [get_available_slots, hold_slot, confirm_appointment, cancel_appointment, reschedule_appointment, get_appointments_by_phone],
                'system_instruction': (
                    "You are a professional appointment scheduling assistant for The Tech Clinic. "
                    "You MUST remember details provided by the user (like their name, phone number, and chosen date/time) "
                    "throughout the conversation. If they mention a time once, do not ask for it again.\n\n"
                    "Workflow:\n"
                    "1. Check availability with 'get_available_slots'.\n"
                    "2. When a time is picked, call 'hold_slot'.\n"
                    "3. Ask for final confirmation, then call 'confirm_appointment'.\n"
                    "If a user wants to cancel or check an appointment but doesn't have an ID, "
                    "ask for their phone number and use 'get_appointments_by_phone' to find it. "
                    "Once found, confirm with the user before calling 'cancel_appointment'."
                )
            },
            history=GeminiService._chat_history
        )

        # 2. Send the message within the stateful chat session
        response = chat.send_message(prompt)

        # 3. Update the class-level history so the NEXT request knows what happened in this one
        GeminiService._chat_history = chat.get_history()

        # Handle cases where the model might return a tool call result instead of plain text
        if response.text:
            return response.text
        else:
            return "I've processed that request for you. What else can I help with?"

    @classmethod
    def clear_history(cls):
        """Helper method to reset the AI's memory (useful for testing)."""
        cls._chat_history = []