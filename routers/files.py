from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from datetime import datetime, timedelta, timezone
import secrets
import os
from typing import Optional
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
import random

# Load environment variables
load_dotenv()

app = FastAPI()
router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

class FileShareResponse(BaseModel):
    share_code: str
    download_url: str
    expires_at: str
    file_name: str
    file_size: int
    file_path: str
    content_type: str

class FileInfoResponse(BaseModel):
    file_name: str
    file_size: int
    download_url: str
    expires_at: str
    content_type: str

def generate_share_code():
    """Generate a 4-digit numeric share code"""
    return f"{random.randint(0, 9999):04d}"

def ensure_bucket_exists(bucket_name: str = "filesdata"):
    try:
        supabase.storage.get_bucket(bucket_name)
        return True
    except Exception:
        try:
            supabase.storage.create_bucket(
                bucket_name,
                options={
                    "public": False,
                    "allowed_mime_types": ["*"],
                    "file_size_limit": "50MB"
                }
            )
            return True
        except Exception as e:
            logger.error(f"Bucket creation failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Storage configuration error")

@router.post("/upload", response_model=FileShareResponse)
async def upload_file(file: UploadFile = File(...), expires_days: int = 7):
    try:
        logger.info(f"Received upload - file: {file.filename}")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename required")

        max_size = 50 * 1024 * 1024  # 50MB
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > max_size:
            raise HTTPException(status_code=413, detail="File too large")

        ensure_bucket_exists("filesdata")

        # Generate unique 4-digit code
        share_code = generate_share_code()
        
        # Ensure code is unique
        existing = supabase.table("file_shares").select("*").eq("share_code", share_code).execute()
        while existing.data:
            share_code = generate_share_code()
            existing = supabase.table("file_shares").select("*").eq("share_code", share_code).execute()

        file_path = f"shared/{share_code}/{file.filename}"
        file_contents = await file.read()
        
        # Upload file
        res = supabase.storage.from_("filesdata").upload(
            path=file_path,
            file=file_contents,
            file_options={
                "content-type": file.content_type,
                "upsert": False
            }
        )

        if hasattr(res, 'error') and res.error:
            raise HTTPException(status_code=500, detail=f"File upload failed: {res.error.message}")

        # Create signed URL (returns a dictionary)
        url_res = supabase.storage.from_("filesdata").create_signed_url(
            file_path, 
            60*60*24*expires_days  # Expires in X days
        )
        
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
        created_at = datetime.now(timezone.utc).isoformat()

        # Insert metadata
        insert_result = supabase.table("file_shares").insert({
            "file_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "share_code": share_code,
            "created_at": created_at,
            "expires_at": expires_at,
            "content_type": file.content_type
        }).execute()

        if hasattr(insert_result, 'error') and insert_result.error:
            supabase.storage.from_("filesdata").remove([file_path])
            raise HTTPException(
                status_code=500,
                detail=f"Database insert failed: {insert_result.error.message}"
            )

        return {
            "share_code": share_code,
            "download_url": url_res['signedURL'],  # Access signedURL from dict
            "expires_at": expires_at,
            "file_name": file.filename,
            "file_size": file_size,
            "file_path": file_path,
            "content_type": file.content_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{share_code}", response_model=FileInfoResponse)
async def get_file_by_code(share_code: str):
    try:
        # Validate share code format
        if not share_code.isdigit() or len(share_code) != 4:
            raise HTTPException(status_code=400, detail="Invalid share code format")

        # Get file info from database
        result = supabase.table("file_shares").select("*").eq("share_code", share_code).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_info = result.data[0]
        
        # Check if expired
        expires_at = datetime.fromisoformat(file_info["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=410, detail="File link has expired")
        
        # Generate new signed URL (returns a dictionary)
        url_res = supabase.storage.from_("filesdata").create_signed_url(
            file_info["file_path"], 
            60*60  # 1 hour expiration for the signed URL
        )
        
        return {
            "file_name": file_info["file_name"],
            "file_size": file_info["file_size"],
            "download_url": url_res['signedURL'],  # Access signedURL from dict
            "expires_at": file_info["expires_at"],
            "content_type": file_info["content_type"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("File retrieval failed")
        raise HTTPException(status_code=500, detail=str(e))

