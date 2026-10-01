import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ...rest of your existing main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.streams import router as streams_router
from backend.app.api.viewer import router as viewer_router
from backend.app.api.admin import router as admin_router
from backend.app.api.webrtc import router as webrtc_router
from backend.app.api.auth import router as auth_router
from sqlalchemy import text
from backend.app.database import AsyncSessionLocal


app = FastAPI(
    title="DroneStream API",
    description="Secure live drone streaming platform",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(streams_router)
app.include_router(viewer_router)
app.include_router(admin_router)
app.include_router(webrtc_router)
app.include_router(auth_router)


@app.get("/")
async def root():
    return {
        "application": "DroneStream",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }
    
@app.get("/health/database")
async def database_health():
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar_one()

        return {
            "status": "healthy",
            "database": "connected",
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }