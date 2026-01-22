"""
Configuration file for the crawler
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in crawler directory
BASE_DIR = Path(__file__).parent
env_file = BASE_DIR / ".env"
load_dotenv(env_file)

# Base paths (BASE_DIR already set above)
RESOURCES_DIR = BASE_DIR / "resources"
SOURCES_FILE = RESOURCES_DIR / "sources.json"

# Vertex AI Configuration
VERTEX_PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
VERTEX_INDEX_ID = os.getenv("VERTEX_INDEX_ID", "")
VERTEX_INDEX_ENDPOINT = os.getenv("VERTEX_INDEX_ENDPOINT", "")

# Google Cloud Credentials
# Resolve relative paths relative to the config file location, not current working directory
_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if _creds_path and not os.path.isabs(_creds_path):
    # If it's a relative path, resolve it relative to the crawler directory
    _creds_path = str((BASE_DIR / _creds_path).resolve())
GOOGLE_APPLICATION_CREDENTIALS = _creds_path

# Crawler Settings
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
MAX_PAGES_PER_PDF = int(os.getenv("MAX_PAGES_PER_PDF", "1000"))

# Request Settings
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.0"))  # Delay between requests in seconds
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

# Output Settings
OUTPUT_DIR = BASE_DIR / "output"
CHUNKS_FILE = OUTPUT_DIR / "chunks.json"
LOG_FILE = OUTPUT_DIR / "crawler.log"

# Create output directory if it doesn't exist
OUTPUT_DIR.mkdir(exist_ok=True)
