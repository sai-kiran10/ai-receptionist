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
MODEL_ID = "gemini-2.5-flash-native-audio-preview-09-2025"

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
    await websocket.accept()
    print("🚀 Voice Stream Connected")

    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options={'api_version': 'v1alpha'}
    )

    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": "Puck"}
            }
        },
        "tools": [{"function_declarations": [
            {"name": "get_available_slots",
             "description": "Get available slots for a date (YYYY-MM-DD).",
             "parameters": {"type": "OBJECT", "properties": {"date": {"type": "STRING"}}, "required": ["date"]}},
            {"name": "hold_slot",
             "description": "Temporary hold on a slot.",
             "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "STRING"}, "phone_number": {"type": "STRING"}}, "required": ["slot_id", "phone_number"]}},
            {"name": "confirm_appointment",
             "description": "Finalize a booking.",
             "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "STRING"}, "phone_number": {"type": "STRING"}}, "required": ["slot_id", "phone_number"]}}
        ]}],
        "system_instruction": (
            "You are a friendly medical receptionist on a live phone call. "
            "Keep responses brief and natural. When looking up info say 'Let me check that for you.' "
            "Wait for the patient to finish speaking before responding."
        )
    }

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        stream_sid = None
        audio_queue = asyncio.Queue()  # Queue decouples WebSocket from Gemini
        print("✅ Gemini session established successfully")

        await session.send(
            input="Greet the caller warmly and ask how you can help them today.",
            end_of_turn=True
        )
        print("✅ Greeting sent to Gemini")

        async def keepalive():
            """Send silent audio every 5s to prevent Gemini session timeout"""
            silent_chunk = b'\x00' * 1600
            while True:
                await asyncio.sleep(5)
                try:
                    await session.send_realtime_input(
                        media=types.Blob(
                            data=silent_chunk,
                            mime_type="audio/pcm;rate=8000"
                        )
                    )
                except Exception:
                    break

        async def send_to_twilio():
            """Receives audio from Gemini and forwards to Twilio"""
            try:
                async for message in session.receive():
                    print(f"DEBUG msg type: server_content={bool(message.server_content)}, tool_call={bool(message.tool_call)}, setup_complete={bool(message.setup_complete)}")
                    if message.tool_call:
                        for fc in message.tool_call.function_calls:
                            f_name = fc.name
                            f_args = fc.args
                            print(f"🛠️ Tool called: {f_name} with {f_args}")
                            func = FUNCTIONS.get(f_name)
                            try:
                                result = func(**f_args) if func else {"error": "Function not found"}
                                print(f"✅ Tool result: {result}")
                            except Exception as e:
                                print(f"❌ Tool error: {e}")
                                result = {"error": str(e)}

                            await session.send(
                                input=types.LiveClientToolResponse(
                                        function_responses=[
                                            types.FunctionResponse(
                                                name=f_name,
                                                id=fc.id,
                                                response={"result": result}
                                            )
                                        ]
                                    )
                                )

                    if message.server_content and message.server_content.model_turn:
                        for part in message.server_content.model_turn.parts:
                            if part.inline_data:
                                raw_audio = part.inline_data.data
                                print(f"🔊 Gemini audio: {len(raw_audio)} bytes")

                                remainder = len(raw_audio) % 6
                                if remainder > 0:
                                    raw_audio = raw_audio[:-remainder]

                                if len(raw_audio) > 0:
                                    try:
                                        resampled_audio, _ = audioop.ratecv(raw_audio, 2, 1, 24000, 8000, None)
                                        mulaw_audio = audioop.lin2ulaw(resampled_audio, 2)
                                        audio_payload = base64.b64encode(mulaw_audio).decode('utf-8')
                                        await websocket.send_json({
                                            "event": "media",
                                            "streamSid": stream_sid,
                                            "media": {"payload": audio_payload}
                                        })
                                    except Exception as e:
                                        print(f"❌ Audio conversion error: {e}")
            except Exception as e:
                print(f"❌ send_to_twilio error: {e}")

        async def send_to_gemini():
            """Reads from queue and forwards audio to Gemini — runs independently"""
            silent_chunk = b'\x00' * 1600
            try:
                while True:
                    try:
                        pcm_data = await asyncio.wait_for(audio_queue.get(), timeout=3.0)
                        if pcm_data is None:  # Poison pill — shut down
                            break
                        await session.send_realtime_input(
                            media=types.Blob(
                                data=pcm_data,
                                mime_type="audio/pcm;rate=8000"
                            )
                        )
                        audio_queue.task_done()
                    except asyncio.TimeoutError:
                        print("Sending keepalive silence")
                        await session.send_realtime_input(
                            media=types.Blob(
                                data=silent_chunk,
                                mime_type="audio/pcm;rate=8000"
                            )
                        )
            except Exception as e:
                print(f"❌ send_to_gemini error: {e}")

        # Both tasks run concurrently — neither blocks the other
        send_task = asyncio.create_task(send_to_twilio())
        gemini_task = asyncio.create_task(send_to_gemini())
        keepalive_task = asyncio.create_task(keepalive())

        try:
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)

                if data['event'] == "start":
                    stream_sid = data['start']['streamSid']
                    print(f"📞 Call started, StreamSid: {stream_sid}")

                elif data['event'] == "media":
                    payload = data['media']['payload']
                    mu_law_data = base64.b64decode(payload)
                    pcm_data = audioop.ulaw2lin(mu_law_data, 2)
                    boosted_pcm = audioop.mul(pcm_data, 2, 1.5)

                    # 👇 Just enqueue — never awaits Gemini directly in this loop
                    await audio_queue.put(boosted_pcm)

                elif data['event'] == "stop":
                    print("📞 Call ended")
                    break

        except Exception as e:
            print(f"❌ WebSocket error: {e}")
        finally:
            await audio_queue.put(None)  # Shut down gemini_task cleanly
            send_task.cancel()
            gemini_task.cancel()
            keepalive_task.cancel()
            try:
                await websocket.close()
            except:
                pass
            print("✅ Connection closed")
