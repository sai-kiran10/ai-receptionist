import json
from openai import OpenAI

client = OpenAI()

SYSTEM_PROMPT = """
You are an appointment scheduling assistant.
You NEVER book, hold, or confirm appointments.
You ONLY extract structured intent.

Valid intents:
BOOK, CONFIRM, CANCEL, ASK_AVAILABILITY, UNKNOWN

If information is missing, use null.
Respond ONLY with valid JSON.
"""

def extract_intent(message: str):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)
