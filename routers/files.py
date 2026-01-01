from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta, timezone
import os
from pydantic import BaseModel
import logging
import random
import cloudinary.uploader

from database import file_shares_collection

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FileShareResponse(BaseModel):
    share_code: str
    download_url: str
    expires_at: str
    file_name: str
    file_size: int
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

        # Generate unique 4-digit code
        share_code = generate_share_code()
        
        # Ensure code is unique
        existing = await file_shares_collection.find_one({"share_code": share_code})
        while existing:
            share_code = generate_share_code()
            existing = await file_shares_collection.find_one({"share_code": share_code})

        # Read file contents
        file_contents = await file.read()
        
        # Upload to Cloudinary
        # Use resource_type="raw" for non-image/video files
        upload_result = cloudinary.uploader.upload(
            file_contents,
            public_id=f"onlineclip/{share_code}/{file.filename}",
            resource_type="auto",  # auto-detect file type
            folder="onlineclip_files"
        )
        
        # Get the secure URL from Cloudinary
        download_url = upload_result.get("secure_url")
        cloudinary_public_id = upload_result.get("public_id")
        
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        created_at = datetime.now(timezone.utc)

        # Insert metadata into MongoDB
        await file_shares_collection.insert_one({
            "file_name": file.filename,
            "cloudinary_public_id": cloudinary_public_id,
            "cloudinary_url": download_url,
            "file_size": file_size,
            "share_code": share_code,
            "created_at": created_at,
            "expires_at": expires_at,
            "content_type": file.content_type
        })

        return {
            "share_code": share_code,
            "download_url": download_url,
            "expires_at": expires_at.isoformat(),
            "file_name": file.filename,
            "file_size": file_size,
            "content_type": file.content_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{share_code}", response_model=FileInfoResponse)
async def get_file_info(share_code: str):
    try:
        # Validate share code format
        if not share_code.isdigit() or len(share_code) != 4:
            raise HTTPException(status_code=400, detail="Invalid share code format")

        # Get file info from database
        file_info = await file_shares_collection.find_one({"share_code": share_code})
        
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if expired - handle both timezone-aware and naive datetimes
        expires_at = file_info["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            # Optionally delete from Cloudinary
            try:
                cloudinary.uploader.destroy(file_info["cloudinary_public_id"])
            except:
                pass
            await file_shares_collection.delete_one({"share_code": share_code})
            raise HTTPException(status_code=410, detail="File link has expired")
        
        return {
            "file_name": file_info["file_name"],
            "file_size": file_info["file_size"],
            "download_url": file_info["cloudinary_url"],
            "expires_at": file_info["expires_at"].isoformat(),
            "content_type": file_info["content_type"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("File info retrieval failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{share_code}")
async def download_file(share_code: str):
    """Redirect to Cloudinary URL for download"""
    try:
        # Validate share code format
        if not share_code.isdigit() or len(share_code) != 4:
            raise HTTPException(status_code=400, detail="Invalid share code format")

        # Get file info from database
        file_info = await file_shares_collection.find_one({"share_code": share_code})
        
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Check if expired - handle both timezone-aware and naive datetimes
        expires_at = file_info["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=410, detail="File link has expired")
        
        # Redirect to Cloudinary URL
        return RedirectResponse(url=file_info["cloudinary_url"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("File download failed")
        raise HTTPException(status_code=500, detail=str(e))
