from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv
import os
import cloudinary
import cloudinary.uploader
import certifi

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")

if not MONGODB_URL:
    raise ValueError("Missing MONGODB_URL in environment variables")

# MongoDB client with TLS configuration for better compatibility
client: AsyncIOMotorClient = AsyncIOMotorClient(
    MONGODB_URL,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=30000,
    retryWrites=True
)

# Database instance
db: AsyncIOMotorDatabase = client.get_database("onlineclip")

# Collections
clipboard_collection = db.get_collection("clipboard_items")
file_shares_collection = db.get_collection("file_shares")
short_urls_collection = db.get_collection("short_urls")

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


async def create_indexes():
    """Create necessary indexes for performance"""
    # Clipboard indexes
    await clipboard_collection.create_index("code", unique=True)
    await clipboard_collection.create_index("expires_at")
    
    # File shares indexes
    await file_shares_collection.create_index("share_code", unique=True)
    await file_shares_collection.create_index("expires_at")
    
    # Short URLs indexes
    await short_urls_collection.create_index("short_path", unique=True)
    await short_urls_collection.create_index("expires_at")
