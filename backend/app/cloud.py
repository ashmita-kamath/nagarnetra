"""Everything Cloudinary: upload, privacy blur, smart crops, share cards, before/after."""

import io

import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

from .config import settings

cloudinary.reset_config()
cloudinary.config(secure=True)

PRIVACY = {"effect": "blur_faces:800"}
OPTIMISE = {"fetch_format": "auto", "quality": "auto"}


def is_configured() -> bool:
    cfg = cloudinary.config()
    return bool(cfg.cloud_name and cfg.api_key and cfg.api_secret)


def upload_image(data: bytes, tags: list, context: dict) -> dict:
    return cloudinary.uploader.upload(
        io.BytesIO(data),
        folder=settings.cloudinary_folder,
        resource_type="image",
        tags=tags,
        context=context,
    )


def _url(public_id: str, transformation: list) -> str:
    return cloudinary_url(public_id, transformation=transformation)[0]


def _layer_id(public_id: str) -> str:
    return public_id.replace("/", ":")


def image_urls(public_id: str) -> dict:
    return {
        "thumb": _url(public_id, [PRIVACY, {"width": 480, "height": 320, "crop": "fill", "gravity": "auto"}, OPTIMISE]),
        "full": _url(public_id, [PRIVACY, {"width": 1600, "crop": "limit"}, OPTIMISE]),
    }


def share_card_url(public_id: str, category: str, label: str, score: int, reports: int) -> str:
    text = f"{category.upper()}  |  Severity {label} {score} of 100  |  {reports} citizen report{'s' if reports != 1 else ''}"
    return _url(
        public_id,
        [
            PRIVACY,
            {"width": 1200, "height": 630, "crop": "fill", "gravity": "auto"},
            {
                "overlay": {"font_family": "Arial", "font_size": 40, "font_weight": "bold", "text": text},
                "color": "white",
                "background": "rgb:000000",
                "border": "20px_solid_rgb:000000",
                "gravity": "south_west",
                "x": 30,
                "y": 30,
            },
            {
                "overlay": {"font_family": "Arial", "font_size": 34, "font_weight": "bold", "text": "NagarNetra"},
                "color": "white",
                "background": "rgb:d62828",
                "border": "14px_solid_rgb:d62828",
                "gravity": "north_west",
                "x": 30,
                "y": 30,
            },
            OPTIMISE,
        ],
    )


def before_after_url(before_id: str, after_id: str) -> str:
    return _url(
        before_id,
        [
            PRIVACY,
            {"width": 600, "height": 400, "crop": "fill", "gravity": "auto"},
            {"width": 1200, "height": 400, "crop": "pad", "gravity": "west", "background": "white"},
            {"overlay": _layer_id(after_id), "width": 600, "height": 400, "crop": "fill", "gravity": "auto"},
            {"flags": "layer_apply", "gravity": "east"},
            {"overlay": {"font_family": "Arial", "font_size": 30, "font_weight": "bold", "text": "BEFORE"},
             "color": "white", "background": "rgb:d62828", "border": "10px_solid_rgb:d62828",
             "gravity": "north_west", "x": 16, "y": 16},
            {"overlay": {"font_family": "Arial", "font_size": 30, "font_weight": "bold", "text": "FIXED"},
             "color": "white", "background": "rgb:2a9d8f", "border": "10px_solid_rgb:2a9d8f",
             "gravity": "north_east", "x": 16, "y": 16},
            OPTIMISE,
        ],
    )
