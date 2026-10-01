import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "score_db")
    mongo_collection: str = os.getenv("MONGO_COLLECTION", "requirements")
    voyage_api_key: str = os.getenv("VOYAGE_API_KEY", "")
    voyage_model: str = os.getenv("VOYAGE_MODEL", "voyage-3.5")


settings = Settings()
