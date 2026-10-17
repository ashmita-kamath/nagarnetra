"""Pothole detection with an open-weight YOLO11 model exported to ONNX.

Runs on onnxruntime + numpy only (no PyTorch), so it fits free-tier hosting.
If no model file is present the app still works: reports are saved and
severity falls back to a per-category baseline.
"""

import ast
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import BACKEND_DIR, settings

log = logging.getLogger("nagarnetra.detector")

_session = None
_input_name = None
_input_size = 640
_names: dict = {}

CATEGORY_KEYWORDS = (
    ("pothole", "pothole"),
    ("crack", "pothole"),
    ("garbage", "garbage"),
    ("trash", "garbage"),
    ("litter", "garbage"),
    ("waste", "garbage"),
)


class InvalidImage(Exception):
    pass


@dataclass
class DetectionResult:
    width: int
    height: int
    detections: list = field(default_factory=list)
    ai_used: bool = False


def _model_file() -> Path:
    path = Path(settings.model_path)
    return path if path.is_absolute() else BACKEND_DIR / path


def load_model() -> bool:
    global _session, _input_name, _input_size, _names
    path = _model_file()
    if not path.exists():
        log.warning("No model at %s - running without AI detection", path)
        return False
    try:
        import onnxruntime as ort

        _session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        inp = _session.get_inputs()[0]
        _input_name = inp.name
        if len(inp.shape) == 4 and isinstance(inp.shape[2], int):
            _input_size = inp.shape[2]
        meta = _session.get_modelmeta().custom_metadata_map
        if "names" in meta:
            _names = {int(k): str(v) for k, v in ast.literal_eval(meta["names"]).items()}
        log.info("Loaded model %s classes=%s", path.name, _names)
        return True
    except Exception:
        log.exception("Failed to load model %s", path)
        _session = None
        return False


def model_status() -> dict:
    return {
        "loaded": _session is not None,
        "path": settings.model_path,
        "classes": list(_names.values()),
    }


def _letterbox(img: Image.Image, size: int):
    w, h = img.size
    r = min(size / w, size / h)
    nw, nh = round(w * r), round(h * r)
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas.paste(resized, (px, py))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = np.ascontiguousarray(arr.transpose(2, 0, 1)[None])
    return arr, r, px, py


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list:
    x1, y1, x2, y2 = boxes.T
    areas = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou < iou_thr]
    return keep


def detect(data: bytes) -> DetectionResult:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage(str(exc)) from exc

    W, H = img.size
    if _session is None:
        return DetectionResult(W, H, [], False)

    x, r, px, py = _letterbox(img, _input_size)
    out = _session.run(None, {_input_name: x})[0]
    pred = out[0].T
    nc = len(_names) if _names else pred.shape[1] - 4
    boxes = pred[:, :4]
    cls_scores = pred[:, 4 : 4 + nc]
    cls = cls_scores.argmax(1)
    conf = cls_scores.max(1)

    mask = conf >= settings.confidence
    boxes, cls, conf = boxes[mask], cls[mask], conf[mask]
    if not len(conf):
        return DetectionResult(W, H, [], True)

    cx, cy, bw, bh = boxes.T
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
    xyxy[:, [0, 2]] -= px
    xyxy[:, [1, 3]] -= py
    xyxy /= r
    xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, W)
    xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, H)

    offset = cls[:, None].astype(np.float32) * 10000.0
    keep = _nms(xyxy + offset, conf, 0.45)[:50]

    dets = []
    for i in keep:
        x1, y1, x2, y2 = xyxy[i].tolist()
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        dets.append(
            {
                "label": _names.get(int(cls[i]), f"class_{int(cls[i])}"),
                "confidence": round(float(conf[i]), 3),
                "box": [round(x1 / W, 4), round(y1 / H, 4), round(x2 / W, 4), round(y2 / H, 4)],
            }
        )
    return DetectionResult(W, H, dets, True)


def infer_category(detections: list) -> str:
    for det in sorted(detections, key=lambda d: -d["confidence"]):
        label = det["label"].lower()
        for keyword, category in CATEGORY_KEYWORDS:
            if keyword in label:
                return category
    return "other"
