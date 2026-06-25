# 챗 지식 RAG (domain/chat Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗(4-4)용 `domain/chat/` 지식 RAG를 만든다 — Meta 정책 + 마케팅 지식을 큐레이션 마크다운으로 적재·임베딩하고, 하이브리드 검색으로 근거를 찾아, **주입된 LLM 함수로** 근거 게이트 통과 시에만 인용 답변하는 answer service까지. (구체 Gemini 어댑터·SSE 스트리밍 배선은 후속.)

**Architecture:** DDD 바운디드 컨텍스트 `domain/chat/`. 순수 로직(정규화·청킹·해시·RRF·게이트·인용)을 DB/LLM과 분리해 단위테스트 가능하게 두고, DB는 챗 전용 신규 테이블 2개(`chat_knowledge_documents`·`chat_knowledge_chunks`, pgvector 1536), 검색은 벡터+키워드 RRF 융합(`source_type`·`status='active'`는 documents join으로 양 채널 필터), 답변 서비스는 **주입된 LLM 함수**로 코사인 근거 게이트 통과 시에만 chunk-id 인용 응답한다(구체 Gemini 어댑터·SSE는 후속). management KB 코드는 참고만 하고 직접 의존하지 않는다.

**Tech Stack:** FastAPI · SQLAlchemy(async) · pgvector · Alembic · OpenAI `text-embedding-3-small`(1536) · Gemini 2.0 Flash · pytest(asyncio) · uv.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `backend/core/config.py` (수정) | 챗 지식 RAG 상수 4개 추가(임베딩 모델/차원/청크 길이/게이트 임계값) |
| `backend/domain/chat/__init__.py` (생성) | 패키지 |
| `backend/domain/chat/contracts/__init__.py` (생성) | 패키지 |
| `backend/domain/chat/contracts/schemas.py` (생성) | `RetrievedChunk` 등 외부 의존 없는 스키마 |
| `backend/domain/chat/contracts/ports.py` (생성) | `KnowledgeIngestor`·`KnowledgeRetriever` Protocol |
| `backend/domain/chat/knowledge/__init__.py` (생성) | 패키지 |
| `backend/domain/chat/knowledge/normalize.py` (생성) | 마크다운 정규화 + 해시(단일 기준) |
| `backend/domain/chat/knowledge/chunking.py` (생성) | `## 섹션`+keywords 파싱, 최대길이 하위분할 |
| `backend/domain/chat/knowledge/sources.py` (생성) | 출처 레지스트리(파일→source_type/url), B seam |
| `backend/domain/chat/knowledge/ingestor.py` (생성) | md→청크→임베딩→DB(멱등·advisory lock) |
| `backend/domain/chat/knowledge/retriever.py` (생성) | 하이브리드 검색 + RRF + documents-join 필터 |
| `backend/domain/chat/knowledge/kb/marketing_basics.md` (생성) | 일반 마케팅 지식 큐레이션 |
| `backend/domain/chat/knowledge/kb/meta_ad_policy.md` (생성) | Meta 정책 요약 큐레이션 |
| `backend/domain/chat/service/__init__.py` (생성) | 패키지 |
| `backend/domain/chat/service/chat_service.py` (생성) | 게이트 + 주입 LLM 인용 답변(answer service) |
| `backend/core/models.py` (수정) | `ChatKnowledgeDocument`·`ChatKnowledgeChunk` ORM |
| `backend/alembic/versions/025_chat_knowledge.py` (생성) | 신규 테이블 마이그레이션 |
| `backend/tests/chat/__init__.py` (생성) | 패키지 |
| `backend/tests/chat/test_normalize.py` (생성) | 정규화·해시 테스트 |
| `backend/tests/chat/test_chunking.py` (생성) | 청킹·keywords·하위분할 테스트 |
| `backend/tests/chat/test_retriever_fuse.py` (생성) | RRF 융합 순수 테스트 |
| `backend/tests/chat/test_chat_service.py` (생성) | 게이트·인용·근거없음 테스트(fake 주입) |

> ⚠️ **공통부** `core/config.py`·`core/models.py`·Alembic은 협업 규칙상 공통부. 본 브랜치에선 자유 추가하되 통합 시 사전 공지. `api/main.py` 라우터 등록은 이 Phase 범위 밖(엔드포인트 연결은 후속 — chat_service는 함수로 제공해 기존 `/chat/complete` CLIO 경로나 신규 라우터가 호출).

---

## Task 1: 설정 상수 + 챗 도메인 스키마/포트

**Files:**
- Modify: `backend/core/config.py` (Settings 클래스 내 Generator 섹션 뒤)
- Create: `backend/domain/chat/__init__.py`
- Create: `backend/domain/chat/contracts/__init__.py`
- Create: `backend/domain/chat/contracts/schemas.py`
- Create: `backend/domain/chat/contracts/ports.py`

- [ ] **Step 1: 설정 상수 추가**

`backend/core/config.py`의 `jwt_expire_minutes` 줄 바로 아래(검증자 `@field_validator` 앞)에 추가.

```python
    # Chat knowledge RAG (domain/chat) — 임베딩/검색 단일 출처 상수
    # 모델·차원은 여기서만 정의: ingestor·retriever·DB row가 같은 값을 본다.
    chat_knowledge_embedding_model: str = "text-embedding-3-small"
    chat_knowledge_embedding_dim: int = 1536  # vector(1536) 마이그레이션과 일치
    chat_knowledge_max_chunk_chars: int = 1500  # 초과 섹션은 하위 분할
    chat_knowledge_relevance_threshold: float = 0.35  # 초기값 — eval로 조정
```

- [ ] **Step 2: 패키지 init 3개 생성**

`backend/domain/chat/__init__.py`, `backend/domain/chat/contracts/__init__.py` 둘 다 빈 파일(첫 줄 한국어 헤더 주석 1줄).

```python
# 챗(4-4) 바운디드 컨텍스트 패키지
```
```python
# 챗 도메인 포트·스키마(외부 의존 없음) 패키지
```

