"""
API Endpoints — REST + WebSocket routes for the Emergency Intelligence System.

Routes:
  GET  /status            → system health
  GET  /video-stream      → MJPEG stream (processed via YOLO)
  POST /detect            → run detection on a single uploaded image
  GET  /heatmap           → latest density heatmap
  GET  /alerts            → recent alert history
  POST /upload-video      → upload a video file as stream source
  POST /connect-stream    → connect to RTSP/HTTP live stream
  POST /process-video     → upload + frame-by-frame analysis with WS push
  POST /set-source        → switch input source (mock/webcam)
  POST /simulate          → trigger a demo scenario
  POST /simulate-alert    → push a single simulated alert
  WS   /ws/alerts         → real-time alert + heatmap push
"""
import asyncio
import time
import os
import cv2
import numpy as np
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.websocket_manager import ws_manager
from app.services.ml_pipeline import ml_pipeline
from app.services.storage import storage_service
from app.services.decision_engine import decision_engine
from app.services.simulation import simulation_service
from app.utils.video_feed import video_feed

from app.services.forecasting import forecasting_service

router = APIRouter()

# ─────────────────────────────── HEALTH ───────────────────────────────

@router.get("/status")
async def get_status():
    storage_health = storage_service.health()
    return {
        "status": "online",
        "uptime": time.time(),
        "services": {
            "yolo": "ready",
            "video_source": video_feed.source_type,
            **storage_health,
        },
        "websocket_clients": ws_manager.count,
        "grid": f"{settings.GRID_ROWS}x{settings.GRID_COLS}",
    }

# ─────────────────────────────── ALERTS ───────────────────────────────

@router.get("/alerts")
async def get_alerts():
    alerts = await storage_service.get_recent_alerts(50)
    return {"alerts": alerts}

# ─────────────────────────────── HEATMAP ──────────────────────────────

@router.get("/heatmap")
async def get_heatmap():
    heatmap = await storage_service.get_cached_heatmap()
    return {"heatmap": heatmap or {}}

# ─────────────────────────── SINGLE DETECT ────────────────────────────

@router.post("/detect")
async def detect_frame(file: UploadFile = File(...)):
    """Upload an image and run person detection on it."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"error": "Could not decode image"}

    result = ml_pipeline.detect_single(frame)
    # Update live feed to show this image
    video_feed.set_image(frame)
    await storage_service.log_event("detect", f"people={result['total_people']}")
    return result

# ─────────────────────────── VIDEO UPLOAD ─────────────────────────────

@router.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file to use as the live stream source."""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(path, "wb") as f:
        content = await file.read()
        f.write(content)

    video_feed.set_video_file(path)
    await storage_service.log_event("upload", f"file={file.filename}")
    return {"message": f"Video uploaded: {file.filename}", "source": video_feed.source_type}


@router.get("/forecasts")
async def get_forecasts():
    return {
        "forecasts": forecasting_service.get_latest()
    }

@router.get("forecasts/history")
async def get_forecast_history():
    forecasts = await storage_service.get_recent_forecasts(50)
    return {
        "forecasts" : forecasts
    }


# ──────────────────────── RTSP / URL STREAM ───────────────────────────

class ConnectStreamRequest(BaseModel):
    url: str  # rtsp://... or http://... stream URL


@router.post("/connect-stream")
async def connect_stream(req: ConnectStreamRequest):
    """Connect to an RTSP or HTTP video stream URL."""
    video_feed.set_rtsp(req.url)
    source = video_feed.source_type
    if source == "rtsp":
        await storage_service.log_event("stream_connect", f"url={req.url}")
        return {"message": f"Connected to stream: {req.url}", "source": source}
    else:
        return {"error": "Failed to connect to stream — falling back to mock", "source": source}

# ──────────────────── FRAME-BY-FRAME VIDEO PROCESS ────────────────────

