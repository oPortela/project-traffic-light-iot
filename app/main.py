import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.controller import Controller

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".runtime"))
controller = Controller()
lock = threading.RLock()
stop = threading.Event()
state = {"mode": "demo", "running": False, "presence": False, "ids": [],
         "seen_at": 0, "camera_status": "desligada", "error": None,
         "roi": [0.2, 0.15, 0.8, 0.95], "generation": 0}
frame = None


class Command(BaseModel):
    action: str
    mode: str = "demo"
    presence: bool = False


class Configuration(BaseModel):
    wait: float = Field(default=10, ge=1, le=60)
    crossing: float = Field(default=8, ge=2, le=60)
    roi: list[float] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_roi(self):
        x1, y1, x2, y2 = self.roi
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("Área de espera inválida")
        return self


def camera_loop():
    global frame
    cap = model = None
    active_generation = -1
    try:
        while not stop.is_set():
            with lock:
                enabled = state["running"] and state["mode"] == "camera"
                generation = state["generation"]
                roi = state["roi"][:]
            if not enabled:
                if cap is not None:
                    cap.release()
                    cap = None
                stop.wait(0.1)
                continue
            try:
                import cv2
                if model is None:
                    with lock:
                        state["camera_status"] = "carregando modelo"
                    Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
                    from ultralytics import YOLO
                    model = YOLO(os.environ.get("YOLO_MODEL", "yolov8n.pt"))
                if cap is None:
                    cap = cv2.VideoCapture(int(os.environ.get("CAMERA_INDEX", "0")))
                    if not cap.isOpened():
                        raise RuntimeError("Não foi possível abrir a webcam. Feche outros apps que usam a câmera e confira as permissões do Windows.")
                if generation != active_generation:
                    if getattr(model, "predictor", None) is not None:
                        for tracker in getattr(model.predictor, "trackers", []):
                            tracker.reset()
                    active_generation = generation
                ok, img = cap.read()
                if not ok:
                    raise RuntimeError("A webcam parou de enviar imagens. Reinicie a câmera.")
                h, w = img.shape[:2]
                if w > 800:
                    img = cv2.resize(img, (800, int(h * 800 / w)))
                    h, w = img.shape[:2]
                result = model.track(img, persist=True, classes=[0], conf=0.5,
                                     imgsz=416, tracker="bytetrack.yaml", verbose=False)[0]
                ids = []
                if result.boxes is not None and result.boxes.id is not None:
                    for box, identity in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.id.int().cpu().tolist()):
                        x1, y1, x2, y2 = box
                        # Bottom center approximates where a pedestrian touches the ground.
                        px, py = (x1 + x2) / (2 * w), y2 / h
                        inside = roi[0] <= px <= roi[2] and roi[1] <= py <= roi[3]
                        if inside:
                            ids.append(identity)
                        color = (130, 220, 70) if inside else (180, 180, 180)
                        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        cv2.putText(img, f"Pessoa {identity}", (int(x1), max(20, int(y1)-8)), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
                cv2.rectangle(img, (int(roi[0]*w), int(roi[1]*h)), (int(roi[2]*w), int(roi[3]*h)), (255, 190, 60), 2)
                ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                with lock:
                    if state["generation"] == generation and state["running"] and state["mode"] == "camera":
                        state.update(ids=ids, seen_at=time.monotonic(), camera_status="ativa", error=None)
                        if ok:
                            frame = jpg.tobytes()
            except Exception as exc:
                logging.exception("Camera failure")
                with lock:
                    if state["generation"] == generation:
                        state.update(running=False, ids=[], error=str(exc), camera_status="erro")
                        controller.reset()
                if cap is not None:
                    cap.release()
                    cap = None
                stop.wait(0.2)
    finally:
        if cap is not None:
            cap.release()


def tick_loop():
    while not stop.wait(0.05):
        with lock:
            now = time.monotonic()
            ids = []
            if state["running"]:
                if state["mode"] == "demo":
                    ids = ["demo"] if state["presence"] else []
                elif now - state["seen_at"] < 1:
                    ids = state["ids"]
                controller.update(now, ids)


@asynccontextmanager
async def lifespan(app):
    stop.clear()
    threads = [threading.Thread(target=fn, daemon=True) for fn in (camera_loop, tick_loop)]
    for thread in threads:
        thread.start()
    yield
    stop.set()
    for thread in threads:
        thread.join(timeout=2)


app = FastAPI(title="Travessia · Simulador IoT", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static/index.html")


@app.get("/api/state")
def snapshot():
    with lock:
        return {**controller.snapshot(time.monotonic()), **state,
                "crossing_duration": controller.settings.crossing}


@app.post("/api/control")
def control(command: Command):
    global frame
    with lock:
        if command.action == "presence":
            state["presence"] = command.presence
        elif command.action in ("start", "stop", "reset"):
            if command.mode not in ("demo", "camera"):
                raise HTTPException(400, "Modo inválido")
            controller.reset()
            state.update(running=command.action == "start", mode=command.mode,
                         presence=False, ids=[], seen_at=0, error=None,
                         camera_status="iniciando" if command.action == "start" and command.mode == "camera" else "desligada",
                         generation=state["generation"] + 1)
            frame = None
        else:
            raise HTTPException(400, "Ação inválida")
    return snapshot()


@app.post("/api/config")
def configure(config: Configuration):
    with lock:
        if state["running"]:
            raise HTTPException(409, "Pare a simulação antes de alterar as configurações.")
        controller.settings.wait = config.wait
        controller.settings.crossing = config.crossing
        state["roi"] = config.roi
        controller.reset()
    return snapshot()


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(snapshot())
            await asyncio.sleep(0.15)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass


@app.get("/video")
async def video():
    async def frames():
        while not stop.is_set():
            with lock:
                data = frame
            if data:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(0.1)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})
