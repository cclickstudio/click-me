# 아는 출처 URL을 httpx+trafilatura로 긁어 KB 초안(draft)으로 적재 — 사람 검수 전 자동수집
"""화이트리스트 출처를 가져와 본문만 추출해 draft 문서로 쌓는다(검색에는 안 잡힘).

설계 원칙 — 자동수집분은 '초안'까지만이다. trafilatura 본문 추출엔 노이즈·출처 충돌이 섞이므로,
사람이 검수해 kb/*.md로 정리한 뒤 kb_ingest가 active 정본화한다. 따라서 여기서는:
- status="draft", verified_by=None, doc_metadata.trust="advisory" 로 적재,
- 청크/임베딩을 만들지 않는다 → chunk 기반 retriever에 자동 격리(검색 비노출).

실행: cd backend && uv run python -m domain.management.assistant.source_refresh
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ManagementKbDocument

# 화이트리스트만 수집 — 임의 URL 스크래핑 금지(robots·약관·rate limit 준수).
_KNOWN_SOURCES: dict[str, str] = {
    "benchmark_meta_industry": (
        "https://www.adamigo.ai/blog/meta-ads-benchmarks-2026-by-objective-and-placement"
    ),
    "benchmark_cpm_country": (
        "https://www.adamigo.ai/blog/meta-ads-cpm-cpc-benchmarks-by-country-2026"
    ),
}

_DRAFT_TTL_DAYS = 90  # 초안 신선도 — 이 기간 지나면 재수집·검수 대상


async def fetch_extract(url: str, client: httpx.AsyncClient) -> str | None:
    """URL 본문 텍스트 추출. 실패하면 None(수집은 best-effort)."""
    try:
        resp = await client.get(url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  {url}: fetch 실패 — {e}")
        return None
    # trafilatura는 동기 라이브러리 → to_thread로 감싸 이벤트 루프 블로킹 방지.
    import trafilatura  # noqa: PLC0415 — 선택 의존성(수집 시에만 로드)

    text = await asyncio.to_thread(trafilatura.extract, resp.text)
    return text or None


async def refresh(slug: str | None = None) -> list[str]:
    """화이트리스트(또는 단일 slug)를 수집해 draft 문서로 적재. 적재된 slug 목록 반환."""
    targets = {slug: _KNOWN_SOURCES[slug]} if slug else dict(_KNOWN_SOURCES)
    done: list[str] = []
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db, httpx.AsyncClient() as client:
        for name, url in targets.items():
            text = await fetch_extract(url, client)
            if not text:
                continue
            title = f"{name}.draft.md"
            # 같은 초안 재수집 시 옛 draft 교체(active 정본은 title이 달라 영향 없음).
            await db.execute(
                delete(ManagementKbDocument).where(
                    ManagementKbDocument.title == title,
                    ManagementKbDocument.status == "draft",
                )
            )
            db.add(
                ManagementKbDocument(
                    tenant_id=None,
                    visibility="global",
                    source_type="benchmark",
                    source_url=url,
                    title=title,
                    status="draft",  # 검색 비노출 — 사람 검수 후 kb/*.md로 정본화
                    language="ko",
                    retrieved_at=now,
                    expires_at=now + timedelta(days=_DRAFT_TTL_DAYS),
                    verified_by=None,  # 자동수집 — 미검수
                    doc_metadata={
                        "trust": "advisory",
                        "auto": True,
                        "src_url": url,
                        "extracted_chars": len(text),
                    },
                )
            )
            done.append(name)
            print(f"  {name}: draft 적재 ({len(text):,}자) ← {url}")
        await db.commit()
    print(f"수집 완료: {len(done)} draft (검수 후 kb/*.md 정리 → kb_ingest로 정본화)")
    return done


if __name__ == "__main__":
    _ = settings  # .env 로드 보장
    asyncio.run(refresh())
