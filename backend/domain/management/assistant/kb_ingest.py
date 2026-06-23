# 매니지먼트 KB 인제스천 — 마크다운 → 섹션 청크 → 임베딩 → management_kb_chunks
"""kb/*.md를 '## 섹션' 단위로 청크화해 임베딩 후 DB에 적재한다(소스별 재적재=멱등).

실행: cd backend && uv run python -m domain.management.assistant.kb_ingest
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import delete

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk, ManagementKbDocument
from domain.management.assistant.retriever import EMBEDDING_MODEL

_KB_DIR = Path(__file__).parent / "kb"

# 파일별 출처 유형 — 문서 메타(source_type). 미지정은 playbook.
_SOURCE_TYPES = {
    "meta_ad_policy.md": "meta_official",
    "optimization_playbook.md": "playbook",
    "kpi_measurement_rules.md": "internal_policy",
    "remediation_actions.md": "internal_policy",
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
    async with AsyncSessionLocal() as db:
        for md in sorted(_KB_DIR.glob("*.md")):
            source = md.name
            text = md.read_text(encoding="utf-8")
            sections = _chunk_markdown(text)
            if not sections:
                continue
            # 재적재 멱등: 같은 출처의 문서 삭제(청크 cascade) + 옛 평면 청크 정리 후 재생성.
            await db.execute(
                delete(ManagementKbDocument).where(ManagementKbDocument.title == source)
            )
            await db.execute(delete(ManagementKbChunk).where(ManagementKbChunk.source == source))
            doc = ManagementKbDocument(
                tenant_id=None,  # 공통(global) 지식
                visibility="global",
                source_type=_SOURCE_TYPES.get(source, "playbook"),
                title=source,
                version=_sha(text)[:12],
                status="active",
                content_hash=_sha(text),
                language="ko",
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
    print(f"적재 완료: {total} chunks")
    return total


if __name__ == "__main__":
    asyncio.run(ingest())
