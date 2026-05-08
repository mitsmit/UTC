import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CHAT_MODEL = "gpt-4o"

# Chunk size in characters (~800 tokens). T&C sections rarely exceed this.
CHUNK_SIZE = 3000
# Overlap between consecutive chunks to avoid cutting mid-clause
CHUNK_OVERLAP = 200

# Similarity threshold for deciding if input is a T&C document (0–1)
TC_CONFIDENCE_THRESHOLD = 0.6

API_HOST = "0.0.0.0"
API_PORT = 8002          # 8000 is used by personal-agent

REQUEST_TIMEOUT = 20     # seconds for URL fetching
