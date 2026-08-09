from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .background import run_extraction_job
from .schemas import ExtractionJobCreateResponse, ExtractionJobStatusResponse
from .services import prepare_source, submit_job
from .storage import job_registry


router = APIRouter(prefix="/landslide-extraction", tags=["landslide-extraction"])


@router.post("/jobs", response_model=ExtractionJobCreateResponse, status_code=202)
def create_extraction_job(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    path: str | None = Form(default=None),
    url: str | None = Form(default=None),
) -> ExtractionJobCreateResponse:
    content, source_name = prepare_source(upload=file, path=path, url=url)
    job_id = submit_job(background_tasks, content, source_name)
    return ExtractionJobCreateResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=ExtractionJobStatusResponse)
def get_extraction_job(job_id: str) -> ExtractionJobStatusResponse:
    record = job_registry.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return ExtractionJobStatusResponse(**record)


@router.get("/jobs/{job_id}/download")
def download_extraction_job(job_id: str) -> FileResponse:
    record = job_registry.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.get("status") != "complete" or not record.get("output_csv"):
        raise HTTPException(status_code=409, detail="Job is not complete yet")
    return FileResponse(record["output_csv"], media_type="text/csv", filename=f"{job_id}.csv")
