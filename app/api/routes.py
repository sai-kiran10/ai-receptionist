from fastapi import APIRouter, Depends, Form, Response, WebSocket, Request
from app.services.bookings import (
    HoldSlotRequest, ConfirmAppointmentRequest,
    hold_slot, confirm_appointment,
    get_appointments_by_phone, cancel_appointment,
    resend_confirmation
)
from app.services.slots import get_available_slots
from app.services.gemini_service import GeminiService
from app.services.llm_interface import LLMInterface
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
import os, json, base64, asyncio
from datetime import datetime
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
    "confirm_appointment": confirm_appointment,
    "get_appointments_by_phone": get_appointments_by_phone,
    "cancel_appointment": cancel_appointment,
    "resend_confirmation": resend_confirmation,
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
    """Initial entry point for the call — connects Twilio to our WebSocket."""
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

    now = datetime.now()
    today_str   = now.strftime("%Y-%m-%d")       # e.g. 2026-02-24
    today_words = now.strftime("%A, %B %d, %Y")  # e.g. Friday, February 24, 2026

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
                "description": (
                    "Get available appointment slots for a given date (YYYY-MM-DD). "
                    "MUST be called before discussing any available times. "
                    "Always convert relative dates like 'tomorrow' or 'next Monday' "
                    "to YYYY-MM-DD format before calling this."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"date": {"type": "STRING"}},
                    "required": ["date"]
                }
            },
            {
                "name": "hold_slot",
                "description": (
                    "Place a temporary hold on an appointment slot. "
                    "MUST be called before telling the patient a slot is reserved."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "slot_id": {"type": "STRING"},
                        "phone_number": {"type": "STRING"}
                    },
                    "required": ["slot_id", "phone_number"]
                }
            },
            {
                "name": "confirm_appointment",
                "description": (
                    "Permanently confirm and book an appointment. "
                    "Also call this to RESEND a confirmation SMS — use the same slot_id and phone_number. "
                    "MUST be called before saying a booking is confirmed."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "slot_id": {"type": "STRING"},
                        "phone_number": {"type": "STRING"}
                    },
                    "required": ["slot_id", "phone_number"]
                }
            },
            {
                "name": "get_appointments_by_phone",
                "description": (
                    "Look up existing appointments for a patient by phone number. "
                    "Use when a patient asks about their bookings or wants to cancel."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"phone_number": {"type": "STRING"}},
                    "required": ["phone_number"]
                }
            },
            {
                "name": "cancel_appointment",
                "description": "Cancel an existing appointment and free the slot.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"appointment_id": {"type": "STRING"}},
                    "required": ["appointment_id"]
                }
            },
            {
                "name": "resend_confirmation",
                "description": "Resend confirmation SMS for the patient's most recent appointment. Use when patient says they didn't receive the SMS or asks to resend.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"phone_number": {"type": "STRING"}},
                    "required": ["phone_number"]
                }
            }
        ]}],
        "system_instruction": (
            f"You are a medical receptionist AI for The Tech Clinic on a live phone call. "
            f"Today is {today_words} (ISO: {today_str}). "
            f"Use this to resolve relative dates — 'tomorrow', 'next Monday', 'this Friday' etc. "
            f"Always convert to YYYY-MM-DD before calling get_available_slots. "
            "Remember the patient's name and phone number during the whole conversation and don't ask for it again and again."
            "CRITICAL RULES — follow without exception:\n"
            "1. MUST call get_available_slots before discussing any appointment times.\n"
            "2. MUST call hold_slot before saying a slot is reserved.\n"
            "3. MUST call confirm_appointment before saying a booking is confirmed.\n"
            "4. NEVER say an appointment is confirmed without calling confirm_appointment first.\n"
            "5. NEVER invent slot IDs, times, or confirmation details.\n"
            "6. Always get the patient's phone number before calling hold_slot or confirm_appointment.\n"
            "7. If patient says 'didn't get SMS' or 'resend confirmation', call resend_confirmation with their phone number.\n"
            "8. To check existing bookings, call get_appointments_by_phone first.\n"
            "9. NEVER say you sent a message without calling a tool that actually sends it.\n"
            "10. If the patient interrupts you while you are speaking, stop immediately and listen. "
            "Do not finish your sentence. Acknowledge briefly if needed and respond to what they said.\n"
            "Keep responses brief and natural. Say 'Let me check that for you' before tool calls. "
            "Wait for the patient to finish speaking before responding."
        )
    }

    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        stream_sid = None
        audio_queue = asyncio.Queue()
        greeting_done = asyncio.Event()
        print("✅ Gemini session established")

        await session.send_client_content(
            turns={"role": "user", "parts": [{"text": "Greet the caller warmly and ask how you can help them today."}]},
            turn_complete=True
        )
        print("✅ Greeting sent to Gemini")

        async def send_to_twilio():
            """
            Receives responses from Gemini and forwards audio to Twilio.
            """
            print("🔁 send_to_twilio started")
            try:
                while True:
                    print("🔄 Waiting for next Gemini turn...")
                    async for message in session.receive():
                        print(
                            f"DEBUG msg: server_content={bool(message.server_content)}, "
                            f"tool_call={bool(message.tool_call)}, "
                            f"setup_complete={bool(message.setup_complete)}"
                        )

                        if message.tool_call:
                            for fc in message.tool_call.function_calls:
                                f_name = fc.name
                                f_args = fc.args
                                print(f"🛠️  Tool called: {f_name} with {f_args}")
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

                        if message.server_content:

                            # BARGE-IN: user spoke while Gemini was talking.
                            # Gemini stops generating; we flush Twilio's audio buffer
                            # so the caller doesn't hear the tail end of the sentence.
                            if message.server_content.interrupted:
                                print("🤚 Barge-in detected — clearing Twilio audio buffer")
                                if stream_sid:
                                    try:
                                        await websocket.send_json({
                                            "event": "clear",
                                            "streamSid": stream_sid
                                        })
                                    except Exception as e:
                                        print(f"❌ Failed to send clear: {e}")

                            if message.server_content.model_turn:
                                for part in message.server_content.model_turn.parts:
                                    if part.inline_data:
                                        raw_audio = part.inline_data.data
                                        print(f"🔊 Gemini audio: {len(raw_audio)} bytes")
                                        remainder = len(raw_audio) % 6
                                        if remainder:
                                            raw_audio = raw_audio[:-remainder]
                                        if raw_audio:
                                            try:
                                                # Gemini outputs 24kHz PCM → 8kHz μ-law for Twilio
                                                resampled, _ = audioop.ratecv(raw_audio, 2, 1, 24000, 8000, None)
                                                mulaw = audioop.lin2ulaw(resampled, 2)
                                                payload = base64.b64encode(mulaw).decode('utf-8')
                                                await websocket.send_json({
                                                    "event": "media",
                                                    "streamSid": stream_sid,
                                                    "media": {"payload": payload}
                                                })
                                            except Exception as e:
                                                print(f"❌ Audio conversion error: {e}")

                            if message.server_content.turn_complete:
                                print("✅ Turn complete — looping for next turn")
                                greeting_done.set()

            except asyncio.CancelledError:
                print("🛑 send_to_twilio cancelled (call ended)")
            except Exception as e:
                print(f"💥 send_to_twilio CRASHED: {e}")
                traceback.print_exc()
            finally:
                print("✅ send_to_twilio done")

        async def send_to_gemini():
            """
            Reads microphone audio from the queue and streams it to Gemini.
            Waits for greeting to finish, drains accumulated audio, then forwards.
            """
            await greeting_done.wait()
            drained = 0
            while not audio_queue.empty():
                audio_queue.get_nowait()
                audio_queue.task_done()
                drained += 1
            print(f"Greeting done — drained {drained} pre-greeting chunks, forwarding user audio")

            audio_buffer = bytearray()
            SEND_SIZE = 6400  # 200ms at 16kHz

            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(audio_queue.get(), timeout=2.0)
                        if chunk is None:   # poison pill — call ended
                            break
                        audio_buffer.extend(chunk)
                        audio_queue.task_done()

                        while len(audio_buffer) >= SEND_SIZE:
                            await session.send_realtime_input(
                                media=types.Blob(
                                    data=bytes(audio_buffer[:SEND_SIZE]),
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                            audio_buffer = audio_buffer[SEND_SIZE:]
                            print(f"Sent {SEND_SIZE} bytes to Gemini")

                    except asyncio.TimeoutError:
                        if audio_buffer:
                            await session.send_realtime_input(
                                media=types.Blob(
                                    data=bytes(audio_buffer),
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                            print(f"Flushed {len(audio_buffer)} bytes on timeout")
                            audio_buffer = bytearray()

            except asyncio.CancelledError:
                print("🛑 send_to_gemini cancelled (call ended)")
            except Exception as e:
                print(f"💥 send_to_gemini CRASHED: {e}")
                traceback.print_exc()

        def task_exception_handler(task):
            if not task.cancelled():
                try:
                    exc = task.exception()
                    if exc:
                        print(f"⚠️  Task finished with exception: {exc}")
                        traceback.print_tb(exc.__traceback__)
                except Exception:
                    pass

        send_task = asyncio.create_task(send_to_twilio())
        gemini_task = asyncio.create_task(send_to_gemini())
        send_task.add_done_callback(task_exception_handler)
        gemini_task.add_done_callback(task_exception_handler)

        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                event = data.get('event')

                if event == "connected":
                    pass  # expected first Twilio message

                elif event == "start":
                    stream_sid = data['start']['streamSid']
                    print(f"📞 Call started — StreamSid: {stream_sid}")

                elif event == "media":
                    payload    = data['media']['payload']
                    mu_law     = base64.b64decode(payload)
                    pcm_8k     = audioop.ulaw2lin(mu_law, 2)
                    pcm_8k     = audioop.mul(pcm_8k, 2, 1.5)         # slight volume boost
                    # Gemini requires 16kHz — upsample from Twilio's 8kHz
                    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
                    await audio_queue.put(pcm_16k)

                elif event == "stop":
                    print("📞 Call ended")
                    break

                elif event == "mark":
                    pass

                else:
                    print(f"Unknown Twilio event: {event}")

        except Exception as e:
            print(f"❌ WebSocket error: {e}")
        finally:
            await audio_queue.put(None)
            send_task.cancel()
            gemini_task.cancel()
            await asyncio.gather(send_task, gemini_task, return_exceptions=True)
            try:
                await websocket.close()
            except Exception:
                pass
            print("✅ Connection closed cleanly")