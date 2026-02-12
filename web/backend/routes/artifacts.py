"""产物相关 API 路由

Provides endpoints for listing, retrieving, and downloading output artifacts
associated with a task.

Endpoints:
    GET /api/tasks/{task_id}/artifacts              - list artifacts
    GET /api/tasks/{task_id}/artifacts/{artifact_id} - artifact detail
    GET /api/tasks/{task_id}/artifacts/{artifact_id}/download - download single
    GET /api/tasks/{task_id}/artifacts/download-all  - ZIP download all
"""

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from src.artifact_storage import ArtifactStorage

router = APIRouter()

# Module-level storage instance (default path)
_storage = ArtifactStorage()


def get_storage() -> ArtifactStorage:
    """Return the module-level ArtifactStorage instance."""
    return _storage


@router.get("/api/tasks/{task_id}/artifacts")
async def list_artifacts(task_id: str):
    """List all artifacts for a task.

    Returns a JSON array of artifact dicts (without heavy content field).
    """
    storage = get_storage()
    artifacts = await storage.list_artifacts(task_id)
    result = []
    for artifact in artifacts:
        d = artifact.to_dict()
        d.pop("content", None)
        d.pop("content_type", None)
        result.append(d)
    return result


@router.get("/api/tasks/{task_id}/artifacts/download-all")
async def download_all_artifacts(task_id: str):
    """Download all artifacts for a task as a ZIP archive."""
    storage = get_storage()
    artifacts = await storage.list_artifacts(task_id)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f"No artifacts found for task {task_id}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for artifact in artifacts:
            ext = artifact.metadata.format
            filename = f"{artifact.artifact_id}.{ext}"
            if isinstance(artifact.content, bytes):
                zf.writestr(filename, artifact.content)
            else:
                zf.writestr(filename, artifact.content.encode("utf-8"))
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{task_id}_artifacts.zip"'},
    )


@router.get("/api/tasks/{task_id}/artifacts/{artifact_id}")
async def get_artifact(task_id: str, artifact_id: str):
    """Get artifact detail (metadata, without heavy content)."""
    storage = get_storage()
    try:
        artifact = await storage.retrieve(task_id, artifact_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found for task {task_id}",
        )
    d = artifact.to_dict()
    d.pop("content", None)
    d.pop("content_type", None)
    return d


@router.get("/api/tasks/{task_id}/artifacts/{artifact_id}/download")
async def download_artifact(task_id: str, artifact_id: str, inline: bool = False):
    """Download a single artifact file.

    Query params:
        inline: If true, serve with Content-Disposition: inline so the
                browser can render images/videos directly in <img>/<video> tags.
    """
    storage = get_storage()
    try:
        artifact = await storage.retrieve(task_id, artifact_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found for task {task_id}",
        )

    mime = artifact.metadata.mime_type
    ext = artifact.metadata.format
    filename = f"{artifact.artifact_id}.{ext}"

    if isinstance(artifact.content, bytes):
        content_bytes = artifact.content
    else:
        content_bytes = artifact.content.encode("utf-8")

    # Serve inline for media types so <img>/<video> tags can render them,
    # otherwise force download.
    _INLINE_PREFIXES = ("image/", "video/", "audio/")
    if inline or any(mime.startswith(p) for p in _INLINE_PREFIXES):
        disposition = f'inline; filename="{filename}"'
    else:
        disposition = f'attachment; filename="{filename}"'

    return Response(
        content=content_bytes,
        media_type=mime,
        headers={"Content-Disposition": disposition},
    )
