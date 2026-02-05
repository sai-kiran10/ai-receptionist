from fastapi import APIRouter, Depends, Form, Response, WebSocket, Request
from app.services.bookings import HoldSlotRequest, ConfirmAppointmentRequest, hold_slot, confirm_appointment
from app.services.slots import get_available_slots
from app.services.gemini_service import GeminiService
from app.services.llm_interface import LLMInterface
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
import os, json, base64, asyncio
from google import genai
from google.genai import types
import audioop

router = APIRouter()
llm = GeminiService()
MODEL_ID = "gemini-2.5-flash-native-audio-preview-12-2025"

FUNCTIONS = {
    "get_available_slots": get_available_slots,
    "hold_slot": hold_slot,
    "confirm_appointment": confirm_appointment
}

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
async def handle_voice_entry(request: Request):
    """Initial entry point for the call. Connects to WebSocket."""
    response = VoiceResponse()
    
    host = request.headers.get("host")
    stream_url = f"wss://{host}/api/v1/voice/stream"

    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)

    print(f"Streaming to: {stream_url}")
    return Response(content=str(response), media_type="application/xml")

@router.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket):
    """Handles the live audio stream and interruptions."""
    await websocket.accept()
    print("🚀 Voice Stream Connected")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options={'api_version': 'v1alpha'})

    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": "Puck"}
            }
        },
        "generation_config": {
            "candidate_count": 1,
        },
        "tools": [{"function_declarations": [
            {"name": "get_available_slots", "description": "Get available slots for a date (YYYY-MM-DD).", 
             "parameters": {"type": "OBJECT", "properties": {"date": {"type": "string"}}}},
            {"name": "hold_slot", "description": "Temporary hold on a slot.", 
             "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "string"}, "phone_number": {"type": "string"}}}},
            {"name": "confirm_appointment", "description": "Finalize a booking.", 
             "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "string"}, "phone_number": {"type": "string"}}}}
        ]}],
        "system_instruction": "You are a receptionist and this is a live call. Respond immediately when the user finishes speaking."
                              "After you speak, listem immediately for patient's response. If a user asks for slots, use your tools."
                              " Be natural and brief."
    }

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        stream_sid = None

        '''await session.send_client_content(
            turns=[types.Content(role="user", parts=[types.Part(text="Hello! Welcome to The Tech Clinic. How you can help you today?")])],
            turn_complete=True
        )'''
        await session.send(input="Please greet the patient and ask how you can help.")

        async def send_to_twilio():
            async for message in session.receive():
                print("DEBUG - Received msg from Gemini")
                if message.tool_call:
                    for fc in message.tool_call.function_calls:
                        f_name = fc.name
                        f_args = fc.args
                        print(f"🛠️ Gemini is calling: {f_name} with {f_args}")
                        
                        # Execute the actual Python function
                        func = FUNCTIONS.get(f_name)
                        result = func(**f_args) if func else {"error": "Function not found"}
                        
                        # Send the result BACK to Gemini
                        await session.send(tool_response={
                            "function_responses": [{
                                "id": fc.id,
                                "name": f_name,
                                "response": {"result": result}
                            }]
                        })

                if message.server_content and message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            raw_audio = part.inline_data.data
                            resampled_audio, _ = audioop.ratecv(raw_audio, 2, 1, 24000, 8000, None)
                            mulaw_audio = audioop.lin2ulaw(resampled_audio, 2)

                            audio_payload = base64.b64encode(mulaw_audio).decode('utf-8')
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": audio_payload}
                            })

        send_task = asyncio.create_task(send_to_twilio())
        try:
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                if data['event'] == "start":
                    stream_sid = data['start']['streamSid']
                    print(f"Call started, StreamSid: {stream_sid}")
                elif data['event'] == "media":
                    payload = data['media']['payload']
                    mu_law_data = base64.b64decode(payload)
                    pcm_data = audioop.ulaw2lin(mu_law_data, 2)
                    #print(f"DEBUG Audio: {decoded_data[:10].hex()}...Length: {len(decoded_data)}")

                    await session.send_realtime_input(
                        media=types.Blob(
                            data=pcm_data,
                            mime_type="audio/pcm;rate=8000"
                        )
                    )
                    '''await session.send(input={
                        "data": pcm_data,
                        "mime_type": "audio/pcm;rate=8000"
                    })'''
                elif data['event'] == "stop":
                    break
                    
        except Exception as e:
            print(f"Voice Stream Error: {e}")
        finally:
            send_task.cancel()
            await websocket.close()
            print("Connection closed safely")
