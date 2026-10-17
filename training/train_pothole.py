"""Train an open-weight YOLO11 pothole detector and export it to ONNX.

Run in Google Colab (free GPU: Runtime > Change runtime type > T4 GPU).
Cell 1:
    !pip install -q ultralytics
Cell 2:
    !python train_pothole.py
Then download runs/detect/train/weights/best.onnx and save it as
backend/models/pothole.onnx in the repo.

Dataset: Ultralytics' open pothole dataset (pothole-seg.yaml, auto-downloads).
Its polygon labels are converted to boxes automatically for detection training.
"""

from ultralytics import YOLO

EPOCHS = 40
IMGSZ = 640

model = YOLO("yolo11n.pt")
results = model.train(data="pothole-seg.yaml", epochs=EPOCHS, imgsz=IMGSZ, batch=16, patience=10)

best = YOLO(f"{results.save_dir}/weights/best.pt")
metrics = best.val(data="pothole-seg.yaml")
print("mAP50:", round(metrics.box.map50, 3), "mAP50-95:", round(metrics.box.map, 3))

onnx_path = best.export(format="onnx", imgsz=IMGSZ, opset=12, simplify=True)
print("Exported:", onnx_path)
