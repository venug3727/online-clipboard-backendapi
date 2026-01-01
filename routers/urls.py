from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
import secrets
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from database import short_urls_collection

router = APIRouter()


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
    existing = await short_urls_collection.find_one({"short_path": short_path})
    
    if existing:
        raise HTTPException(status_code=400, detail="This custom path is already taken")
    
    # Save to MongoDB
    await short_urls_collection.insert_one({
        "original_url": url_data.url,
        "short_path": short_path,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=365),
        "created_at": datetime.now(timezone.utc)
    })
    
    return {
        "short_url": f"https://clip.vgcs.online/api/urls/{short_path}",
        "original_url": url_data.url
    }


@router.get("/{short_path}")
async def redirect_short_url(short_path: str):
    result = await short_urls_collection.find_one({"short_path": short_path})
    
    if not result:
        raise HTTPException(status_code=404, detail="Short URL not found")
    
    return RedirectResponse(url=result["original_url"])