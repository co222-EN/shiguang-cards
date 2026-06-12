from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


class Settings:
    app_name: str = os.getenv("APP_NAME", "Shiguang Cards")
    app_passcode: str = os.getenv("APP_PASSCODE", "")
    session_secret: str = os.getenv("SESSION_SECRET", "dev-session-secret-change-me")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local").lower()
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_storage_bucket: str = os.getenv("SUPABASE_STORAGE_BUCKET", "moment-photos")
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "12"))


settings = Settings()
