# 🤖 AI Receptionist: The Intelligent Clinic Assistant

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=for-the-badge&logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)
[![Twilio](https://img.shields.io/badge/Twilio-F22F46?style=for-the-badge&logo=Twilio&logoColor=white)](https://www.twilio.com/)

An advanced, stateful AI agent designed to automate medical clinic scheduling. This assistant uses **Gemini 2.0 Flash** for complex reasoning and **Twilio** for two-way SMS communication, managing the entire booking lifecycle from initial inquiry to atomic database confirmation.



---

## 🌟 Features

* **🧠 Smart NLP:** Understands intent and extracts dates/times from natural speech (e.g., *"Can I move my 10am to Friday instead?"*).
* **💾 Stateful Context:** Remembers user details (Name, Phone, History) across SMS exchanges using persistent chat history.
* **⚡ Atomic Operations:** Implements "Hold-Confirm" logic to prevent race conditions and double-booking.
* **📱 Real-Time Webhooks:** Instant two-way communication via Twilio and Ngrok secure tunneling.
* **☁️ Multi-Cloud Architecture:** Leverages AWS DynamoDB for high-speed NoSQL storage and Google AI Studio for LLM processing.

---

## 🛠️ Tech Stack

* **Backend:** Python 3.13, FastAPI, Uvicorn
* **AI Engine:** Google Gemini 2.0 Flash
* **Database:** AWS DynamoDB (Boto3)
* **Communications:** Twilio API/ AWS SNS
* **Testing:** Ngrok (Webhook Tunneling), Pydantic (data validation)

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
ngrok http 8000
```

## 📡 API Endpoints
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/v1/chat` | `POST` | Primary interface for the Gemini AI engine; handles natural language reasoning and tool-calling. |
| `/api/v1/sms/webhook` | `POST` | Twilio Webhook entry point; processes incoming SMS form data and returns TwiML responses. |
| `/api/v1/slots` | `GET` | Fetches a list of all available and held appointment slots from AWS DynamoDB. |
| `/api/v1/slots/hold` | `POST` | Places a temporary 10-minute lock on a specific slot to prevent race conditions. |
| `/api/v1/appointments/confirm` | `POST` | Finalizes the booking record and transitions slot status from 'HELD' to 'BOOKED'. |

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

## 🚀 Future Scope
* **🎙️ Voice Integration:** Implementing Twilio Media Streams to allow the AI to handle real-time phone calls with Speech-to-Text (STT) and Text-to-Speech (TTS).

* **📊 Analytics Dashboard:** A Next.js frontend for clinic administrators to visualize booking trends and manage schedules manually.

* **📅 Calendar Sync:** Two-way synchronization with Google Calendar and Outlook for seamless provider management.

* **🔐 Auth & Multi-tenancy:** Scaling the backend to support multiple different clinics, each with their own unique AI configurations.

## 🤝 Contribution
Feel free to fork this project and submit PRs. I'm currently looking to expand this into a Voice-based AI using Twilio Media Streams!
