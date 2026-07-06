# 매니지먼트 KB 인제스천 — 마크다운 → 섹션 청크 → 임베딩 → management_kb_chunks
"""kb/*.md를 '## 섹션' 단위로 청크화해 임베딩 후 DB에 적재한다(소스별 재적재=멱등).

실행: cd backend && uv run python -m domain.management.assistant.kb_ingest
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk, ManagementKbDocument

_KB_DIR = Path(__file__).parent / "kb"

# 파일별 출처 메타 — (source_type, source_url). 외부 공식 근거가 있으면 URL, 내부 작성물은 None.
# source_type은 검색 네임스페이스로도 쓴다(retriever.search(source_types=[...])).
_SOURCE_META: dict[str, tuple[str, str | None]] = {
    # 매니지먼트(기존)
    "meta_ad_policy.md": ("meta_official", "https://transparency.meta.com/policies/ad-standards/"),
    "optimization_playbook.md": ("playbook", None),
    "kpi_measurement_rules.md": ("internal_policy", None),
    "management_glossary.md": ("internal_policy", None),
    "remediation_actions.md": ("internal_policy", None),
    # 챗 컨시어지(신규) — 내부 작성물(verified_by=manual, source_url 없음).
    "persona_methodology.md": ("persona_methodology", None),
    "simulation_trust.md": ("simulation_trust", None),
    "platform_guide.md": ("platform_guide", None),
    # 외부 레퍼런스 — Meta는 공식 문서 기반 요약(작성 완료), 나머지는 사용자 제공 대기.
    "meta_reference.md": ("meta_reference", "https://transparency.meta.com/policies/ad-standards/"),
    # ↓ 사용자 제공 예정 — 해당 파일명으로 kb/external/에 넣으면 올바른 네임스페이스로 적재됨.
    "kobaco_baseline.md": ("kobaco_baseline", "https://www.kobaco.co.kr/"),
    "evidence.md": ("evidence", None),
    # ADVISE(일반지식) 게이트 검색 풀 — general_knowledge 네임스페이스로 적재.
    "advertising_general_knowledge.md": ("general_knowledge", None),
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
    from domain.management.assistant.embeddings import build_embedding_provider

    embedder = build_embedding_provider(settings)
    total = 0
    skipped = 0
    async with AsyncSessionLocal() as db:
        # rglob — 네임스페이스별 하위폴더(kb/persona/ 등)까지 재귀 수집. source=파일명(고유).
        for md in sorted(_KB_DIR.rglob("*.md")):
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
                print(f"  {source}: 변경 없음 — skip")
                continue
            sections = _chunk_markdown(text)
            if not sections:
                continue
            # 변경/신규 → 같은 출처의 문서 삭제(청크 cascade) + 옛 평면 청크 정리 후 재생성.
            await db.execute(
                delete(ManagementKbDocument).where(ManagementKbDocument.title == source)
            )
            await db.execute(delete(ManagementKbChunk).where(ManagementKbChunk.source == source))
            source_type, source_url = _SOURCE_META.get(source, ("playbook", None))
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
            )
            db.add(doc)
            await db.flush()  # doc.id 확보
            # 임베딩은 주입된 EmbeddingProvider(text-embedding-3-small 1536) — 검색과 동일 차원.
            vectors = await embedder.embed([c for _, c in sections])
            for idx, ((title, chunk), vec) in enumerate(zip(sections, vectors, strict=True)):
                db.add(
                    ManagementKbChunk(
                        source=source,
                        title=title,
                        chunk=chunk,
                        embedding=vec,
                        document_id=doc.id,
                        tenant_id=None,
                        chunk_index=idx,
                        heading_path=title,
                        content_hash=_sha(chunk),
                        embedding_model=settings.embedding_model,
                        embedding_dimensions=len(vec),
                    )
                )
            total += len(sections)
            print(f"  {source} [{doc.source_type}]: {len(sections)} chunks")
        await db.commit()
    print(f"적재 완료: {total} chunks (변경 없음 skip: {skipped})")
    return total


if __name__ == "__main__":
    asyncio.run(ingest())
