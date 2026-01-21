from fastapi import APIRouter, Depends
from app.schemas import ChatRequest
from app.services.gemini_service import GeminiService
from app.services.llm_interface import LLMInterface

router = APIRouter()

def get_llm_service()->LLMInterface:
    return GeminiService()

@router.post("/chat")
async def chat(
    request: ChatRequest,
    llm: LLMInterface = Depends(get_llm_service)
):
    """
    Takes the user message and passes it to the AI.
    Gemini will automatically decide if it needs to call 
    'get_available_slots' or 'hold_slot' based on the conversation.
    """
    response_text = llm.generate_response(request.message)
    return {"reply": response_text}
