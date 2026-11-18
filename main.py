
import cv2
import time
import secrets
import os
import numpy as np

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI(title="FireGuardAI CV Engine")

API_KEY = os.getenv("CAMERA_API_KEY")

latest_frame = None
frames_received = 0
last_received = None


@app.get("/")
def home():
    return {
        "project": "FireGuardAI",
        "engine": "OpenCV",
        "status": "online"
    }


@app.get("/status")
def status():
    return {
        "engine": "online",
        "camera_connected": latest_frame is not None,
        "frames_received": frames_received,
        "last_received": last_received
    }


@app.post("/upload")
async def upload(request: Request):
    global latest_frame, frames_received, last_received

    key = request.headers.get("X-API-Key")

    if not API_KEY or not key or not secrets.compare_digest(key, API_KEY):
        raise HTTPException(401, "Invalid API key")

    data = await request.body()

    if not data or len(data) > 2_000_000:
        raise HTTPException(400, "Invalid image size")

    image = cv2.imdecode(
        np.frombuffer(data, dtype=np.uint8),
        cv2.IMREAD_COLOR
    )

    if image is None:
        raise HTTPException(400, "Invalid JPEG")

    cv2.putText(
        image,
        "FIREGUARDAI | OPENCV",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 100),
        2
    )

    success, encoded = cv2.imencode(".jpg", image)

    if not success:
        raise HTTPException(500, "Encoding failed")

    latest_frame = encoded.tobytes()
    frames_received += 1
    last_received = time.time()

    return {
        "success": True,
        "frames_received": frames_received
    }


@app.get("/stream")
async def stream(key: str):
    if not API_KEY or not secrets.compare_digest(key, API_KEY):
        raise HTTPException(401, "Invalid API key")

    async def generate():
        while True:
            frame = latest_frame

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame + b"\r\n"
                )

            import asyncio
            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
