from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", 
    "http://localhost:5174", 
    "https://bmsclipboard.netlify.app/"
        "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Verify environment variables are loaded
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase configuration in environment variables")

# Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
@app.get("/")
def wel():
    return {
        'data':"welcome"
    }
# Include routers
from routers import clipboard, files, urls
app.include_router(clipboard.router, prefix="/api/clipboard", tags=["Clipboard"])
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(urls.router, prefix="/api/urls", tags=["URLs"])
