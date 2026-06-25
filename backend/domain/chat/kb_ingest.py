# CLIO KB 인제스천 — 마크다운 → 섹션 청크 → 임베딩 → clio_kb_chunks
"""kb/*.md를 '## 섹션' 단위로 청크화해 임베딩 후 DB에 적재한다(소스별 재적재=멱등).

실행: cd backend && uv run python -m domain.chat.kb_ingest
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import delete

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ClioKbChunk

EMBEDDING_MODEL = "text-embedding-3-small"
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
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    total = 0
    async with AsyncSessionLocal() as db:
        for md in sorted(_KB_DIR.glob("*.md")):
            source = md.name
            sections = _chunk_markdown(md.read_text(encoding="utf-8"))
            if not sections:
                continue
            resp = await client.embeddings.create(
                model=EMBEDDING_MODEL, input=[c for _, c in sections]
            )
            await db.execute(delete(ClioKbChunk).where(ClioKbChunk.source == source))
            for (title, chunk), item in zip(sections, resp.data, strict=True):
                db.add(
                    ClioKbChunk(source=source, title=title, chunk=chunk, embedding=item.embedding)
                )
            total += len(sections)
            print(f"  {source}: {len(sections)} chunks")
        await db.commit()
    print(f"적재 완료: {total} chunks")
    return total


if __name__ == "__main__":
    asyncio.run(ingest())
