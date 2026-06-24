# 매니지먼트 KB 인제스천 — 마크다운 → 섹션 청크 → 임베딩 → management_kb_chunks
"""kb/*.md를 '## 섹션' 단위로 청크화해 임베딩 후 DB에 적재한다(소스별 재적재=멱등).

실행: cd backend && uv run python -m domain.management.assistant.kb_ingest
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import delete

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk

_KB_DIR = Path(__file__).parent / "kb"


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
    from domain.chat.wiring import build_embedding_provider

    embedder = build_embedding_provider(settings)
    total = 0
    async with AsyncSessionLocal() as db:
        for md in sorted(_KB_DIR.glob("*.md")):
            source = md.name
            sections = _chunk_markdown(md.read_text(encoding="utf-8"))
            if not sections:
                continue
            vectors = await embedder.embed([c for _, c in sections])
            await db.execute(delete(ManagementKbChunk).where(ManagementKbChunk.source == source))
            for (title, chunk), vec in zip(sections, vectors, strict=True):
                db.add(ManagementKbChunk(source=source, title=title, chunk=chunk, embedding=vec))
            total += len(sections)
            print(f"  {source}: {len(sections)} chunks")
        await db.commit()
    print(f"적재 완료: {total} chunks")
    return total


if __name__ == "__main__":
    asyncio.run(ingest())
