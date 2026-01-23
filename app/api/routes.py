from fastapi import APIRouter, Depends, Form, Response
from app.services.bookings import HoldSlotRequest, ConfirmAppointmentRequest, hold_slot, confirm_appointment
from app.services.slots import get_available_slots
from app.services.gemini_service import GeminiService
from app.services.llm_interface import LLMInterface
from twilio.twiml.messaging_response import MessagingResponse

router = APIRouter()
llm = GeminiService()

@router.post("/slots/hold")
def hold(request: HoldSlotRequest):
    return hold_slot(slot_id=request.slot_id, 
                     phone_number=request.phone_number,
                     hold_seconds=request.hold_seconds)

@router.post("/appointments/confirm")
def confirm(request: ConfirmAppointmentRequest):
    return confirm_appointment(slot_id=request.slot_id, 
                               phone_number=request.phone_number)

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

@router.post("/sms/webhook")
async def handle_sms(From: str = Form(...), Body: str = Form(...)):
    ai_reply = llm.generate_response(Body)

    response = MessagingResponse()
    response.message(ai_reply)

    return Response(content=str(response), media_type="application/xml")

