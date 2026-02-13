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
import google.genai.live as _live_module
from websockets.asyncio.client import connect as _orig_connect
import traceback

os.environ['WEBSOCKETS_MAX_SIZE'] = str(2**24)

router = APIRouter()
llm = GeminiService()
MODEL_ID = "gemini-2.5-flash-native-audio-preview-09-2025"

FUNCTIONS = {
    "get_available_slots": get_available_slots,
    "hold_slot": hold_slot,
    "confirm_appointment": confirm_appointment
}

def _patched_ws_connect(uri, **kwargs):
    kwargs['ping_interval'] = 10
    kwargs['ping_timeout'] = None
    return _orig_connect(uri, **kwargs)
_live_module.ws_connect = _patched_ws_connect

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
            {
                "name": "get_available_slots",
                "description": "Get available appointment slots for a given date (YYYY-MM-DD). MUST be called before discussing any available times.",
                "parameters": {"type": "OBJECT", "properties": {"date": {"type": "STRING"}}, "required": ["date"]}
            },
            {
                "name": "hold_slot",
                "description": "Place a temporary hold on an appointment slot. MUST be called before telling the patient a slot is reserved.",
                "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "STRING"}, "phone_number": {"type": "STRING"}}, "required": ["slot_id", "phone_number"]}
            },
            {
                "name": "confirm_appointment",
                "description": "Permanently confirm and book an appointment. MUST be called before telling the patient their appointment is confirmed.",
                "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "STRING"}, "phone_number": {"type": "STRING"}}, "required": ["slot_id", "phone_number"]}
            }
        ]}],
        "system_instruction": (
            "You are a medical receptionist AI on a live phone call. "
            "CRITICAL RULES - you MUST follow these without exception:\n"
            "1. You MUST call get_available_slots before discussing any appointment times.\n"
            "2. You MUST call hold_slot before saying a slot is reserved.\n"
            "3. You MUST call confirm_appointment before saying a booking is confirmed.\n"
            "4. NEVER say an appointment is booked or confirmed without actually calling confirm_appointment first.\n"
            "5. NEVER invent or hallucinate slot IDs, times, or confirmation details.\n"
            "6. Always get the patient's phone number before calling hold_slot or confirm_appointment.\n"
            "Keep responses brief and natural. Say 'Let me check that for you' before tool calls. "
            "Wait for the patient to finish speaking before responding."
        )
    }

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        stream_sid = None
        audio_queue = asyncio.Queue()
        greeting_done = asyncio.Event()
        print("✅ Gemini session established successfully")

        # FIX: use send_client_content for greeting (reliably triggers response)
        await session.send_client_content(
            turns={"role": "user", "parts": [{"text": "Greet the caller warmly and ask how you can help them today."}]},
            turn_complete=True
        )
        print("✅ Greeting sent to Gemini")

        async def send_to_twilio():
            """Receives audio from Gemini and forwards to Twilio.
            FIX: session.receive() ends after each turn by design — while True restarts it.
            """
            print("🔁 send_to_twilio started")
            try:
                while True:
                    print("🔄 Waiting for next Gemini turn...")
                    async for message in session.receive():
                        print(f"DEBUG msg type: server_content={bool(message.server_content)}, tool_call={bool(message.tool_call)}, setup_complete={bool(message.setup_complete)}")

                        # FIX: tool_call arrives in its own turn — handle it here
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
                                await session.send_tool_response(
                                    function_responses=types.FunctionResponse(
                                        name=f_name,
                                        id=fc.id,
                                        response={"result": result}
                                    )
                                )

                        # FIX: guard ALL server_content access inside one if block
                        if message.server_content:
                            if message.server_content.model_turn:
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

                            # FIX: turn_complete guarded inside 'if message.server_content'
                            if message.server_content.turn_complete:
                                print("✅ Gemini turn complete - looping for next turn")
                                greeting_done.set()
                        # after this inner for-loop ends, while True restarts session.receive()

            except asyncio.CancelledError:
                print("🛑 send_to_twilio cancelled (call ended cleanly)")
            except Exception as e:
                print(f"💥 send_to_twilio CRASHED: {e}")
                traceback.print_exc()
            finally:
                print("✅ send_to_twilio done")

        async def send_to_gemini():
            """Reads from queue and forwards audio to Gemini."""
            await greeting_done.wait()
            print(f"Greeting complete - draining {audio_queue.qsize()} pre-greeting items")
            while not audio_queue.empty():
                audio_queue.get_nowait()
                audio_queue.task_done()
            print("Queue drained, now forwarding user audio to Gemini")

            audio_buffer = bytearray()
            SEND_SIZE = 6400  # 200ms at 16kHz

            try:
                while True:
                    try:
                        pcm_data = await asyncio.wait_for(audio_queue.get(), timeout=2.0)
                        if pcm_data is None:  # poison pill — shut down
                            break
                        audio_buffer.extend(pcm_data)
                        audio_queue.task_done()

                        while len(audio_buffer) >= SEND_SIZE:
                            await session.send_realtime_input(
                                media=types.Blob(
                                    data=bytes(audio_buffer[:SEND_SIZE]),
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                            audio_buffer = audio_buffer[SEND_SIZE:]
                            print(f"Sent {SEND_SIZE} bytes")

                    except asyncio.TimeoutError:
                        if len(audio_buffer) > 0:
                            await session.send_realtime_input(
                                media=types.Blob(
                                    data=bytes(audio_buffer),
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                            print(f"Flushed {len(audio_buffer)} bytes on timeout")
                            audio_buffer = bytearray()

            except asyncio.CancelledError:
                print("🛑 send_to_gemini cancelled (call ended cleanly)")
            except Exception as e:
                print(f"💥 send_to_gemini CRASHED: {e}")
                traceback.print_exc()

        def task_exception_handler(task):
            if not task.cancelled():
                try:
                    exc = task.exception()
                    if exc:
                        print(f"Task crashed: {exc}")
                        traceback.print_tb(exc.__traceback__)
                except Exception:
                    pass

        send_task = asyncio.create_task(send_to_twilio())
        gemini_task = asyncio.create_task(send_to_gemini())
        send_task.add_done_callback(task_exception_handler)
        gemini_task.add_done_callback(task_exception_handler)

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
                    # FIX: upsample 8kHz → 16kHz (Gemini requires 16kHz)
                    pcm_16k, _ = audioop.ratecv(boosted_pcm, 2, 1, 8000, 16000, None)
                    await audio_queue.put(pcm_16k)

                elif data['event'] == "stop":
                    print("📞 Call ended")
                    break

                elif data['event'] == "mark":
                    print(f"Mark: {data}")

                elif data['event'] == "connected":
                    pass  # expected first message, no action needed

                else:
                    print(f"Unknown event: {data['event']}")

        except Exception as e:
            print(f"❌ WebSocket error: {e}")
        finally:
            await audio_queue.put(None)  # shut down send_to_gemini cleanly
            send_task.cancel()
            gemini_task.cancel()
            try:
                await asyncio.gather(send_task, gemini_task, return_exceptions=True)
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
            print("✅ Connection closed")