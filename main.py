
import cv2
import time
import secrets
import os
import asyncio
import numpy as np

from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import (
    StreamingResponse,
    Response,
    HTMLResponse
)

app = FastAPI(title="FireGuardAI CV Engine")

API_KEY = os.getenv("CAMERA_API_KEY")

latest_frame = None
frames_received = 0
last_received = None

FRAME_TIMEOUT = 15


def verify_key(key):
    if (
        not API_KEY
        or not key
        or not secrets.compare_digest(key, API_KEY)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )


@app.get("/")
def home():
    return {
        "project": "FireGuardAI",
        "engine": "OpenCV",
        "status": "online",
        "version": "2.0"
    }


@app.get("/status")
def status():
    connected = (
        latest_frame is not None
        and last_received is not None
        and time.time() - last_received < FRAME_TIMEOUT
    )

    return {
        "engine": "online",
        "camera_connected": connected,
        "frames_received": frames_received,
        "last_received": last_received,
        "last_received_iso": (
            datetime.fromtimestamp(
                last_received, timezone.utc
            ).isoformat()
            if last_received else None
        )
    }


@app.post("/upload")
async def upload(request: Request):
    global latest_frame, frames_received, last_received

    verify_key(request.headers.get("X-API-Key"))

    data = await request.body()

    if not data or len(data) > 2_000_000:
        raise HTTPException(
            status_code=400,
            detail="Invalid image size"
        )

    image = cv2.imdecode(
        np.frombuffer(data, dtype=np.uint8),
        cv2.IMREAD_COLOR
    )

    if image is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid JPEG"
        )

    cv2.putText(
        image,
        "FIREGUARDAI | OPENCV",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 100),
        2
    )

    success, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 85]
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Encoding failed"
        )

    latest_frame = encoded.tobytes()
    frames_received += 1
    last_received = time.time()

    return {
        "success": True,
        "frames_received": frames_received,
        "image_size": len(latest_frame)
    }


# Latest JPEG endpoint
@app.get("/camera/latest")
def camera_latest(request: Request):

    verify_key(request.headers.get("X-API-Key"))

    if latest_frame is None:
        raise HTTPException(
            status_code=503,
            detail="No camera frame received yet"
        )

    return Response(
        content=latest_frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache"
        }
    )


# Browser preview page
@app.get("/preview", response_class=HTMLResponse)
def preview():

    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>FireGuardAI Camera</title>

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 20px;
    background: #101810;
    color: #eaffea;
    font-family: Arial, sans-serif;
}

.container {
    max-width: 850px;
    margin: auto;
}

h1 {
    color: #58e68a;
}

.camera {
    width: 100%;
    background: #080d08;
    border: 1px solid #315b3c;
    border-radius: 14px;
    overflow: hidden;
    min-height: 220px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.camera img {
    width: 100%;
    display: none;
}

#message {
    color: #9cae9c;
    padding: 25px;
    text-align: center;
}

.info {
    margin-top: 15px;
    padding: 15px;
    background: #1b281d;
    border-radius: 12px;
}

input, button {
    padding: 12px;
    border-radius: 8px;
    border: none;
    margin-top: 10px;
}

input {
    width: 100%;
}

button {
    background: #36d878;
    color: #08200f;
    font-weight: bold;
    cursor: pointer;
}

#status {
    color: #58e68a;
}

</style>
</head>

<body>
<div class="container">

<h1>🔥 FireGuardAI</h1>
<p>Online OpenCV Camera Preview</p>

<div class="camera">
    <img id="cameraImage">
    <div id="message">Enter your camera API key to connect.</div>
</div>

<div class="info">
    <div id="status">Disconnected</div>
    <div id="frames">Frames: --</div>
    <div id="updated">Last update: --</div>

    <input
        id="apiKey"
        type="password"
        placeholder="Enter CAMERA_API_KEY"
        autocomplete="off"
    >

    <button onclick="connectCamera()">Connect Camera</button>
</div>

</div>

<script>
let apiKey = "";
let timer = null;
let objectUrl = null;
let busy = false;

const img = document.getElementById("cameraImage");
const message = document.getElementById("message");

async function connectCamera() {

    apiKey = document.getElementById("apiKey").value;

    if (!apiKey) {
        alert("Enter your API key.");
        return;
    }

    if (timer) clearTimeout(timer);

    document.getElementById("status").textContent =
        "Connecting...";

    await refreshFrame();
}

async function refreshFrame() {

    if (busy) return;

    busy = true;

    try {

        const response = await fetch("/camera/latest", {
            headers: {
                "X-API-Key": apiKey
            },
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(
                response.status === 401
                ? "Invalid API key"
                : "Waiting for camera frames"
            );
        }

        const blob = await response.blob();

        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
        }

        objectUrl = URL.createObjectURL(blob);

        img.src = objectUrl;
        img.style.display = "block";
        message.style.display = "none";

        document.getElementById("status").textContent =
            "● Camera connected";

        const statusResponse = await fetch("/status", {
            cache: "no-store"
        });

        if (statusResponse.ok) {
            const data = await statusResponse.json();

            document.getElementById("frames").textContent =
                "Frames received: " + data.frames_received;

            document.getElementById("updated").textContent =
                "Last upload: " + (data.last_received_iso || "--");
        }

    } catch (error) {

        document.getElementById("status").textContent =
            "● " + error.message;

        if (error.message === "Invalid API key") {
            apiKey = "";
        }

        img.style.display = "none";
        message.style.display = "block";
        message.textContent = error.message;

    } finally {

        busy = false;
        timer = setTimeout(refreshFrame, 500);
    }
}
</script>

</body>
</html>
""")
    

# Existing authenticated MJPEG stream
@app.get("/stream")
async def stream(key: str):

    verify_key(key)

    async def generate():

        while True:

            frame = latest_frame

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame + b"\r\n"
                )

            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
