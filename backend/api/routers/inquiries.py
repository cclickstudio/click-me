# 고객 문의 API — 폼 접수(공개). 관리자 조회·해결은 admin 라우터(/api/admin/inquiries).
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models import Inquiry
from core.schemas import InquiryCreate

router = APIRouter()


@router.post("", status_code=201)
async def create_inquiry(body: InquiryCreate, db: AsyncSession = Depends(get_db)):
    """문의 접수 — 공개(인증 불필요). DB에 영속."""
    row = Inquiry(
        title=body.title,
        content=body.content,
        contact_email=body.contact_email,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"inquiry_id": str(row.id), "created_at": row.created_at.isoformat()}