- [ ] **Step 3: 스키마 작성**

Create `backend/domain/chat/contracts/schemas.py`:

```python
# 챗 지식 RAG 검색 결과 스키마 — 외부 의존 없는 순수 데이터
from __future__ import annotations

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    """하이브리드 검색이 돌려주는 청크 1건. score=RRF(상대), similarity=코사인(절대, 게이트용)."""

    chunk_id: str
    source: str
    title: str
    chunk: str
    source_url: str | None = None
    score: float  # RRF 융합 점수(상대 랭킹)
    similarity: float  # 1 - cosine_distance (절대값, 근거 게이트용)
```

- [ ] **Step 4: 포트 작성**

Create `backend/domain/chat/contracts/ports.py`:

```python
# 챗 지식 RAG 포트 — 작게 유지(나중에 tools/knowledge 승격 시 시그니처 그대로 이동)
from __future__ import annotations

from typing import Protocol

from domain.chat.contracts.schemas import RetrievedChunk


class KnowledgeIngestor(Protocol):
    async def ingest(self) -> int:
        """kb/*.md를 청크·임베딩해 적재. 적재된 청크 수 반환(content_hash 멱등)."""
        ...


class KnowledgeRetriever(Protocol):
    async def search(
        self, query: str, k: int = 4, source_type: str | None = None
    ) -> list[RetrievedChunk]:
        """하이브리드 검색. source_type으로 meta만/마케팅만 한정(documents join)."""
        ...
```

- [ ] **Step 5: import 확인**

Run: `cd backend && uv run python -c "from domain.chat.contracts.ports import KnowledgeRetriever, KnowledgeIngestor; from domain.chat.contracts.schemas import RetrievedChunk; from core.config import settings; print(settings.chat_knowledge_embedding_model, settings.chat_knowledge_embedding_dim)"`
Expected: `text-embedding-3-small 1536` 출력, 에러 없음.

- [ ] **Step 6: Commit**

```bash
cd backend && uv run ruff format domain/chat core/config.py && uv run ruff check domain/chat core/config.py --fix
git add core/config.py domain/chat/
git commit -m "add: 챗 지식 RAG 설정 상수·도메인 스키마/포트"
```

---

## Task 2: 마크다운 정규화 + 해시

**Files:**
- Create: `backend/domain/chat/knowledge/__init__.py`
- Create: `backend/domain/chat/knowledge/normalize.py`
- Test: `backend/tests/chat/__init__.py`, `backend/tests/chat/test_normalize.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/chat/__init__.py` (빈 파일). Create `backend/tests/chat/test_normalize.py`:

```python
# 챗 지식 RAG 정규화·해시 단위테스트
from domain.chat.knowledge.normalize import (
    embedding_content_hash,
    strip_keywords_lines,
    normalize_markdown,
)


def test_normalize_collapses_blank_lines_and_trailing_ws():
    raw = "제목  \n\n\n\n본문 줄  \n\n"
    assert normalize_markdown(raw) == "제목\n\n본문 줄"


def test_normalize_crlf_to_lf():
    assert normalize_markdown("a\r\nb\r\n") == "a\nb"


def test_strip_keywords_lines_removes_only_keywords():
    md = "## 리타게팅\nkeywords: 리타게팅, retargeting\n\n본문이다"
    assert "keywords:" not in strip_keywords_lines(md)
    assert "본문이다" in strip_keywords_lines(md)


def test_embedding_hash_ignores_keywords_and_whitespace():
    # title+body 같으면 keywords·공백이 달라도 해시 동일
    h1 = embedding_content_hash("리타게팅", "본문 A")
    h2 = embedding_content_hash("리타게팅", "본문 A  ")
    assert h1 == h2


def test_embedding_hash_changes_on_title():
    assert embedding_content_hash("A", "본문") != embedding_content_hash("B", "본문")
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.chat.knowledge.normalize`.

- [ ] **Step 3: 구현**

Create `backend/domain/chat/knowledge/__init__.py`:
```python
# 챗 지식 RAG 적재·검색 구현 패키지
```

Create `backend/domain/chat/knowledge/normalize.py`:
```python
# 마크다운 정규화·해시 — content_hash 멱등의 단일 기준
from __future__ import annotations

import hashlib
import re


def normalize_markdown(text: str) -> str:
    """① CRLF→LF ② 줄 끝 공백 제거 ③ 연속 3줄+ 빈 줄→1줄 ④ 앞뒤 빈 줄 제거."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def strip_keywords_lines(text: str) -> str:
    """'keywords:'로 시작하는 줄 제거(임베딩 입력에서 제외)."""
    kept = [ln for ln in text.split("\n") if not ln.lstrip().lower().startswith("keywords:")]
    return "\n".join(kept)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embedding_content_hash(title: str, body: str) -> str:
    """청크 content_hash = sha256(정규화 title+본문, keywords 제외).

    임베딩 입력 범위(title+body)와 동일 범위라 title 변경도 추적된다.
    (문서 단위 재임베딩 게이트는 ingestor의 _doc_hash(전체 md) + 빌드 시그니처로 판단.)
    """
    norm = normalize_markdown(strip_keywords_lines(f"{title}\n{body}"))
    return _sha(norm)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_normalize.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff format domain/chat tests/chat && uv run ruff check domain/chat tests/chat --fix
git add domain/chat/knowledge/ tests/chat/
git commit -m "add: 챗 지식 RAG 마크다운 정규화·해시"
```

---

## Task 3: 청킹(`##` + keywords + 최대길이 하위분할)

**Files:**
- Create: `backend/domain/chat/knowledge/chunking.py`
- Test: `backend/tests/chat/test_chunking.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/chat/test_chunking.py`:

