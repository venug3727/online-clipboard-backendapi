from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
import secrets
from fastapi.responses import RedirectResponse
from supabase import create_client
import os
from pydantic import BaseModel

router = APIRouter()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

class URLData(BaseModel):
    url: str
    custom_path: str | None = None

@router.post("/shorten")
async def shorten_url(url_data: URLData):
    if not url_data.url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Validate custom path if provided
    if url_data.custom_path:
        if not url_data.custom_path.isalnum():
            raise HTTPException(
                status_code=400, 
                detail="Custom path can only contain letters and numbers"
            )
        if len(url_data.custom_path) < 3:
            raise HTTPException(
                status_code=400,
                detail="Custom path must be at least 3 characters"
            )
    
    # Use custom path or generate a random one
    short_path = url_data.custom_path or secrets.token_urlsafe(6)
    
    # Check if path exists
    existing = supabase.table("short_urls") \
        .select("*") \
        .eq("short_path", short_path) \
        .execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="This custom path is already taken")
    
    # Save to Supabase
    result = supabase.table("short_urls").insert({
        "original_url": url_data.url,
        "short_path": short_path,
        "expires_at": (datetime.utcnow() + timedelta(days=365)).isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }).execute()
    
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create short URL")
    
    return {
        "short_url": f"https://bmsclipboard.vercel.app/{short_path}",  # Changed to full URL
        "original_url": url_data.url
    }

@router.get("/{short_path}")
async def redirect_short_url(short_path: str):
    # Look up the original URL
    result = supabase.table("short_urls") \
        .select("original_url") \
        .eq("short_path", short_path) \
        .execute()
    
    print(f"Looking up path: {short_path}")  # Debug logging
    
    if not result.data:
        print("Path not found")  # Debug logging
        raise HTTPException(status_code=404, detail="Short URL not found")
    
    original_url = result.data[0]["original_url"]
    print(f"Redirecting to: {original_url}")  # Debug logging
    return RedirectResponse(url=original_url)