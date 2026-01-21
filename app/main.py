from fastapi import FastAPI
from app.api.routes import router as api_router
from app.chat import router as chat_router
from app.background.expiry import expire_held_slots
import asyncio

app = FastAPI()

app.include_router(api_router)
app.include_router(chat_router)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(expire_held_slots())