```python
# 챗 지식 RAG 청킹 단위테스트
from domain.chat.knowledge.chunking import chunk_markdown


def test_splits_by_h2_and_parses_keywords():
    md = (
        "## 리타게팅\n"
        "keywords: 리타게팅, retargeting\n\n"
        "리타게팅은 방문자를 다시 노린다.\n\n"
        "## CPC\n본문2"
    )
    chunks = chunk_markdown(md, max_chars=1000)
    assert [c.title for c in chunks] == ["리타게팅", "CPC"]
    assert chunks[0].keywords == "리타게팅, retargeting"
    assert "keywords:" not in chunks[0].text  # 본문(임베딩 입력)엔 keywords 미포함
    assert chunks[0].text.startswith("리타게팅")  # title이 본문 앞에
    assert chunks[1].keywords is None


def test_long_section_subsplits_and_copies_keywords():
    body = "\n\n".join([f"문단 {i} " + "가" * 200 for i in range(5)])
    md = f"## 긴섹션\nkeywords: 키워드A\n\n{body}"
    chunks = chunk_markdown(md, max_chars=300)
    assert len(chunks) >= 2  # 하위 분할됨
    assert all(c.title == "긴섹션" for c in chunks)
    assert all(c.keywords == "키워드A" for c in chunks)  # 모든 하위 청크에 복사
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_long_single_paragraph_subsplits_by_sentence():
    # 빈 줄 없는 한 문단(여러 문장)이 max_chars 초과 → 문장 단위 하위분할
    para = " ".join(f"문장{i}이다." + "가" * 40 for i in range(10))
    chunks = chunk_markdown(f"## 긴문단\n\n{para}", max_chars=300)
    assert len(chunks) >= 2  # 문단 한 덩어리지만 문장으로 쪼개져 분할됨
    assert max(len(c.text) for c in chunks) < len(para)


def test_single_oversized_sentence_hard_splits():
    # 경계 없는 한 문장이 max_chars 초과 → 하드 분할로 한도 내 청크 보장
    sentence = "가" * 1000  # 문장/문단 경계 없음
    chunks = chunk_markdown(f"## 약관\n\n{sentence}", max_chars=200)
    assert len(chunks) >= 2
    assert all(len(c.text) <= 200 for c in chunks)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.chat.knowledge.chunking`.

- [ ] **Step 3: 구현**

Create `backend/domain/chat/knowledge/chunking.py`:
```python
# '## 섹션'+keywords 파싱과 최대 길이 하위분할 — 검색 단위 청크 생성
from __future__ import annotations

import re
from dataclasses import dataclass

from domain.chat.knowledge.normalize import normalize_markdown


@dataclass(frozen=True)
class Chunk:
    title: str
    text: str  # 임베딩 입력 = title + 본문(keywords 제외)
    keywords: str | None
    chunk_index: int


def _sentence_split(text: str) -> list[str]:
    """문장 경계(. ! ? 。)로 거칠게 분할 — 한국어/영문 혼용 대응."""
    return [p for p in re.split(r"(?<=[.!?。])\s+", text) if p]


def _split_section(title: str, body: str, max_chars: int) -> list[str]:
    """max_chars 초과면 문단(빈 줄)→문장 순으로 하위 분할. 각 조각 앞에 title 부착."""
    full = f"{title}\n{body}".strip()
    if len(full) <= max_chars:
        return [full]
    # 분할 단위 = 문단. 한 문단이 본문 예산을 넘으면 문장으로 더 쪼갠다.
    budget = max(max_chars - len(title) - 1, 1)
    units: list[str] = []
    for para in body.split("\n\n"):
        if len(para) <= budget:
            units.append(para)
        else:
            units.extend(_sentence_split(para))
    # 문장 하나가 예산 초과(긴 약관·URL)면 마지막 폴백으로 하드 분할 → 각 청크 한도 보장.
    bounded: list[str] = []
    for unit in units:
        if len(unit) <= budget:
            bounded.append(unit)
        else:
            bounded.extend(unit[i : i + budget] for i in range(0, len(unit), budget))
    units = bounded
    pieces: list[str] = []
    buf = ""
    for unit in units:
        candidate = f"{buf}\n\n{unit}".strip() if buf else unit
        if buf and len(f"{title}\n{candidate}") > max_chars:
            pieces.append(f"{title}\n{buf}".strip())
            buf = unit
        else:
            buf = candidate
    if buf:
        pieces.append(f"{title}\n{buf}".strip())
    return pieces


def chunk_markdown(text: str, max_chars: int) -> list[Chunk]:
    """정규화 후 '## 헤딩' 단위로 자르고, keywords 줄 분리·긴 섹션 하위분할."""
    text = normalize_markdown(text)
    sections: list[tuple[str, list[str], str | None]] = []
    title: str | None = None
    body: list[str] = []
    keywords: str | None = None
    for line in text.split("\n"):
        if line.startswith("## "):
            if title is not None:
                sections.append((title, body, keywords))
            title, body, keywords = line[3:].strip(), [], None
        elif title is not None and line.lstrip().lower().startswith("keywords:"):
            keywords = line.split(":", 1)[1].strip() or None
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append((title, body, keywords))

    chunks: list[Chunk] = []
    idx = 0
    for sec_title, sec_body, sec_kw in sections:
        body_text = "\n".join(sec_body).strip()
        for piece in _split_section(sec_title, body_text, max_chars):
            chunks.append(Chunk(title=sec_title, text=piece, keywords=sec_kw, chunk_index=idx))
            idx += 1
    return chunks
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_chunking.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff format domain/chat tests/chat && uv run ruff check domain/chat tests/chat --fix
git add domain/chat/knowledge/chunking.py tests/chat/test_chunking.py
git commit -m "add: 챗 지식 RAG 청킹(섹션·keywords·하위분할)"
```

---

## Task 4: DB 모델 + Alembic 마이그레이션

**Files:**
- Modify: `backend/core/models.py` (파일 끝, 다른 KB 모델 뒤)
- Create: `backend/alembic/versions/025_chat_knowledge.py`

