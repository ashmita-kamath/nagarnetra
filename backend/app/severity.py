"""Severity (how bad is it) and priority (what to fix first)."""

from datetime import datetime, timezone

BASELINE = {
    "pothole": 45,
    "waterlogging": 50,
    "garbage": 35,
    "streetlight": 30,
    "other": 25,
}


def label_for(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def score(category: str, detections: list) -> tuple[int, str]:
    if not detections:
        s = BASELINE.get(category, 25)
        return s, label_for(s)

    area = sum((d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) for d in detections)
    area = min(1.0, area)
    count = len(detections)
    mean_conf = sum(d["confidence"] for d in detections) / count

    s = 30 + 40 * min(1.0, area / 0.25) + 15 * min(1.0, (count - 1) / 3) + 15 * mean_conf
    s = int(round(min(100.0, s)))
    return s, label_for(s)


def priority(severity_score: int, reports_count: int, created_at: datetime, status: str) -> int:
    if status != "open":
        return 0
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - created_at).total_seconds() / 86400
    crowd = min(30, 6 * (reports_count - 1))
    waiting = min(20, int(age_days * 2))
    return severity_score + crowd + waiting
