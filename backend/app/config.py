import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(REPO_ROOT / ".env")


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./nagarnetra.db")
    model_path: str = os.getenv("MODEL_PATH", "models/pothole.onnx")
    confidence: float = float(os.getenv("CONFIDENCE", "0.2"))
    admin_key: str = os.getenv("ADMIN_KEY", "change-me")
    cloudinary_folder: str = os.getenv("CLOUDINARY_FOLDER", "nagarnetra")
    merge_radius_m: float = float(os.getenv("MERGE_RADIUS_M", "25"))


settings = Settings()