- [ ] **Step 1: ORM 모델 추가**

`backend/core/models.py` 끝에 추가(이미 `Vector`·`UUID`·`JSONB` import됨):

```python
class ChatKnowledgeDocument(Base):
    """챗 지식 RAG 문서(청크의 부모) — 출처·버전·유효기간 메타. 마이그 025."""

    __tablename__ = "chat_knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128))  # 출처 파일명
    title: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(32))  # meta_official|marketing_general|internal
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ko")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|deprecated
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 임베딩 게이트 해시
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ChatKnowledgeChunk(Base):
    """챗 지식 RAG 청크 — Meta·마케팅 지식의 벡터+키워드 검색. 마이그 025."""

    __tablename__ = "chat_knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_knowledge_documents.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(128))  # 인용용(파일명)
    title: Mapped[str] = mapped_column(String(256))  # 섹션 제목(인용용)
    chunk: Mapped[str] = mapped_column(Text)  # 임베딩 입력 = title+본문
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # 한국어 키워드 보강
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # search_vector는 DB 생성열(title+chunk+keywords) — ORM 미매핑.
```

- [ ] **Step 2: 마이그레이션 작성**

Create `backend/alembic/versions/025_chat_knowledge.py`:
```python
"""add chat_knowledge tables — 챗 지식 RAG (domain/chat Phase 1)

Revision ID: 025
Revises: 024
Create Date: 2026-06-25

Meta 정책·마케팅 지식 마크다운을 청크·임베딩해 벡터+키워드 하이브리드 검색.
신규 테이블만 추가(additive) — 기존 테이블 변경 없음.
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_knowledge_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source VARCHAR(128) NOT NULL,
            title VARCHAR(512) NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            source_url TEXT,
            version VARCHAR(64),
            language VARCHAR(16) NOT NULL DEFAULT 'ko',
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            content_hash VARCHAR(64),
            retrieved_at TIMESTAMPTZ,
            effective_from TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_kb_docs_source "
        "ON chat_knowledge_documents (source, status)"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_knowledge_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL REFERENCES chat_knowledge_documents(id) ON DELETE CASCADE,
            source VARCHAR(128) NOT NULL,
            title VARCHAR(256) NOT NULL,
            chunk TEXT NOT NULL,
            keywords TEXT,
            embedding vector(1536) NOT NULL,
            embedding_model VARCHAR(64),
            chunk_index INTEGER,
            content_hash VARCHAR(64),
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('simple',
                    coalesce(title,'') || ' ' || coalesce(chunk,'') || ' ' || coalesce(keywords,''))
            ) STORED,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_kb_chunks_search "
        "ON chat_knowledge_chunks USING GIN (search_vector)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_kb_chunks_document "
        "ON chat_knowledge_chunks (document_id, chunk_index)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_knowledge_chunks")
    op.execute("DROP TABLE IF EXISTS chat_knowledge_documents")
```

- [ ] **Step 3: 모델 import 확인**

Run: `cd backend && uv run python -c "from core.models import ChatKnowledgeDocument, ChatKnowledgeChunk; print(ChatKnowledgeChunk.__tablename__)"`
Expected: `chat_knowledge_chunks` 출력, 에러 없음.

- [ ] **Step 4: 마이그레이션 적용(로컬 DB 있으면)**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade 024 -> 025` 로그. (DB 미연결이면 이 step은 통합 시 수행 — 메모로 남기고 진행.)

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff format core/models.py alembic/versions/025_chat_knowledge.py && uv run ruff check core/models.py alembic/versions/025_chat_knowledge.py --fix
git add core/models.py alembic/versions/025_chat_knowledge.py
git commit -m "add: 챗 지식 RAG 테이블·마이그레이션(025)"
```

---

## Task 5: 큐레이션 마크다운 + 출처 레지스트리

**Files:**
- Create: `backend/domain/chat/knowledge/kb/marketing_basics.md`
- Create: `backend/domain/chat/knowledge/kb/meta_ad_policy.md`
- Create: `backend/domain/chat/knowledge/sources.py`
- Test: `backend/tests/chat/test_sources.py`

- [ ] **Step 1: 마케팅 지식 md 작성**

Create `backend/domain/chat/knowledge/kb/marketing_basics.md`:
```markdown
# 일반 마케팅 지식

## 리타게팅
keywords: 리타게팅, 리마케팅, retargeting, remarketing, 방문자 재타겟팅, 장바구니 이탈

리타게팅은 한 번 방문했거나 관심을 보인 사용자에게 광고를 다시 노출하는 전략이다.
장바구니에 담고 이탈한 사용자, 특정 페이지를 본 사용자 등 세그먼트별로 메시지를 달리한다.
신규 고객 확보보다 전환율이 높고 비용이 낮은 편이라 퍼포먼스 캠페인의 기본이다.

## CTR과 CVR
keywords: CTR, 클릭률, CVR, 전환율, click through rate, conversion rate

CTR(클릭률)은 노출 대비 클릭 비율, CVR(전환율)은 클릭(또는 방문) 대비 전환 비율이다.
CTR이 높아도 CVR이 낮으면 랜딩 페이지나 타겟 적합도를 점검해야 한다.
두 지표는 함께 봐야 하며 단독 수치로 성과를 단정하지 않는다.

## A/B 테스트
keywords: A/B 테스트, AB test, 분할 테스트, 대조군, 변수 통제

A/B 테스트는 한 번에 하나의 변수만 바꾼 두 시안을 동시 노출해 성과를 비교하는 방법이다.
충분한 표본과 기간을 확보해야 하며, 여러 변수를 동시에 바꾸면 원인을 분리할 수 없다.
```

- [ ] **Step 2: Meta 정책 요약 md 작성**

