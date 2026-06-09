import uuid
from datetime import datetime, timezone
from fastapi import APIRouter

from core.schemas import UserCreate

router = APIRouter()

_users: list[dict] = [
    {
        "user_id": str(uuid.uuid4()),
        "email": "admin@clickme.io",
        "name": "관리자",
        "role": "admin",
        "created_at": "2026-06-01T00:00:00Z",
        "last_login_at": None,
    }
]


@router.get("/users")
async def list_users():
    return {"users": _users}


@router.post("/users", status_code=201)
async def create_user(body: UserCreate):
    user_id = str(uuid.uuid4())
    _users.append({
        "user_id": user_id,
        "email": body.email,
        "name": body.name,
        "role": body.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login_at": None,
    })
    return {"user_id": user_id}


@router.get("/inquiries")
async def list_inquiries():
    from api.routers.inquiries import _store as _inquiries
    return {"inquiries": _inquiries}


@router.get("/stats")
async def get_stats():
    return {"users": len(_users), "inquiries": 0}
