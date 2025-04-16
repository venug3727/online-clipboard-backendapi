from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
import secrets
from cryptography.fernet import Fernet
import hashlib
import base64
import os

import hashlib
import base64
import os

from supabase import create_client
from datetime import datetime, timezone, timedelta

router = APIRouter()

# Initialize Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

def generate_code() -> str:
    return str(secrets.randbelow(9000) + 1000)


def encrypt_content(content: str, key: str = None) -> str:
    """Encrypt content with optional user key or system key"""
    if key:
        # Use user-provided key
        key_hash = hashlib.sha256(key.encode()).digest()
        fernet = Fernet(base64.urlsafe_b64encode(key_hash))
    else:
        # Use system key
        fernet = Fernet(os.getenv("ENCRYPTION_KEY").encode())
    return fernet.encrypt(content.encode()).decode()

def decrypt_content(encrypted_content: str, key: str = None) -> str:
    """Decrypt content with optional user key or system key"""
    try:
        if key:
            # Use user-provided key
            key_hash = hashlib.sha256(key.encode()).digest()
            fernet = Fernet(base64.urlsafe_b64encode(key_hash))
        else:
            # Use system key
            fernet = Fernet(os.getenv("ENCRYPTION_KEY").encode())
        return fernet.decrypt(encrypted_content.encode()).decode()
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")

@router.post("/send")
async def send_clipboard(data: dict):
    # Generate unique 4-digit code
    code = generate_code()
    
    # Check if code exists
    existing = supabase.from_("clipboard_items")\
        .select("*")\
        .eq("code", code)\
        .execute()
    
    if existing.data:
        code = generate_code()  # try again
    
    # Encrypt content if confidential
    encrypted_content = data["content"]
    if data.get("is_confidential"):
        encrypted_content = encrypt_content(
            data["content"], 
            data.get("encryption_key")
        )
    
    # Set expiration (15 minutes default)
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    
    # Insert into Supabase
    item = supabase.from_("clipboard_items").insert({
        "content": encrypted_content,
        "content_type": data.get("content_type", "text"),
        "is_confidential": data.get("is_confidential", False),
        "encryption_key": data.get("encryption_key"),
        "code": code,
        "expires_at": expires_at
    }).execute()
    
    return {
        "code": code,
        "expires_at": expires_at,
        "qr_code_url": f"/qr/{code}"
    }


@router.post("/receive")
async def receive_clipboard(data: dict):
    # Get clipboard item by code
    result = supabase.from_("clipboard_items")\
        .select("*")\
        .eq("code", data["code"])\
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Clipboard content not found")
    
    item = result.data[0]
    
    # Convert expires_at to timezone-aware datetime
    expires_at = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
    
    # Compare with timezone-aware UTC now
    if expires_at < datetime.now(timezone.utc):
        # Delete expired item
        supabase.from_("clipboard_items")\
            .delete()\
            .eq("id", item["id"])\
            .execute()
        raise HTTPException(status_code=410, detail="Clipboard content has expired")
    
    # Decrypt content if confidential
    try:
        content = item["content"]
        if item["is_confidential"]:
            if not data.get("decryption_key"):
                raise HTTPException(
                    status_code=400,
                    detail="Decryption key required for confidential content"
                )
            content = decrypt_content(
                item["content"],
                data["decryption_key"]
            )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
    return {
        "content": content,
        "content_type": item["content_type"],
        "is_confidential": item["is_confidential"],
        "created_at": item["created_at"]
    }