Create `backend/domain/chat/knowledge/kb/meta_ad_policy.md`:
```markdown
# Meta 광고 정책 요약

## 금지·제한 콘텐츠
keywords: 금지 콘텐츠, 정책 위반, 차별, 과장 광고, 건강 보조

Meta 광고는 차별적 표현, 검증되지 않은 효능 주장, 과장·허위 정보를 금지한다.
체중 감량·건강 보조 등은 비현실적 결과나 before/after 강조를 제한한다.
정확한 최신 기준은 공식 광고 표준 문서를 따른다.

## 개인 속성 강조 금지
keywords: 개인 속성, personal attributes, 인종, 종교, 건강상태, 직접 지칭

광고 문구에서 사용자의 인종·종교·나이·건강상태·성적 지향 등을 직접 단정·지칭하는 표현을 금지한다.
"당신처럼 ~한 사람"처럼 개인 속성을 안다고 암시하는 2인칭 표현에 주의한다.
```

- [ ] **Step 3: 실패 테스트 작성**

Create `backend/tests/chat/test_sources.py`:
```python
# 출처 레지스트리 단위테스트
from domain.chat.knowledge.sources import resolve_source


def test_known_meta_file_maps_to_meta_official():
    st, url = resolve_source("meta_ad_policy.md")
    assert st == "meta_official"
    assert url is not None


def test_marketing_file_maps_to_general():
    st, url = resolve_source("marketing_basics.md")
    assert st == "marketing_general"
    assert url is None


def test_unknown_file_defaults_to_internal():
    st, url = resolve_source("random_notes.md")
    assert st == "internal"
    assert url is None
```

- [ ] **Step 4: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.chat.knowledge.sources`.

- [ ] **Step 5: 구현**

Create `backend/domain/chat/knowledge/sources.py`:
```python
# 출처 레지스트리 — 파일명→(source_type, source_url). B(자동수집) 끼울 seam.
from __future__ import annotations

# 파일별 출처 메타. 외부 공식 근거가 있으면 URL, 내부 작성물은 None.
_SOURCE_META: dict[str, tuple[str, str | None]] = {
    "meta_ad_policy.md": ("meta_official", "https://transparency.meta.com/policies/ad-standards/"),
    "marketing_basics.md": ("marketing_general", None),
}


def resolve_source(filename: str) -> tuple[str, str | None]:
    """등록된 파일이면 매핑, 아니면 internal 기본."""
    return _SOURCE_META.get(filename, ("internal", None))
```

- [ ] **Step 6: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_sources.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
cd backend && uv run ruff format domain/chat tests/chat && uv run ruff check domain/chat tests/chat --fix
git add domain/chat/knowledge/kb/ domain/chat/knowledge/sources.py tests/chat/test_sources.py
git commit -m "add: 챗 지식 RAG 큐레이션 md·출처 레지스트리"
```

---

## Task 6: Ingestor (멱등 적재 + advisory lock)

**Files:**
- Create: `backend/domain/chat/knowledge/ingestor.py`

> 적재는 DB·임베딩 의존이라 단위테스트는 순수 부분(Task 2·3)에서 이미 커버했다. ingestor는 라이브(DB+OpenAI 키)로 검증하며, 본 Task는 구현+스모크 import만 게이트한다(management의 kb_ingest와 동일한 검증 전략).

- [ ] **Step 1: 구현**

Create `backend/domain/chat/knowledge/ingestor.py`:
```python
# 챗 지식 KB 인제스천 — kb/*.md → 청크 → 임베딩 → chat_knowledge_* (멱등·advisory lock)
"""kb/*.md를 '## 섹션'(+최대길이) 청크화해 임베딩 후 적재한다.

변경 종류별 처리:
- title/본문 변경(embedding_content_hash 달라짐) → 문서·청크 재생성 + 재임베딩
- keywords만 변경 → 재임베딩 skip, chunks.keywords만 UPDATE(search_vector 자동 갱신)
- 메타만 변경 → 재임베딩 skip, 문서 row UPDATE
- 전부 동일 → 완전 skip

실행: cd backend && uv run python -m domain.chat.knowledge.ingestor
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import delete, select, text, update

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ChatKnowledgeChunk, ChatKnowledgeDocument
from domain.chat.knowledge.chunking import chunk_markdown
from domain.chat.knowledge.normalize import (
    embedding_content_hash,
    normalize_markdown,
    strip_keywords_lines,
)
from domain.chat.knowledge.sources import resolve_source

_KB_DIR = Path(__file__).parent / "kb"
_LOCK_KEY = 0x0C8A7C0DE  # 챗 KB ingest 전용 advisory lock 고정 키


def _doc_hash(md: str) -> str:
    """문서 본문(전체) 임베딩 해시 — keywords 제외 정규화 전체."""
    norm = normalize_markdown(strip_keywords_lines(md))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# 청킹 알고리즘 버전 — 알고리즘이 바뀌면 올린다(빌드 시그니처에 포함 → 재색인 유발).
_CHUNKING_VERSION = "1"


def _build_signature(model: str, max_chars: int) -> str:
    """임베딩 모델·청킹 설정·알고리즘 버전을 묶은 빌드 시그니처. version 컬럼에 저장·비교.

    본문이 같아도 모델/청킹이 바뀌면 시그니처가 달라져 재색인된다(스펙 §5 교체=재색인).
    """
    return f"c{_CHUNKING_VERSION}-{model}-{max_chars}"


async def ingest() -> int:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    model = settings.chat_knowledge_embedding_model
    signature = _build_signature(model, settings.chat_knowledge_max_chunk_chars)
    total = 0
    async with AsyncSessionLocal() as db:
        # 동시 실행 직렬화 — 트랜잭션 종료 시 자동 해제(xact lock).
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
        for md_path in sorted(_KB_DIR.glob("*.md")):
            source = md_path.name
            raw = md_path.read_text(encoding="utf-8")
            new_hash = _doc_hash(raw)
            source_type, source_url = resolve_source(source)
            now = datetime.now(UTC)

            existing = (
                (
                    await db.execute(
                        select(ChatKnowledgeDocument).where(
                            ChatKnowledgeDocument.source == source,
                            ChatKnowledgeDocument.status == "active",
                        )
                    )
                )
                .scalars()
                .first()
            )

            chunks = chunk_markdown(raw, settings.chat_knowledge_max_chunk_chars)
            if not chunks:
                continue

            # 본문·빌드설정(모델·청킹) 동일 → 재임베딩 skip. keywords/메타만 동기화.
            # 모델/청킹이 바뀌면 시그니처 불일치 → 아래 재색인 경로로 떨어진다(스펙 §5).
            if (
                existing is not None
                and existing.content_hash == new_hash
                and existing.version == signature
            ):
                if (existing.source_url, existing.source_type) != (source_url, source_type):
                    existing.source_url = source_url
                    existing.source_type = source_type
                    existing.updated_at = now
                # keywords 동기화(본문 임베딩 불변).
                for c in chunks:
                    await db.execute(
                        update(ChatKnowledgeChunk)
                        .where(
                            ChatKnowledgeChunk.document_id == existing.id,
                            ChatKnowledgeChunk.chunk_index == c.chunk_index,
                        )
                        .values(keywords=c.keywords)
                    )
                continue

            # 변경/신규 → 출처 문서·청크 삭제 후 재생성(cascade).
            await db.execute(
                delete(ChatKnowledgeDocument).where(ChatKnowledgeDocument.source == source)
            )
            doc = ChatKnowledgeDocument(
                source=source,
                title=source,
                source_type=source_type,
                source_url=source_url,
                version=signature,
                status="active",
                content_hash=new_hash,
                retrieved_at=now,
                effective_from=now,
            )
            db.add(doc)
            await db.flush()
            resp = await client.embeddings.create(model=model, input=[c.text for c in chunks])
            for c, item in zip(chunks, resp.data, strict=True):
                db.add(
                    ChatKnowledgeChunk(
                        document_id=doc.id,
                        source=source,
                        title=c.title,
                        chunk=c.text,
                        keywords=c.keywords,
                        embedding=item.embedding,
                        embedding_model=model,
                        chunk_index=c.chunk_index,
                        content_hash=embedding_content_hash(c.title, c.text),
                    )
                )
            total += len(chunks)
            print(f"  {source} [{source_type}]: {len(chunks)} chunks")
        await db.commit()
    print(f"적재 완료: {total} chunks")
    return total


if __name__ == "__main__":
    asyncio.run(ingest())
```

