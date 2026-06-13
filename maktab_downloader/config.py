import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


class Settings(BaseModel):
    # API endpoints
    BASE_URL: str = "https://maktabkhooneh.org"
    MY_COURSES_URL: str = "https://maktabkhooneh.org/api/v1/accounts/profile-courses/my_courses/"
    COURSE_OUTLINE_URL: str = "https://maktabkhooneh.org/api/v1/lms/courses/{course_id}/outline/"
    UNIT_DETAIL_URL: str = "https://maktabkhooneh.org/api/v1/lms/units/{unit_id}/"

    # Catalog, Course Public Landing, Actions, Enrollment & Reviews
    CATALOG_SEARCH_URL: str = "https://maktabkhooneh.org/api/v1/courses/categories/-/search/"
    COURSE_LANDING_URL: str = "https://maktabkhooneh.org/api/v1/courses/{course_slug_mk}/"
    COURSE_ACTIONS_URL: str = "https://maktabkhooneh.org/api/v1/courses/{course_slug_mk}/actions/"
    COURSE_ENROLL_URL: str = "https://maktabkhooneh.org/api/v1/courses/{course_slug_mk}/enroll/"
    COURSE_REVIEWS_URL: str = "https://maktabkhooneh.org/api/v1/courses/{course_slug_mk}/reviews/"

    # Database & Storage
    DB_PATH: Path = Field(default_factory=lambda: Path(os.getenv("DB_PATH", "maktabkhooneh.db")))
    DOWNLOAD_DIR: Path = Field(default_factory=lambda: Path(os.getenv("DOWNLOAD_DIR", "downloads")))

    # Authentication
    COOKIE_STRING: Optional[str] = Field(default_factory=lambda: os.getenv("MAKTAB_COOKIE_STRING"))
    SESSIONID: Optional[str] = Field(default_factory=lambda: os.getenv("MAKTAB_SESSIONID"))
    CSRFTOKEN: Optional[str] = Field(default_factory=lambda: os.getenv("MAKTAB_CSRFTOKEN"))
    BROWSER: Optional[str] = Field(default_factory=lambda: os.getenv("MAKTAB_BROWSER", "chrome"))

    # Concurrency & Networking
    MAX_CONCURRENT_REQUESTS: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_REQUESTS", "8")))
    MAX_CONCURRENT_DOWNLOADS: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3")))
    REQUEST_MIN_DELAY: float = Field(default_factory=lambda: float(os.getenv("REQUEST_MIN_DELAY_SECONDS", "0.0")))
    REQUEST_MAX_DELAY: float = Field(default_factory=lambda: float(os.getenv("REQUEST_MAX_DELAY_SECONDS", "0.05")))
    REQUEST_TIMEOUT: float = 20.0
    DOWNLOAD_TIMEOUT: float = 300.0
    CHUNK_SIZE: int = 1024 * 64  # 64 KB per chunk

    # Retry Settings
    MAX_RETRIES: int = 5
    RETRY_BACKOFF_MIN: float = 2.0
    RETRY_BACKOFF_MAX: float = 30.0

    # Default Preferences
    DEFAULT_QUALITY: str = Field(default_factory=lambda: os.getenv("DEFAULT_QUALITY", "1080p"))
    DOWNLOAD_CAPTIONS: bool = True
    DOWNLOAD_POSTERS: bool = True

    # Telegram Integration & Host Storage Management
    TELEGRAM_API_ID: Optional[int] = Field(default_factory=lambda: int(os.getenv("TELEGRAM_API_ID")) if os.getenv("TELEGRAM_API_ID") else None)
    TELEGRAM_API_HASH: Optional[str] = Field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH"))
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    TELEGRAM_SESSION_STRING: Optional[str] = Field(default_factory=lambda: os.getenv("TELEGRAM_SESSION_STRING"))
    TELEGRAM_SESSION_NAME: str = Field(default_factory=lambda: os.getenv("TELEGRAM_SESSION_NAME", "maktab_telethon"))
    TELEGRAM_TARGET_CHAT: Optional[str] = Field(default_factory=lambda: os.getenv("TELEGRAM_TARGET_CHAT", "me"))
    STORAGE_LIMIT_MB: float = Field(default_factory=lambda: float(os.getenv("STORAGE_LIMIT_MB", "2048.0")))  # Default 2GB limit

    # HTTP Headers template
    DEFAULT_HEADERS: dict = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,fa;q=0.8,tr;q=0.7",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
    }


settings = Settings()
