"""API routes — trigger sync jobs, check status, download output files."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import settings
from workers.crm_writer import OUTPUT_DIR
from workers.sync_worker import run_sync_job

router = APIRouter()


def _check_auth(authorization: str) -> None:
    expected = f"Bearer {settings.axis_crm_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid token")


class TriggerRequest(BaseModel):
    adviser_id: str
    portal_id: str
    portal_login_url: str
    portal_base_url: str
    secret_ref: str
    twilio_number: str | None = None
    session_ttl_hours: int = 12


class TriggerResponse(BaseModel):
    task_id: str
    status: str = "queued"


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_sync(
    req: TriggerRequest,
    authorization: str = Header(...),
):
    """Manually trigger a sync job for a specific adviser + portal."""
    _check_auth(authorization)

    result = run_sync_job.apply_async(
        kwargs=req.model_dump(),
        queue=f"portal_{req.portal_id}",
    )

    return TriggerResponse(task_id=result.id)


@router.get("/{task_id}")
async def get_job_status(
    task_id: str,
    authorization: str = Header(...),
):
    """Check the status of a sync job by Celery task ID."""
    _check_auth(authorization)

    result = run_sync_job.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "status": result.status,
    }
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/output/list")
async def list_output_files():
    """List all generated Excel files."""
    if not OUTPUT_DIR.exists():
        return {"files": []}
    files = sorted(OUTPUT_DIR.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
    return {
        "files": [
            {"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)}
            for f in files
        ]
    }


@router.get("/output/{filename}")
async def download_output_file(filename: str):
    """Download a specific Excel output file."""
    filepath = OUTPUT_DIR / filename
    if not filepath.exists() or not filepath.suffix == ".xlsx":
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