- [ ] **Step 2: 스모크 import 확인**

Run: `cd backend && uv run python -c "from domain.chat.knowledge.ingestor import ingest; print('ok')"`
Expected: `ok` 출력, 에러 없음.

- [ ] **Step 3: 라이브 적재(DB+OpenAI 키 있으면)**

Run: `cd backend && uv run python -m domain.chat.knowledge.ingestor`
Expected: `marketing_basics.md`·`meta_ad_policy.md` 청크 수 출력, `적재 완료: N chunks`. 한 번 더 실행하면 `적재 완료: 0 chunks`(멱등). (키/DB 없으면 통합 시 수행 — 메모.)

- [ ] **Step 4: Commit**

```bash
cd backend && uv run ruff format domain/chat && uv run ruff check domain/chat --fix
git add domain/chat/knowledge/ingestor.py
git commit -m "add: 챗 지식 RAG ingestor(멱등 적재·advisory lock)"
```

---

## Task 7: Retriever (하이브리드 + RRF + documents-join 필터)

**Files:**
- Create: `backend/domain/chat/knowledge/retriever.py`
- Test: `backend/tests/chat/test_retriever_fuse.py`

- [ ] **Step 1: RRF 융합 실패 테스트 작성**

Create `backend/tests/chat/test_retriever_fuse.py`:
```python
# RRF 융합 순수 로직 테스트(DB 불필요)
from types import SimpleNamespace

from domain.chat.knowledge.retriever import rrf_fuse


def _row(id_, dist=None):
    return SimpleNamespace(
        id=id_, source="s", title="t", chunk="c", source_url=None, dist=dist
    )


def test_chunk_in_both_channels_ranks_first():
    vec = [_row("A", dist=0.1), _row("B", dist=0.2)]
    kw = [_row("B"), _row("C")]
    out = rrf_fuse(vec, kw, k=3)
    assert out[0].chunk_id == "B"  # 두 채널 모두 잡힘 → 최상위


def test_similarity_is_one_minus_distance():
    vec = [_row("A", dist=0.25)]
    out = rrf_fuse(vec, [], k=1)
    assert abs(out[0].similarity - 0.75) < 1e-9  # 1 - 0.25


def test_keyword_only_chunk_has_zero_similarity():
    out = rrf_fuse([], [_row("C")], k=1)
    assert out[0].similarity == 0.0  # 벡터 채널에 없으면 유사도 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_retriever_fuse.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.chat.knowledge.retriever`.

- [ ] **Step 3: 구현**

