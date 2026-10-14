"""Relay control agent.

Small HTTP service that owns the per-game FFmpeg process which pulls a stream
from the local SRS relay and pushes it to a YouTube RTMP ingest endpoint.

It is intentionally kept dependency-light (FastAPI + ffmpeg) so it can run in a
container alongside SRS, on the same Docker network.
"""
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
SRS_RTMP_BASE = os.environ.get("SRS_RTMP_BASE", "rtmp://srs:1935").rstrip("/")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
LOG_DIR = os.environ.get("RELAY_LOG_DIR", "/tmp/relay-logs")

os.makedirs(LOG_DIR, exist_ok=True)

app = FastAPI(title="DiamondManager Relay Agent", version="1.0.0")


class RelayStartRequest(BaseModel):
    stream_id: str
    ingest_url: str
    stream_key: str
    source_url: Optional[str] = None


class RelayStopRequest(BaseModel):
    stream_id: str


class RelayJob:
    def __init__(self, stream_id: str, process: subprocess.Popen, log_path: str):
        self.stream_id = stream_id
        self.process = process
        self.log_path = log_path
        self.started_at = time.time()

    def to_dict(self) -> Dict:
        return {
            "stream_id": self.stream_id,
            "running": self.process.poll() is None,
            "pid": self.process.pid,
            "started_at": datetime.fromtimestamp(self.started_at, tz=timezone.utc).isoformat(),
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "exit_code": self.process.poll(),
            "log_path": self.log_path,
        }


_jobs: Dict[str, RelayJob] = {}
_lock = threading.Lock()


def _require_token(token: Optional[str]):
    if not RELAY_TOKEN:
        raise HTTPException(status_code=500, detail="Relay token not configured")
    if token != RELAY_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid relay token")


def _build_command(source_url: str, ingest_url: str, stream_key: str) -> list:
    target = f"{ingest_url.rstrip('/')}/{stream_key}"
    return [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel", "warning",
        "-nostdin",
        "-i", source_url,
        "-c", "copy",
        "-f", "flv",
        target,
    ]


@app.get("/health")
def health():
    return {"status": "ok", "active_streams": len(_jobs)}


@app.get("/relay/{stream_id:path}")
def relay_status(stream_id: str, x_relay_token: Optional[str] = Header(None)):
    _require_token(x_relay_token)
    job = _jobs.get(stream_id)
    if not job:
        return {"stream_id": stream_id, "running": False, "exists": False}
    return {**job.to_dict(), "exists": True}


@app.post("/relay/start")
def relay_start(req: RelayStartRequest, x_relay_token: Optional[str] = Header(None)):
    _require_token(x_relay_token)
    if not shutil.which(FFMPEG_BIN):
        raise HTTPException(status_code=500, detail="ffmpeg not available on relay host")

    with _lock:
        existing = _jobs.get(req.stream_id)
        if existing and existing.process.poll() is None:
            return {"status": "already_running", **existing.to_dict()}
        if not req.ingest_url or not req.stream_key:
            raise HTTPException(status_code=400, detail="ingest_url and stream_key are required")

        source_url = req.source_url or f"{SRS_RTMP_BASE}/{req.stream_id}"
        command = _build_command(source_url, req.ingest_url, req.stream_key)
        safe_name = req.stream_id.replace("/", "_")
        log_path = os.path.join(LOG_DIR, f"{safe_name}.log")
        log_file = open(log_path, "ab", buffering=0)
        try:
            process = subprocess.Popen(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        except Exception as exc:  # noqa: BLE001
            log_file.close()
            raise HTTPException(status_code=500, detail=f"Failed to start ffmpeg: {exc}")

        job = RelayJob(req.stream_id, process, log_path)
        _jobs[req.stream_id] = job
        return {"status": "started", **job.to_dict()}


@app.post("/relay/stop")
def relay_stop(req: RelayStopRequest, x_relay_token: Optional[str] = Header(None)):
    _require_token(x_relay_token)
    with _lock:
        job = _jobs.get(req.stream_id)
        if not job:
            return {"status": "not_running", "stream_id": req.stream_id}
        if job.process.poll() is None:
            job.process.terminate()
            try:
                job.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                job.process.kill()
                job.process.wait(timeout=5)
        del _jobs[req.stream_id]
        return {"status": "stopped", "stream_id": req.stream_id}


@app.on_event("shutdown")
def shutdown():
    with _lock:
        for job in _jobs.values():
            if job.process.poll() is None:
                job.process.terminate()
        _jobs.clear()
