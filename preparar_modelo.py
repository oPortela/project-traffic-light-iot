"""Download and smoke-test the detector without opening the webcam."""
import os
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(__file__).resolve().parent / ".runtime"))

if __name__ == "__main__":
    Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(os.environ.get("YOLO_MODEL", "yolov8n.pt"))
    result = model.track(np.zeros((480, 640, 3), dtype=np.uint8), persist=True,
                         classes=[0], conf=0.5, imgsz=416,
                         tracker="bytetrack.yaml", verbose=False)
    assert len(result) == 1
    print("Detector e rastreador carregados com sucesso. Webcam não foi aberta.")