Create `backend/domain/chat/knowledge/retriever.py`:
```python
# 챗 지식 하이브리드 검색 — pgvector 코사인 + GIN 키워드, RRF 융합, documents-join 필터
"""벡터(의미)+키워드(정확 토큰)를 RRF로 합친다. source_type은 documents를 join해 양 채널에 적용.

근거 게이트용으로 벡터 채널의 코사인 유사도(1 - distance)를 함께 돌려준다(절대값).
임베딩은 설정 상수 모델(text-embedding-3-small, 1536).
"""

from __future__ import annotations

from openai import AsyncOpenAI
from sqlalchemy import select, text

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import ChatKnowledgeChunk, ChatKnowledgeDocument
from domain.chat.contracts.schemas import RetrievedChunk

_RRF_K = 60  # Reciprocal Rank Fusion 상수

# 키워드 채널 — documents join으로 source_type 필터(NULL이면 전체). title+chunk+keywords가 색인됨.
_KW_SQL = text(
    "SELECT c.id, c.source, c.title, c.chunk, d.source_url,"
    " ts_rank(c.search_vector, websearch_to_tsquery('simple', :q)) AS rank"
    " FROM chat_knowledge_chunks c"
    " JOIN chat_knowledge_documents d ON d.id = c.document_id"
    " WHERE c.search_vector @@ websearch_to_tsquery('simple', :q)"
    "   AND d.status = 'active'"
    "   AND (:st IS NULL OR d.source_type = :st)"
    " ORDER BY rank DESC LIMIT :lim"
)


def rrf_fuse(vec: list, kw: list, k: int) -> list[RetrievedChunk]:
    """두 랭킹을 RRF(1/(K+순위))로 합산. similarity=1-dist(벡터 채널), 없으면 0.0."""
    fused: dict[str, dict] = {}
    for rank, r in enumerate(vec):
        sim = 1.0 - float(r.dist) if r.dist is not None else 0.0
        fused.setdefault(str(r.id), {"r": r, "s": 0.0, "sim": sim})["s"] += 1.0 / (_RRF_K + rank + 1)
    for rank, r in enumerate(kw):
        entry = fused.setdefault(str(r.id), {"r": r, "s": 0.0, "sim": 0.0})
        entry["s"] += 1.0 / (_RRF_K + rank + 1)
    top = sorted(fused.values(), key=lambda x: x["s"], reverse=True)[:k]
    return [
        RetrievedChunk(
            chunk_id=str(x["r"].id),
            source=x["r"].source,
            title=x["r"].title,
            chunk=x["r"].chunk,
            source_url=x["r"].source_url,
            score=round(x["s"], 4),
            similarity=round(x["sim"], 4),
        )
        for x in top
    ]


class PgKnowledgeRetriever:
    """KnowledgeRetriever 구현 — 세션 팩토리·임베딩 클라이언트 주입 가능(테스트)."""

    def __init__(self, api_key: str | None = None, session_factory=AsyncSessionLocal) -> None:
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._sf = session_factory
        self._model = settings.chat_knowledge_embedding_model

    async def _embed(self, query: str) -> list[float]:
        resp = await self._client.embeddings.create(model=self._model, input=[query])
        return resp.data[0].embedding

    async def search(
        self, query: str, k: int = 4, source_type: str | None = None
    ) -> list[RetrievedChunk]:
        emb = await self._embed(query)
        pool = max(k * 3, 8)
        dist = ChatKnowledgeChunk.embedding.cosine_distance(emb).label("dist")
        vec_q = (
            select(
                ChatKnowledgeChunk.id,
                ChatKnowledgeChunk.source,
                ChatKnowledgeChunk.title,
                ChatKnowledgeChunk.chunk,
                ChatKnowledgeDocument.source_url,
                dist,
            )
            .join(ChatKnowledgeDocument, ChatKnowledgeDocument.id == ChatKnowledgeChunk.document_id)
            .where(ChatKnowledgeDocument.status == "active")
            .order_by(dist)
            .limit(pool)
        )
        if source_type is not None:
            vec_q = vec_q.where(ChatKnowledgeDocument.source_type == source_type)
        async with self._sf() as db:
            vec = (await db.execute(vec_q)).all()
            kw = (await db.execute(_KW_SQL, {"q": query, "st": source_type, "lim": pool})).all()
        return rrf_fuse(vec, kw, k)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_retriever_fuse.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff format domain/chat tests/chat && uv run ruff check domain/chat tests/chat --fix
git add domain/chat/knowledge/retriever.py tests/chat/test_retriever_fuse.py
git commit -m "add: 챗 지식 RAG 하이브리드 검색(RRF·documents 필터)"
```

---

## Task 8: chat_service (근거 게이트 + 인용 답변)

**Files:**
- Create: `backend/domain/chat/service/__init__.py`
- Create: `backend/domain/chat/service/chat_service.py`
- Test: `backend/tests/chat/test_chat_service.py`

> 범위: LLM은 주입(`Callable[[str], Awaitable[str]]`)받는 순수 answer service까지. 구체 Gemini 어댑터·SSE 배선은 후속(스펙 §4, 아래 후속 섹션).

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/chat/test_chat_service.py`:
```python
# chat_service 게이트·인용·근거없음 테스트 — fake retriever/LLM 주입(DB·키 불필요)
import pytest

from domain.chat.contracts.schemas import RetrievedChunk
from domain.chat.service.chat_service import answer_knowledge_question, build_citations


class _FakeRetriever:
    def __init__(self, chunks):
        self._chunks = chunks

    async def search(self, query, k=4, source_type=None):
        return self._chunks


async def _fake_llm(prompt: str) -> str:
    return "리타게팅은 재방문 유도 전략입니다 [1]."


def _chunk(sim, cid="c1"):
    return RetrievedChunk(
        chunk_id=cid, source="marketing_basics.md", title="리타게팅",
        chunk="리타게팅 본문", source_url=None, score=0.9, similarity=sim,
    )


def test_build_citations_numbers_from_one():
    cites = build_citations([_chunk(0.8, "a"), _chunk(0.7, "b")])
    assert cites[0]["n"] == 1 and cites[0]["chunk_id"] == "a"
    assert cites[1]["n"] == 2


@pytest.mark.asyncio
async def test_low_similarity_triggers_no_grounds_without_llm():
    called = {"llm": False}

    async def spy_llm(prompt):
        called["llm"] = True
        return "should not be called"

    res = await answer_knowledge_question(
        "관련 없는 질문", _FakeRetriever([_chunk(0.20)]), spy_llm, threshold=0.35
    )
    assert res.grounded is False
    assert called["llm"] is False  # 게이트 탈락 → LLM 미호출
    assert "지식 베이스" in res.answer


@pytest.mark.asyncio
async def test_empty_result_is_not_grounded():
    res = await answer_knowledge_question("무엇", _FakeRetriever([]), _fake_llm, threshold=0.35)
    assert res.grounded is False


