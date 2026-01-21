from fastapi import APIRouter, Depends
from app.services.bookings import HoldSlotRequest, ConfirmAppointmentRequest, hold_slot, confirm_appointment
from app.services.slots import get_available_slots
from app.services.gemini_service import GeminiService
from app.services.llm_interface import LLMInterface

router = APIRouter()

@router.post("/slots/hold")
def hold(request: HoldSlotRequest):
    return hold_slot(request)

@router.post("/appointments/confirm")
def confirm(request: ConfirmAppointmentRequest):
    return confirm_appointment(request)

@router.get("/slots")
def list_slots():
    return get_available_slots()

@router.post("/chat")
async def chat_with_receptionist(
    user_message: str,
    llm: LLMInterface = Depends(GeminiService)
):
    """
    This is the endpoint Twilio will call.
    It takes what the user says and lets LLM handle it.
    """
    response = llm.generate_response(user_message)
    return {"reply": response}