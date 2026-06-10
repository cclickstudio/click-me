import uuid
from datetime import UTC, datetime

from fastapi import APIRouter

from core.schemas import InquiryCreate

router = APIRouter()

_store: list[dict] = []


@router.post("", status_code=201)
async def create_inquiry(body: InquiryCreate):
    inquiry_id = str(uuid.uuid4())
    _store.append(
        {
            "inquiry_id": inquiry_id,
            "title": body.title,
            "content": body.content,
            "contact_email": body.contact_email,
            "is_resolved": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    return {"inquiry_id": inquiry_id, "created_at": _store[-1]["created_at"]}
