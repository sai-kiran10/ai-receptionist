import os
import google.genai as genai
from dotenv import load_dotenv
from .llm_interface import LLMInterface
from app.services.slots import get_available_slots
from app.services.bookings import hold_slot, confirm_appointment, cancel_appointment, reschedule_appointment, get_appointments_by_phone     
from datetime import datetime

load_dotenv()


class GeminiService(LLMInterface):
    # It allows the AI to remember previous context.
    _chat_history = []

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
            
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash"

    def generate_response(self, prompt: str) -> str:
        #Create a chat session using the persistent class history
        # Using start_chat (or chats.create) is what enables "memory"
        today_date = datetime.now().strftime("%Y-%m-%d")
        chat = self.client.chats.create(
            model=self.model_id,
            config={
                'tools': [get_available_slots, hold_slot, confirm_appointment, cancel_appointment, reschedule_appointment, get_appointments_by_phone],
                'system_instruction': (
                    f"You are a professional appointment scheduling assistant for The Tech Clinic. Today's date is {today_date}."
                    f"Always call get_available_slots at the start of a scheduling conversation so you have the correct slot_ids" 
                    f"in your memory. If the user doesn't specify a date, use today's date ({today_date}). When a user picks a time, map it to the corresponding slot_id and call hold_slot immediately."
                    "You MUST remember details provided by the user (like their name, phone number, and chosen date/time) "
                    "throughout the conversation. If they mention a time once, do not ask for it again.\n"
                    "If the user provides a date and time, you must internalize it and" 
                    "map it to the available slot_id format (YYYY-MM-DD-HH:MM)." 
                    "Do not ask the user to use a specific format; translate their natural language (e.g., 'Tomorrow at 3') into the correct ID yourself.\n\n"
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

        #Send the message within the stateful chat session
        response = chat.send_message(prompt)

        #Update the class-level history so the NEXT request knows what happened in this one
        GeminiService._chat_history = chat.get_history()

        #Handle cases where the model might return a tool call result instead of plain text
        if response.text:
            return response.text
        else:
            return "I've processed that request for you. What else can I help with?"

    @classmethod
    def clear_history(cls):
        """Helper method to reset the AI's memory (useful for testing)."""
        cls._chat_history = []