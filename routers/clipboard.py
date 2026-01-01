from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
import secrets
from cryptography.fernet import Fernet
import hashlib
import base64
import os

from database import clipboard_collection

router = APIRouter()


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
    existing = await clipboard_collection.find_one({"code": code})
    
    while existing:
        code = generate_code()
        existing = await clipboard_collection.find_one({"code": code})
    
    # Encrypt content if confidential
    encrypted_content = data["content"]
    if data.get("is_confidential"):
        encrypted_content = encrypt_content(
            data["content"], 
            data.get("encryption_key")
        )
    
    # Set expiration (15 minutes default)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    created_at = datetime.now(timezone.utc)
    
    # Insert into MongoDB
    item = {
        "content": encrypted_content,
        "content_type": data.get("content_type", "text"),
        "is_confidential": data.get("is_confidential", False),
        "encryption_key": data.get("encryption_key"),
        "code": code,
        "expires_at": expires_at,
        "created_at": created_at
    }
    
    await clipboard_collection.insert_one(item)
    
    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "qr_code_url": f"/qr/{code}"
    }


@router.post("/receive")
async def receive_clipboard(data: dict):
    # Get clipboard item by code
    item = await clipboard_collection.find_one({"code": data["code"]})
    
    if not item:
        raise HTTPException(status_code=404, detail="Clipboard content not found")
    
    # Check expiration - handle both timezone-aware and naive datetimes
    expires_at = item["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        # Delete expired item
        await clipboard_collection.delete_one({"_id": item["_id"]})
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
        "created_at": item["created_at"].isoformat()
    }