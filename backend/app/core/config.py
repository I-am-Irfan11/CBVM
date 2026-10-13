import json
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173", "https://cbvm.vercel.app",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_env: Literal["development", "production", "test"] = "development"
    database_mode: Literal["memory", "mongodb"] = "mongodb"
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "gatelog"
    use_mock_ai: bool = False
    seed_on_startup: bool = False
    yolo_model_path: str = "models/license_plate.pt"
    ocr_confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    duplicate_cooldown_seconds: int = Field(default=30, ge=0)
    video_source: Literal["mock", "rtsp", "mp4", "webcam"] = "mock"
    rtsp_url: str = ""
    video_file: str = ""
    webcam_index: int = 0
    frame_sample_rate: float = Field(default=2, gt=0, le=60)
    run_video_worker: bool = False
    camera_id: str = "main-gate-in"
    cors_origins: Annotated[list[str], NoDecode] = DEFAULT_CORS_ORIGINS
    campus_timezone: str = "Asia/Kolkata"
    retention_days: int = Field(default=90, ge=1)
    jwt_secret_key: str | None = Field(default=None, min_length=32)
    jwt_access_token_expire_minutes: int = Field(default=60, ge=1, le=1440)
    cookie_secure: bool = False
    seed_operational_data: bool = False
    firebase_project_id: str = ""
    firebase_allowed_emails: str = ""
    firebase_allowed_domains: str = ""
    firebase_allowed_uids: str = ""
    firebase_admin_emails: str = ""
    r2_endpoint_url: str = ""
    retain_scan_images: bool = False
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_presigned_url_expiry_seconds: int = Field(default=300, ge=30, le=3600)
    enable_demo_reset: bool = False
    # Development-only bypass. Production startup rejects this setting.
    demo_open_access: bool = False
    reconnect_delay_seconds: float = Field(default=1, gt=0, le=60)

    @field_validator("campus_timezone")
    @classmethod
    def timezone_exists(cls, value):
        ZoneInfo(value)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if value is None:
            return DEFAULT_CORS_ORIGINS
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return DEFAULT_CORS_ORIGINS
            if raw.startswith("["):
                value = json.loads(raw)
            else:
                value = raw.split(",")
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("CORS_ORIGINS must be a JSON array or comma-separated origins")
        origins = [str(origin).strip() for origin in value if str(origin).strip()]
        return origins or DEFAULT_CORS_ORIGINS
