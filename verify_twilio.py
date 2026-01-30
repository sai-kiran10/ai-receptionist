import os
from twilio.rest import Client
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

print(f"DEBUG: Checking path: {env_path}")
print(f"DEBUG: SID found: {os.getenv('TWILIO_ACCOUNT_SID')}")
print(f"DEBUG: Token found: {'Exists' if os.getenv('TWILIO_AUTH_TOKEN') else 'None'}")
print(f"DEBUG: Phone found: {os.getenv('TWILIO_PHONE_NUMBER')}")

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
from_number = os.getenv('TWILIO_PHONE_NUMBER')

if not account_sid or not auth_token:
    print("❌ ERROR: Your .env file is not being read correctly.")
else:
    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body="Direct test from AI Receptionist! 🤖",
            from_=from_number,
            to="+15715648104"  # Need to add our verified number here
        )
        print(f"✅ Success! SID: {message.sid}")
    except Exception as e:
        print(f"❌ Twilio Error: {e}")