@router.post("/process-video")
async def process_video(file: UploadFile = File(...)):
    """
    Upload a video file and process it frame-by-frame.
    Results are broadcast via WebSocket in real time and a summary is returned.
    """
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, f"proc_{file.filename}")
    with open(path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Update live feed source to this video
    video_feed.set_video_file(path)

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"error": "Could not open video file"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Process at max 10 FPS — skip frames if source FPS is higher
    skip = max(1, int(fps / settings.STREAM_FPS))

    frame_idx = 0
    processed_count = 0
    all_alerts = []
    peak_density = {}
    total_people_sum = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        if frame_idx % skip != 0:
            continue

        _, densities, alerts = ml_pipeline.process_frame(frame)
        total_people = sum(densities.values())
        total_people_sum += total_people
        processed_count += 1

        # Track peak density per zone
        for zone, count in densities.items():
            if count > peak_density.get(zone, 0):
                peak_density[zone] = count

        # Persist and broadcast alerts
        for alert in alerts:
            await storage_service.save_alert(alert)
            all_alerts.append(alert)
        if alerts:
            await ws_manager.broadcast({"type": "alerts", "data": alerts})

        # Broadcast heatmap for this frame
        await storage_service.cache_heatmap(densities)
        await ws_manager.broadcast({
            "type": "heatmap", "data": densities,
        })
        await ws_manager.broadcast({
            "type": "video_progress",
            "data": {
                "frame": frame_idx,
                "total_frames": total_frames,
                "people": total_people,
            }
        })

        # Yield control so WS messages flush
        await asyncio.sleep(0)

    cap.release()

    avg_people = total_people_sum / max(processed_count, 1)
    await storage_service.log_event("process_video", f"file={file.filename}, frames={processed_count}")

    return {
        "message": f"Processed {processed_count} frames from {file.filename}",
        "total_frames_read": frame_idx,
        "frames_processed": processed_count,
        "average_people": round(avg_people, 1),
        "peak_density": peak_density,
        "total_alerts": len(all_alerts),
        "alerts": all_alerts[-20:],  # last 20
    }

# ─────────────────────── SOURCE SWITCHING ─────────────────────────────

class SetSourceRequest(BaseModel):
    source: str  # "mock" | "webcam"


@router.post("/set-source")
async def set_source(req: SetSourceRequest):
    """Switch the video feed source (mock or webcam)."""
    if req.source == "mock":
        video_feed.set_mock()
    elif req.source == "webcam":
        video_feed.set_webcam(0)
    else:
        return {"error": f"Unknown source: {req.source}"}
    await storage_service.log_event("set_source", f"source={req.source}")
    return {"message": f"Source set to {req.source}", "source": video_feed.source_type}

# ─────────────────────────── VIDEO STREAM ─────────────────────────────

def _stream_generator():
    """Synchronous generator that yields MJPEG frames."""
    delay = 1.0 / settings.STREAM_FPS
    while True:
        frame = video_feed.get_frame()
        annotated, densities, alerts = ml_pipeline.process_frame(frame)

        # Encode frame
        _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')

        # Push data through the event loop (fire-and-forget from sync context)
        try:
            loop = asyncio.get_event_loop()
            if alerts:
                for alert in alerts:
                    loop.create_task(storage_service.save_alert(alert))
                loop.create_task(ws_manager.broadcast({"type": "alerts", "data": alerts}))
            loop.create_task(storage_service.cache_heatmap(densities))
            loop.create_task(ws_manager.broadcast({"type": "heatmap", "data": densities}))
        except RuntimeError:
            pass

        import time as _t
        _t.sleep(delay)


@router.get("/video-stream")
async def video_stream():
    return StreamingResponse(
        _stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

# ─────────────────────────── SIMULATION ───────────────────────────────

class SimulateRequest(BaseModel):
    scenario: str = "normal"  # normal | crowded | panic


@router.post("/simulate")
async def simulate(req: SimulateRequest):
    """Trigger a demo scenario and broadcast alerts."""
    result = simulation_service.generate_scenario(req.scenario)
    for alert in result["alerts"]:
        await storage_service.save_alert(alert)
    await storage_service.cache_heatmap(result["zone_densities"])

    # Broadcast to WS clients
    if result["alerts"]:
        await ws_manager.broadcast({"type": "alerts", "data": result["alerts"]})
    await ws_manager.broadcast({"type": "heatmap", "data": result["zone_densities"]})

    await storage_service.log_event("simulate", f"scenario={req.scenario}")
    return result


class SimAlertRequest(BaseModel):
    zone: str = "Zone_1_1"
    level: str = "warning"


@router.post("/simulate-alert")
async def simulate_alert(req: SimAlertRequest):
    """Push a single custom simulated alert."""
    alert = decision_engine.simulate_alert(req.zone, req.level)
    await storage_service.save_alert(alert)
    await ws_manager.broadcast({"type": "alerts", "data": [alert]})
    return {"alert": alert}

# ─────────────────────────── WEBSOCKET ────────────────────────────────

@router.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    await storage_service.log_event("ws_connect", f"clients={ws_manager.count}")
    try:
        while True:
            data = await websocket.receive_text()
            # Handle client commands (manual overrides, etc.)
            if data == "ping":
                await ws_manager.send_personal(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        await storage_service.log_event("ws_disconnect", f"clients={ws_manager.count}")
