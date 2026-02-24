# 🤖 AI Receptionist: The Intelligent Clinic Assistant

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)
[![Twilio](https://img.shields.io/badge/Twilio-F22F46?style=for-the-badge&logo=Twilio&logoColor=white)](https://www.twilio.com/)

An advanced, stateful AI agent designed to automate medical clinic scheduling. This assistant uses **Gemini 2.0 Flash (for SMS)** and **Gemini 2.5 Flash Live (for Calls)** for complex reasoning and **Twilio** for two-way SMS communication and calls, managing the entire booking lifecycle from initial inquiry to atomic database confirmation.



---

## 🌟 Features

* **🧠 Smart NLP:** Understands intent and extracts dates/times from natural speech (e.g., *"Can I move my 10am to Friday instead?"*).
* **💾 Stateful Context:** Remembers user details (Name, Phone, History) across SMS exchanges using persistent chat history.
* **⚡ Atomic Operations:** Implements "Hold-Confirm" logic to prevent race conditions and double-booking.
* **📱 Real-Time Webhooks:** Instant two-way communication via Twilio and Ngrok secure tunneling.
* **☁️ Multi-Cloud Architecture:** Leverages AWS DynamoDB for high-speed NoSQL storage and Google AI Studio for LLM processing.

---
### 🎙️ Voice Call Support
- **Real-time phone coversations** via Twilio Media Streams + Gemini 2.5 Flash Live API
- **Native audio processing** - no STT/TTS latency, direct audio in/out
- **Barge-in interruption** - users can interrupt mid-sentence, bot stops immediately
- **Multi-turn dialogue** - handles complex conversations with context retention
- **Data intelligence** - understands "next Monday", "tomorrow at 2pm" correctly
- **Dual-channel support** - both SMS/WhatsApp and voice calls work simultaneously

---

## 🛠️ Tech Stack

* **Backend:** Python 3.13, FastAPI, Uvicorn
* **AI Engine:** Google Gemini 2.0 Flash, Gemini 2.5 Flash Live API
* **Database:** AWS DynamoDB (Boto3)
* **Communications:** Twilio API/ AWS SNS, Twilio Media Streams (WebSocket)
* **Audio Processing:** Python audioop (8kHz to 16kHz resampling, mu-law to PCM conversion)
* **Real-time Streaming:** WebSocket bidirectional audio, async Python (asyncio)
* **Testing:** Ngrok (Webhook Tunneling), Pydantic (data validation)

---

## 🎯 How It Works

### **For SMS/WhatsApp:**
1. Patient texts appointment request to your Twilio number
2. Twilio forwards message to `/api/v1/sms/webhook`
3. Gemini processes request, calls appropriate tools (check slots, hold, confirm)
4. System respons via SMS/WhatsApp message with confirmation details

### **For Voice Calls:**
1. Patient calls the Twilio number
2. Twilio hits `/api/v1/voice/webhook` -> returns TwiML to connect to WebSocket
3. WebSocket stream (`/api/v1/voice/stream`) opens bidirectional audio connection
4. Audio flows: Caller <-> Twilio <-> FastAPI <-> Gemini Live API
5. Gemini speaks responses naturally, handles interruptions, calls database tools
6. Confirmation message sent automatically after booking

Both channels use the same backend logic and DynamoDB tables - a patient can start on SMS and call later to modify their booking.

---

## 🚀 Quick Start

### 1. Prerequisites
* Python 3.10+
* [Google AI Studio API Key](https://aistudio.google.com/)
* [AWS IAM Credentials](https://aws.amazon.com/) (DynamoDB & SNS Access)
* [Twilio Account](https://www.twilio.com/) (Trial credits work fine)

### 2. Installation
```bash
git clone https://github.com/sai-kiran10/ai-receptionist.git
cd ai_receptionist
```
```bash
# Setup environment
python -m venv venv
```
```bash
# Linux:
source venv/bin/activate
```
```bash
# Windows:
venv\Scripts\activate
```
```bash
pip install -r requirements.txt
```

### 3. Environment Config (.env)
Create a .env file in the root:
```bash
GEMINI_API_KEY=your_key
AWS_ACCESS_KEY_ID=your_id
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_twilio_number
```

### Launch
```bash
# Start FastAPI
uvicorn app.main:app --reload

# Start Ngrok (in a new terminal)
ngrok http 8000POST
```

**📌 Note:** Copy the `https://xxxxxx.ngrok.io` URL from ngrok's output and configure it in Twilio:

1. Go to Twilio Console -> Phone Numbers -> [Your number]

**For Voice Calls:**

2. Under **Voice Configuration**:
    - When a call comes in: "Webhook"
    - URL: `https://xxxxx.ngrok.io/api/v1/voice/webhook`
    - HTTP Method: "POST"

**For SMS/WhatsApp:**

3. Under **Messaging Configuration**:
    - When a message comes in: "Webhook"
    - URL: `https://xxxxxx.ngrok.io/api/v1/sms/webhook`
    - HTTP Method: "POST"

---

## 📡 API Endpoints
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/v1/chat` | `POST` | Primary interface for the Gemini AI engine; handles natural language reasoning and tool-calling. |
| `/api/v1/sms/webhook` | `POST` | Twilio Webhook entry point; processes incoming SMS form data and returns TwiML responses. |
| `/api/v1/slots` | `GET` | Fetches a list of all available and held appointment slots from AWS DynamoDB. |
| `/api/v1/slots/hold` | `POST` | Places a temporary 10-minute lock on a specific slot to prevent race conditions. |
| `/api/v1/appointments/confirm` | `POST` | Finalizes the booking record and transitions slot status from 'HELD' to 'BOOKED'. |
| `/api/v1/voice/webhook` | `POST` | Twilio voice call entry point; returns TwiML to connect call to WebSocket stream. |
| `/api/v1/voice/stream` | `WebSocket` | Real-time bidirectional audio streaming endpoint for live voice conversations with Gemini. |

---

## 🏗️ Technical Highlights
### **Atomic Rescheduling Logic**
To ensure data integrity and prevent the "Lost Appointment" bug, the system performs a multi-step transaction for every reschedule request:

1.  **Hold:** The system immediately places a temporary lock on the new requested slot to prevent other users from taking it while the transaction is in progress.
2.  **Cancel:** It releases the old slot back into the available pool and removes the previous booking record from the `Appointments` table.
3.  **Confirm:** It converts the new "Hold" into a permanent "Booked" status.

This **"Self-Healing"** logic ensures the database state always matches the AI's promises to the user, even if a mid-process error occurs.

### **Concurrency Protection**
The project implements robust concurrency control using **AWS DynamoDB ConditionExpressions**. 

* **Logic:** When updating a slot, the system checks if the status is currently `AVAILABLE` at the exact millisecond of the write.
* **Result:** If two users try to book the same slot at the exact same time, DynamoDB will reject the second request with a `ConditionalCheckFailedException`, effectively preventing double-booking in a high-traffic environment.

### **Real-time Voice Processing**
The voice system uses a sophisticated audio pipeline to achieve sub-500ms response latency:

1. **Audio Format Conversion:** Twilio sends 8kHz mu-law audio; Gemini requires 16kHz PCM. The system performs real-time upsampling/downsampling using Python's **"audioop"** module.

2. **Barge-in Detection:** Gemini's built-in VAD (Voice Activity Detection) recognizes when the user interrupts. The system immediately sends a Twilio **clear** event to flush the audio buffer, creating natural interruption behavious.

3. **Session Isolation:** Each phone call gets its own isolated WebSocket connection, Gemini session, and async task queues - preventing crosstalk even with 10+ simultaneous callers.

4. **Dual-Task Architecture:**
    - send_to_gemini : Continuously streams user audio to Gemini (200ms chunks)
    - send_to_twilio : Receives Gemini's audio responses and forwards to caller

    Both tasks run concurrently using Python's asyncio, with a "while True" loop to handle Gemini's turn-based iterator design.

---

## 🚀 Future Scope
* **📊 Analytics Dashboard:** A Next.js frontend for clinic administrators to visualize booking trends and manage schedules manually.

* **🌍 Multi-Language Support:** Expanding beyond English to support Spanish, Hindi, and other languages for diverse patient populations.

* **📅 Calendar Sync:** Two-way synchronization with Google Calendar and Outlook for seamless provider management.

* **🔐 Auth & Multi-tenancy:** Scaling the backend to support multiple different clinics, each with their own unique AI configurations.

* **🔔 Proactive Reminders:** Automated SMS/voice reminders 24 hours before appointment to reduce no-shows.

---

## 🤝 Contribution
Feel free to fork this project and submit PRs.
