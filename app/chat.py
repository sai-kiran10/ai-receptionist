from fastapi import APIRouter
from app.schemas import ChatRequest
from app.llm import extract_intent
from app.services.slots import get_available_slots

router = APIRouter()

@router.post("/chat")
def chat(request: ChatRequest):
    intent = extract_intent(request.message)

    if intent["intent"] == "BOOK":
        if not intent["date"]:
            return {"reply": "Which date are you looking for?"}

        slots = get_available_slots(
            date=intent["date"],
            time_pref=intent["time_preference"]
        )

        if not slots:
            return {"reply": "No available slots for that time."}

        return {
            "reply": "Here are some available times.",
            "slots": slots
        }

    return {"reply": "I can help you book an appointment."}
