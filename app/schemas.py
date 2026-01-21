from pydantic import BaseModel
from typing import Optional, Literal

class ChatRequest(BaseModel):
    message: str

class IntentResponse(BaseModel):
    intent: Literal["BOOK", "CONFIRM", "CANCEL", "ASK_AVAILABILITY", "UNKNOWN"]
    date: Optional[str]
    time_preference: Optional[Literal["morning", "afternoon", "evening", "exact_time"]]
    exact_time: Optional[str]
