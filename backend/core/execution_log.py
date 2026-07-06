# 실행 히스토리(롱텀 메모리) 공용 기록·검색 — 세 도메인이 도메인 경계 없이 core 경유로 사용
"""chat_execution_history 테이블의 유일한 쓰기·읽기 경로.

쓰기는 각 기능의 실행 확정 지점에서 코드가 결정적으로 호출(record_execution),
읽기는 채팅 recall_history 도구·컨텍스트 주입이 BM25 키워드 서치로 회수한다.
모두 best-effort — 기록·검색 실패가 기능 흐름을 막지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select

from core.db import AsyncSessionLocal
from core.models import ChatExecutionHistory

_KST = timezone(timedelta(hours=9))  # 날짜 필터 기준 — 사용자 체감 시간(KST)


def _as_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """문자열/UUID를 UUID로. 형식이 아니면 None(비UUID 스코프는 기록 생략)."""
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _history_date_bound(value: str | None, *, end: bool) -> datetime | None:
    """YYYY-MM-DD(KST) → 필터 경계. end=True면 다음날 0시(미만 비교용). 형식 오류는 None."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if end:
        d += timedelta(days=1)
    return d.replace(tzinfo=_KST)


async def record_execution(
    project_id: str | None,
    feature_type: str,
    action: str,
    summary: str,
    payload: dict | None = None,
    user_id: str | None = None,
) -> None:
    """기능 수행 1건을 실행 히스토리에 적재(best-effort·비차단).

    summary는 tsvector 색인 대상(키워드 서치용 평문). feature_type=simulation|generation|management.
    프로젝트 스코프 없으면 생략. 실패해도 조용히 무시(기능 흐름을 막지 않는다).
    """
    pid = _as_uuid(project_id)
    if pid is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                ChatExecutionHistory(
                    project_id=pid,
                    user_id=_as_uuid(user_id),
                    feature_type=feature_type,
                    action=action,
                    summary=(summary or "")[:2000],
                    payload=payload or {},
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — 히스토리 적재 실패가 기능을 막지 않게
        print(f"[execution-log] record error: {exc!r}")


async def search_execution_history(
    project_id: str | None,
    query: str,
    k: int = 5,
    feature_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """실행 히스토리를 BM25급 키워드 서치로 회수 — tsvector @@ plainto_tsquery + ts_rank_cd 순.

    query 비었거나 매칭 0건이면 executed_at 최신순 폴백. 한국어는 'simple' config(공백 토큰).
    date_from/date_to는 YYYY-MM-DD(KST) — '몇월 며칠에 뭐 했지' 시점 질의 필터(경계 포함).
    """
    pid = _as_uuid(project_id)
    if pid is None:
        return []
    start = _history_date_bound(date_from, end=False)
    until = _history_date_bound(date_to, end=True)

    def _scoped(stmt: Select) -> Select:
        if feature_type:
            stmt = stmt.where(ChatExecutionHistory.feature_type == feature_type)
        if start is not None:
            stmt = stmt.where(ChatExecutionHistory.executed_at >= start)
        if until is not None:
            stmt = stmt.where(ChatExecutionHistory.executed_at < until)
        return stmt

    def _row(r: ChatExecutionHistory, score: float | None = None) -> dict:
        d = {
            "feature_type": r.feature_type,
            "action": r.action,
            "summary": r.summary,
            "payload": r.payload,
            # KST로 변환해 반환 — 소비처(recall_history 등)가 그대로 잘라 표시(사용자 체감 시간).
            "executed_at": r.executed_at.astimezone(_KST).isoformat() if r.executed_at else None,
        }
        if score is not None:
            d["score"] = round(score, 4)
        return d

    try:
        async with AsyncSessionLocal() as db:
            q = (query or "").strip()
            if q:
                tsq = func.plainto_tsquery("simple", q)
                rank = func.ts_rank_cd(ChatExecutionHistory.search_tsv, tsq).label("rank")
                stmt = _scoped(
                    select(ChatExecutionHistory, rank).where(
                        ChatExecutionHistory.project_id == pid,
                        ChatExecutionHistory.search_tsv.op("@@")(tsq),
                    )
                )
                rows = (await db.execute(stmt.order_by(rank.desc()).limit(k))).all()
                if rows:
                    return [_row(r[0], float(r[1])) for r in rows]
            # 폴백 — 최신순(빈 query·매칭 0건). 종류·날짜 필터는 유지.
            stmt = _scoped(
                select(ChatExecutionHistory).where(ChatExecutionHistory.project_id == pid)
            )
            rows2 = await db.execute(
                stmt.order_by(ChatExecutionHistory.executed_at.desc()).limit(k)
            )
            return [_row(r) for r in rows2.scalars()]
    except Exception as exc:  # noqa: BLE001 — 검색 실패면 빈 목록
        print(f"[execution-log] search error: {exc!r}")
        return []
