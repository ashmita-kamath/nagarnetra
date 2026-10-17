import logging
import math
import secrets
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from . import cloud, detector, severity
from .config import REPO_ROOT, settings
from .db import Report, SessionLocal, init_db, utcnow

logging.basicConfig(level=logging.INFO)

CATEGORIES = {"pothole", "garbage", "streetlight", "waterlogging", "other"}
MAX_BYTES = 10 * 1024 * 1024
FRONTEND_DIR = REPO_ROOT / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    detector.load_model()
    yield


app = FastAPI(title="NagarNetra API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def _iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def serialize(r: Report) -> dict:
    urls = cloud.image_urls(r.image_public_id)
    data = {
        "id": r.id,
        "created_at": _iso(r.created_at),
        "lat": r.lat,
        "lng": r.lng,
        "category": r.category,
        "description": r.description,
        "image_url": urls["full"],
        "thumb_url": urls["thumb"],
        "share_url": cloud.share_card_url(
            r.image_public_id, r.category, r.severity_label, r.severity_score, r.reports_count
        ),
        "detections": r.detections or [],
        "ai_used": r.ai_used,
        "severity_score": r.severity_score,
        "severity_label": r.severity_label,
        "reports_count": r.reports_count,
        "priority": severity.priority(r.severity_score, r.reports_count, r.created_at, r.status),
        "status": r.status,
        "resolved_at": _iso(r.resolved_at),
        "after_url": None,
        "comparison_url": None,
    }
    if r.after_public_id:
        data["after_url"] = cloud.image_urls(r.after_public_id)["full"]
        data["comparison_url"] = cloud.before_after_url(r.image_public_id, r.after_public_id)
    return data


async def _read_image(image: UploadFile) -> bytes:
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(415, "Please upload an image file.")
    data = await image.read()
    if not data:
        raise HTTPException(400, "The image is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 10 MB.")
    return data


def _require_cloudinary():
    if not cloud.is_configured():
        raise HTTPException(503, "Cloudinary is not configured. Set CLOUDINARY_URL in .env.")


@app.get("/api/health")
def health():
    return {"ok": True, "cloudinary": cloud.is_configured(), "model": detector.model_status()}


@app.post("/api/reports", status_code=201)
async def create_report(
    image: UploadFile = File(...),
    lat: float = Form(...),
    lng: float = Form(...),
    category: str = Form("auto"),
    description: str = Form(""),
):
    _require_cloudinary()
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(422, "Invalid location.")
    data = await _read_image(image)

    try:
        result = await run_in_threadpool(detector.detect, data)
    except detector.InvalidImage:
        raise HTTPException(400, "Could not read that image.")

    category = (category or "auto").strip().lower()
    if category not in CATEGORIES:
        category = detector.infer_category(result.detections)
    score, label = severity.score(category, result.detections)
    description = (description or "").strip()[:500]

    with SessionLocal() as db:
        deg = settings.merge_radius_m / 111_000 * 2
        nearby = db.scalars(
            select(Report).where(
                Report.status == "open",
                Report.category == category,
                Report.lat.between(lat - deg, lat + deg),
                Report.lng.between(lng - deg, lng + deg),
            )
        ).all()
        for existing in nearby:
            if haversine_m(lat, lng, existing.lat, existing.lng) <= settings.merge_radius_m:
                existing.reports_count += 1
                if score > existing.severity_score:
                    existing.severity_score, existing.severity_label = score, label
                db.commit()
                return {"merged": True, "report": serialize(existing)}

        try:
            upload = await run_in_threadpool(
                cloud.upload_image,
                data,
                ["nagarnetra", category, f"severity-{label.lower()}"],
                {"category": category, "severity": label, "lat": f"{lat:.6f}", "lng": f"{lng:.6f}"},
            )
        except Exception as exc:
            logging.exception("Cloudinary upload failed")
            raise HTTPException(502, f"Image upload failed: {exc}")

        report = Report(
            lat=lat,
            lng=lng,
            category=category,
            description=description,
            image_public_id=upload["public_id"],
            image_width=upload.get("width") or result.width,
            image_height=upload.get("height") or result.height,
            detections=result.detections,
            ai_used=result.ai_used,
            severity_score=score,
            severity_label=label,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return {"merged": False, "report": serialize(report)}


@app.get("/api/reports")
def list_reports(
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    sort: str = Query("priority", pattern="^(priority|recent)$"),
    limit: int = Query(200, ge=1, le=1000),
):
    with SessionLocal() as db:
        q = select(Report)
        if status != "all":
            q = q.where(Report.status == status)
        rows = db.scalars(q.order_by(Report.created_at.desc()).limit(limit)).all()
        items = [serialize(r) for r in rows]
    if sort == "priority":
        items.sort(key=lambda x: (x["status"] != "open", -x["priority"]))
    return items


@app.get("/api/reports/{report_id}")
def get_report(report_id: int):
    with SessionLocal() as db:
        r = db.get(Report, report_id)
        if not r:
            raise HTTPException(404, "Report not found.")
        return serialize(r)


@app.post("/api/reports/{report_id}/upvote")
def upvote(report_id: int):
    with SessionLocal() as db:
        r = db.get(Report, report_id)
        if not r:
            raise HTTPException(404, "Report not found.")
        if r.status != "open":
            raise HTTPException(409, "This issue is already resolved.")
        r.reports_count += 1
        db.commit()
        return serialize(r)


@app.post("/api/reports/{report_id}/resolve")
async def resolve(
    report_id: int,
    image: UploadFile = File(...),
    x_admin_key: Optional[str] = Header(None),
):
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(401, "Wrong admin key.")
    _require_cloudinary()
    data = await _read_image(image)
    with SessionLocal() as db:
        r = db.get(Report, report_id)
        if not r:
            raise HTTPException(404, "Report not found.")
        upload = await run_in_threadpool(
            cloud.upload_image, data, ["nagarnetra", r.category, "resolved"], {"report_id": str(r.id)}
        )
        r.after_public_id = upload["public_id"]
        r.status = "resolved"
        r.resolved_at = utcnow()
        db.commit()
        return serialize(r)


@app.get("/api/stats")
def stats():
    with SessionLocal() as db:
        total = db.scalar(select(func.count(Report.id))) or 0
        open_n = db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
        high = db.scalar(
            select(func.count(Report.id)).where(Report.status == "open", Report.severity_label == "High")
        ) or 0
        citizens = db.scalar(select(func.coalesce(func.sum(Report.reports_count), 0))) or 0
        by_cat = dict(db.execute(select(Report.category, func.count(Report.id)).group_by(Report.category)).all())
    return {
        "total": total,
        "open": open_n,
        "resolved": total - open_n,
        "high_open": high,
        "citizen_reports": int(citizens),
        "by_category": by_cat,
    }


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
