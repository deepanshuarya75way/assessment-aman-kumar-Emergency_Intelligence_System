"""
Centralized configuration — all settings read from environment variables.
"""
import os
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import ClassVar

load_dotenv()

from pydantic_settings import BaseSettings

class Settings(BaseModel):
    # ── Server ──
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Database (MongoDB Atlas) ──
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "eis_db")

    # ── Cache (Upstash Redis) ──
    UPSTASH_REDIS_REST_URL: str = os.getenv("UPSTASH_REDIS_REST_URL", "")
    UPSTASH_REDIS_REST_TOKEN: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

    # ── ML Models ──
    YOLO_MODEL_PATH: str = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
    YOLO_CONFIDENCE: float = float(os.getenv("YOLO_CONFIDENCE", "0.35"))

    # ── Grid / Zone ──
    GRID_ROWS: int = int(os.getenv("GRID_ROWS", "3"))
    GRID_COLS: int = int(os.getenv("GRID_COLS", "3"))

    # ── Thresholds ──
    DENSITY_WARNING: int = int(os.getenv("DENSITY_WARNING", "5"))
    DENSITY_CRITICAL: int = int(os.getenv("DENSITY_CRITICAL", "10"))

    # ── Video ──
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    STREAM_FPS: int = int(os.getenv("STREAM_FPS", "10"))

    # ___ Forecasting ___

    FORECAST_HORIZONS : ClassVar[list[int]] = [5,10,15]

    FORECAST_HISTORY_SIZE : ClassVar[int] = 60

    FORECAST_MIN_SAMPLES : ClassVar[int] = 5

    FORECAST_SAMPLE_INTERVAL : ClassVar[int] = 5

    PREDICTIVE_ALERT : ClassVar[bool] = True

    FORECAST_THRESHOLD_CHANGE : ClassVar[int] = 2

    class Config:
        env_file = ".env"


settings = Settings()
