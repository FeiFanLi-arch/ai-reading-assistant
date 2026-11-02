"""Environment-driven server settings. Secrets never leave the server."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("DB_PATH", str(ROOT / "data" / "reader.db"))
    ai_mode: str = os.getenv("AI_MODE", "auto").lower()
    api_key: str = os.getenv("AI_API_KEY", "")
    base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model: str = os.getenv("AI_MODEL", "gpt-4.1-mini")
    access_token: str = os.getenv("APP_ACCESS_TOKEN", "")
    max_text_length: int = 100_000
    ai_context_chars: int = 32_000
    request_timeout: int = 90

    @property
    def mode(self) -> str:
        return "ai" if self.ai_mode == "ai" or (self.ai_mode == "auto" and self.api_key) else "demo"


settings = Settings()