@pytest.mark.asyncio
async def test_grounded_answer_has_citations():
    res = await answer_knowledge_question(
        "리타게팅 뭐야", _FakeRetriever([_chunk(0.82)]), _fake_llm, threshold=0.35
    )
    assert res.grounded is True
    assert res.answer.startswith("리타게팅")
    assert res.citations[0]["chunk_id"] == "c1"


@pytest.mark.asyncio
async def test_keyword_only_first_but_similar_vector_is_grounded():
    # RRF 1위가 keyword-only(sim=0)여도, 뒤에 충분히 유사한 청크가 있으면 grounded(max로 게이트)
    chunks = [_chunk(0.0, "kw"), _chunk(0.82, "vec")]
    res = await answer_knowledge_question(
        "리타게팅", _FakeRetriever(chunks), _fake_llm, threshold=0.35
    )
    assert res.grounded is True
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_chat_service.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.chat.service.chat_service`.

- [ ] **Step 3: 구현**

Create `backend/domain/chat/service/__init__.py`:
```python
# 챗 지식 RAG 서비스(유스케이스) 패키지
```

Create `backend/domain/chat/service/chat_service.py`:
```python
# 챗 지식 RAG 답변 — 검색→근거 게이트→LLM 인용 답변. LLM은 주입(테스트 가능).
from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from domain.chat.contracts.ports import KnowledgeRetriever
from domain.chat.contracts.schemas import RetrievedChunk

# 근거 없으면 일반상식으로 못 때우게 강제하는 시스템 프롬프트.
SYSTEM_PROMPT = (
    "당신은 ClickMe의 마케팅 지식 어시스턴트입니다.\n"
    "제공된 컨텍스트에 근거해서만 답하세요. 컨텍스트에 없으면 모른다고 답하세요.\n"
    "추측이나 일반지식으로 채우지 마세요. 사용한 근거는 [번호]로 인용하세요."
)
_NO_GROUNDS = "현재 지식 베이스에 해당 내용이 없습니다."


class KnowledgeAnswer(BaseModel):
    answer: str
    grounded: bool
    citations: list[dict]


def build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    """[n] → {chunk_id, source, title, source_url} 매핑(1부터)."""
    return [
        {
            "n": i,
            "chunk_id": c.chunk_id,
            "source": c.source,
            "title": c.title,
            "source_url": c.source_url,
        }
        for i, c in enumerate(chunks, start=1)
    ]


def _build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    ctx = "\n\n".join(f"[{i}] ({c.title}) {c.chunk}" for i, c in enumerate(chunks, start=1))
    return f"{SYSTEM_PROMPT}\n\n# 컨텍스트\n{ctx}\n\n# 질문\n{question}"


async def answer_knowledge_question(
    question: str,
    retriever: KnowledgeRetriever,
    llm: Callable[[str], Awaitable[str]],
    *,
    k: int = 4,
    source_type: str | None = None,
    threshold: float = 0.35,
) -> KnowledgeAnswer:
    """검색→게이트(top-1 similarity)→통과 시에만 LLM 호출. 인용 포함."""
    chunks = await retriever.search(question, k=k, source_type=source_type)
    # RRF 정렬 특성상 keyword-only(similarity=0)가 1위에 올 수 있어, top-1이 아니라
    # 검색된 청크 중 최대 코사인 유사도로 게이트한다(false negative 방지).
    best_sim = max((c.similarity for c in chunks), default=0.0)
    if not chunks or best_sim < threshold:
        return KnowledgeAnswer(answer=_NO_GROUNDS, grounded=False, citations=[])
    answer = await llm(_build_prompt(question, chunks))
    return KnowledgeAnswer(answer=answer, grounded=True, citations=build_citations(chunks))
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_chat_service.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: 전체 챗 테스트 회귀 확인**

Run: `cd backend && uv run pytest tests/chat/ -v`
Expected: PASS (전체 테스트 통과).

- [ ] **Step 6: Commit**

```bash
cd backend && uv run ruff format domain/chat tests/chat && uv run ruff check domain/chat tests/chat --fix
git add domain/chat/service/ tests/chat/test_chat_service.py
git commit -m "add: 챗 지식 RAG 답변 서비스(근거 게이트·인용)"
```

---

## 후속(이 계획 범위 밖, 스펙 §14)

- **LLM 어댑터 + 엔드포인트 연결** — 구체 Gemini 호출 함수(`llm: Callable[[str], Awaitable[str]]`)를 만들어 `chat_service.answer_knowledge_question`에 주입하고, 기존 `/chat/complete` CLIO 경로 또는 신규 라우터에 배선(SSE 스트리밍). `api/main.py` 라우터 등록은 append-only. (이 Phase의 Task 8은 LLM 주입 가능한 순수 answer service까지만 — Gemini 어댑터·SSE는 여기 후속.)
- B(Meta 공식 문서 자동 수집 어댑터), 한국어 특화 임베딩·FTS, `tools/knowledge` 승격, 대화 메모리.

---

## Self-Review 메모

- **스펙 커버리지** §5 상수(T1)·§6 테이블(T4)·§7 keywords md(T5)·§8 포트(T1)·§9 적재/멱등/청킹/해시/lock(T2·T3·T6)·§10 검색/필터(T7)·§11 게이트/인용(T8)·§12 cron(T6 entrypoint, 스케줄은 운영 설정)·§13 테스트(각 Task) 매핑됨. 엔드포인트(SSE)는 스펙 §4 chat_service까지 구현하고 라우터 배선만 후속으로 분리(범위 명시).
- **타입 일관성** `RetrievedChunk`(chunk_id·similarity·score) T1 정의 → T7 생성 → T8 소비 일치. `Chunk`(title·text·keywords·chunk_index) T3 정의 → T6 소비 일치. `chat_knowledge_*` 테이블/컬럼 T4 정의 → T6·T7 쿼리 일치.
- **플레이스홀더** 없음(모든 step에 실제 코드·명령·기대출력).
