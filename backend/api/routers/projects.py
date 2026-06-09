import uuid
from datetime import datetime, timezone
from fastapi import APIRouter

from core.schemas import ProjectCreate

router = APIRouter()

_projects: list[dict] = []


@router.get("")
async def list_projects():
    return {"projects": _projects}


@router.post("", status_code=201)
async def create_project(body: ProjectCreate):
    project_id = str(uuid.uuid4())
    _projects.append({
        "id": project_id,
        "name": body.name,
        "description": body.description,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"id": project_id}


@router.get("/{project_id}")
async def get_project(project_id: str):
    for p in _projects:
        if p["id"] == project_id:
            return p
    return {"error": "Not found"}
