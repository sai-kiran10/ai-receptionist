from fastapi import APIRouter, Depends, Form, Response, WebSocket
from app.services.bookings import HoldSlotRequest, ConfirmAppointmentRequest, hold_slot, confirm_appointment
from app.services.slots import get_available_slots
from app.services.gemini_service import GeminiService
from app.services.llm_interface import LLMInterface
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
import json

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
    clean_phone = From.replace("whatsapp:", "")

    prompt_with_context = f"[User Phone: {clean_phone}] {Body}"
    
    ai_reply = llm.generate_response(prompt_with_context)

    response = MessagingResponse()
    response.message(ai_reply)

    return Response(content=str(response), media_type="application/xml")

@router.post("/voice/webhook")
async def handle_voice_entry():
    """Initial entry point for the call. Connects to WebSocket."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"https://unmonistic-aarav-despitefully.ngrok-free.dev/api/v1/voice/stream")
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@router.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """Handles the live audio stream and interruptions."""
    await websocket.accept()
    print("🚀 Voice Stream Connected")
    
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            
            if data['event'] == "start":
                print("Call started")
            elif data['event'] == "media":
                pass
            elif data['event'] == "mark":
                print("Audio playback finished")
                
    except Exception as e:
        print(f"Voice Stream Error: {e}")
    finally:
        await websocket.close()
