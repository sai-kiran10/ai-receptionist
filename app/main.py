from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio

from app.api.routes import router as api_router
from app.chat import router as chat_router
from app.background.expiry import expire_held_slots

# The Lifespan handles startup and shutdown in one clean block
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Receptron")
    # This runs your background task for DynamoDB slot expiry
    bg_task = asyncio.create_task(expire_held_slots())
    
    yield  # The app is now running and "alive"
    
    print("🛑 Shutting down...")
    bg_task.cancel() # Cleanly stop the background worker

app = FastAPI(title="AI Receptionist", lifespan=lifespan)

# Including routers with clear prefixes
app.include_router(api_router, prefix="/api/v1")
#app.include_router(chat_router, prefix="/chat/v1")