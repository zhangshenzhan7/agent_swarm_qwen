"""文件上传/下载路由"""

import os
import uuid
import base64
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from utils import get_recommended_roles_for_files

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", "uploads")
# 兼容：如果从 backend 目录运行
if not os.path.exists(UPLOAD_DIR):
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
UPLOAD_DIR = os.path.abspath(UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        file_id = uuid.uuid4().hex[:8]
        ext = file.filename.split(".")[-1] if "." in file.filename else ""
        saved_name = f"{file_id}.{ext}" if ext else file_id
        file_path = os.path.join(UPLOAD_DIR, saved_name)
        with open(file_path, "wb") as f:
            f.write(content)
        base64_data = None
        if file.content_type and file.content_type.startswith("image/"):
            base64_data = base64.b64encode(content).decode("utf-8")
        recommended_roles = get_recommended_roles_for_files([{"type": file.content_type, "name": file.filename}])
        return {
            "success": True,
            "file": {
                "id": file_id, "name": file.filename, "type": file.content_type,
                "size": len(content), "path": file_path, "url": f"/api/files/{saved_name}",
                "base64": base64_data,
            },
            "recommended_roles": recommended_roles,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/upload/multiple")
async def upload_multiple_files(files: List[UploadFile] = File(...)):
    results = []
    all_recommended_roles = set()
    for file in files:
        try:
            content = await file.read()
            file_id = uuid.uuid4().hex[:8]
            ext = file.filename.split(".")[-1] if "." in file.filename else ""
            saved_name = f"{file_id}.{ext}" if ext else file_id
            file_path = os.path.join(UPLOAD_DIR, saved_name)
            with open(file_path, "wb") as f:
                f.write(content)
            base64_data = None
            if file.content_type and file.content_type.startswith("image/"):
                base64_data = base64.b64encode(content).decode("utf-8")
            recommended = get_recommended_roles_for_files([{"type": file.content_type, "name": file.filename}])
            all_recommended_roles.update(recommended)
            results.append({
                "success": True,
                "file": {
                    "id": file_id, "name": file.filename, "type": file.content_type,
                    "size": len(content), "path": file_path, "url": f"/api/files/{saved_name}",
                    "base64": base64_data,
                },
                "recommended_roles": recommended,
            })
        except Exception as e:
            results.append({"success": False, "name": file.filename, "error": str(e)})
    return {
        "results": results, "total": len(files),
        "successful": sum(1 for r in results if r.get("success")),
        "all_recommended_roles": list(all_recommended_roles),
    }


@router.get("/api/files/{filename}")
async def get_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
