from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

from database import create_indexes

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create indexes
    await create_indexes()
    yield
    # Shutdown: Nothing needed for now

app = FastAPI(lifespan=lifespan)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174", 
        "https://bmsclipboard.netlify.app",
        "https://bmsclipboard.vgcs.online"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

@app.get("/")
def wel():
    return {
        'data': "welcome with MongoDB"
    }

# Include routers
from routers import clipboard, files, urls
app.include_router(clipboard.router, prefix="/api/clipboard", tags=["Clipboard"])
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(urls.router, prefix="/api/urls", tags=["URLs"])
