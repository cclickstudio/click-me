# 매니지먼트 KB 인제스천 — 마크다운 → 섹션 청크 → 임베딩 → management_kb_chunks
"""kb/*.md를 '## 섹션' 단위로 청크화해 임베딩 후 DB에 적재한다(소스별 재적재=멱등).

실행: cd backend && uv run python -m domain.management.assistant.kb_ingest
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import delete, select

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk, ManagementKbDocument
from domain.management.assistant.retriever import EMBEDDING_MODEL

_KB_DIR = Path(__file__).parent / "kb"

# 파일별 출처 메타 — (source_type, source_url, trust, extra_meta).
# trust: system_backed(코드 기준값 근거 → 단정 가능) | advisory(외부 참고 → 단서 필수) |
#        reference(출처 있는 구성/통계 → 인용하되 효율 단정 금지).
# extra_meta는 doc_metadata JSONB에 trust와 함께 병합된다(platform·as_of·confidence 등).
_SOURCE_META: dict[str, tuple[str, str | None, str, dict]] = {
    "meta_ad_policy.md": (
        "meta_official",
        "https://transparency.meta.com/policies/ad-standards/",
        "system_backed",
        {"platform": "meta"},
    ),
    "optimization_playbook.md": ("playbook", None, "system_backed", {"platform": "meta"}),
    "kpi_measurement_rules.md": ("internal_policy", None, "system_backed", {"platform": "meta"}),
    "remediation_actions.md": ("internal_policy", None, "system_backed", {"platform": "meta"}),
    "benchmark_meta_industry.md": (
        "benchmark",
        "https://www.adamigo.ai/blog/meta-ads-benchmarks-2026-by-objective-and-placement",
        "system_backed",
        {"platform": "meta", "as_of": "2026-06", "confidence": "high"},
    ),
    "benchmark_multiplatform.md": (
        "benchmark",
        None,
        "advisory",
        {"platform": "cross", "as_of": "2026-06", "confidence": "low"},
    ),
    "segment_korea.md": (
        "benchmark",
        "https://adstat.kobaco.co.kr/mcr/portal/introPage.do",
        "reference",
        {"platform": "meta", "as_of": "2026-06", "confidence": "medium"},
    ),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    """'## 헤딩' 단위로 (title, chunk) 리스트. 헤딩 앞 서문은 무시(헤딩 본문만)."""
    out: list[tuple[str, str]] = []
    title, buf = None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if title:
                out.append((title, f"{title}\n" + "\n".join(buf).strip()))
            title, buf = line[3:].strip(), []
        elif title:
            buf.append(line)
    if title:
        out.append((title, f"{title}\n" + "\n".join(buf).strip()))
    return out


async def ingest() -> int:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    total = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        for md in sorted(_KB_DIR.glob("*.md")):
            source = md.name
            text = md.read_text(encoding="utf-8")
            new_hash = _sha(text)
            # 증분(content_hash 변경감지): 같은 출처 active 문서가 동일 해시면 재임베딩 스킵.
            existing = (
                (
                    await db.execute(
                        select(ManagementKbDocument).where(
                            ManagementKbDocument.title == source,
                            ManagementKbDocument.status == "active",
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None and existing.content_hash == new_hash:
                skipped += 1
                print(f"  {source}: 변경 없음 - skip")
                continue
            sections = _chunk_markdown(text)
            if not sections:
                continue
            # 변경/신규 → 같은 출처의 문서 삭제(청크 cascade) + 옛 평면 청크 정리 후 재생성.
            await db.execute(
                delete(ManagementKbDocument).where(ManagementKbDocument.title == source)
            )
            await db.execute(delete(ManagementKbChunk).where(ManagementKbChunk.source == source))
            source_type, source_url, trust, extra = _SOURCE_META.get(
                source, ("playbook", None, "system_backed", {})
            )
            now = datetime.now(UTC)
            doc = ManagementKbDocument(
                tenant_id=None,  # 공통(global) 지식
                visibility="global",
                source_type=source_type,
                source_url=source_url,  # 외부 공식 근거 URL(없으면 내부 작성물 → None)
                title=source,
                version=_sha(text)[:12],
                status="active",
                content_hash=_sha(text),
                language="ko",
                retrieved_at=now,  # 이 내용을 KB에 반영(확인)한 시각
                effective_from=now,  # 유효 시작 — 자동수집 도입 시 버전별로 갱신
                verified_by="manual",  # 사람이 작성·검수한 요약 (자동수집 아님)
                doc_metadata={"trust": trust, **extra},  # 답변 인용 시 신뢰도 라벨
            )
            db.add(doc)
            await db.flush()  # doc.id 확보
            resp = await client.embeddings.create(
                model=EMBEDDING_MODEL, input=[c for _, c in sections]
            )
            for idx, ((title, chunk), item) in enumerate(zip(sections, resp.data, strict=True)):
                db.add(
                    ManagementKbChunk(
                        source=source,
                        title=title,
                        chunk=chunk,
                        embedding=item.embedding,
                        document_id=doc.id,
                        tenant_id=None,
                        chunk_index=idx,
                        heading_path=title,
                        content_hash=_sha(chunk),
                        embedding_model=EMBEDDING_MODEL,
                        embedding_dimensions=len(item.embedding),
                    )
                )
            total += len(sections)
            print(f"  {source} [{doc.source_type}]: {len(sections)} chunks")
        await db.commit()
    print(f"적재 완료: {total} chunks (변경 없음 skip: {skipped})")
    return total


if __name__ == "__main__":
    asyncio.run(ingest())
