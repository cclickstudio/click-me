# 챗 지식 RAG 설계 — `domain/chat/` 바운디드 컨텍스트 (Phase 1)

> 작성 2026-06-25 · 브랜치 `feat/chat-boeun`
> 챗(4-4) 어시스턴트가 Meta 공식 정책 + 일반 마케팅 지식을 근거로 답하도록, 큐레이션 마크다운을 임베딩해 DB에 저장하고 하이브리드 검색으로 인용 답변을 제공한다.

---

## 1. 목적 · 성격

- **성격** 범용 마케팅 지식 Q&A. 사용자 데이터에 붙는 운영 질문(매니지먼트 어시스턴트의 영역)이 아니라, *"리타게팅이 뭐야", "이 카피 Meta 정책상 괜찮아?"* 같은 **지식 질문**에 답한다.
- **왜 RAG** 마케팅 지식을 미리 임베딩해 DB에 두면, 매번 LLM 프롬프트에 긴 지식을 욱여넣는 대신 질문에 관련된 작은 청크만 꺼내 쓴다 → **토큰 비용↓·속도↑**, 환각↓(근거 기반).
- **비목표(YAGNI, 후속)** 자동 크롤링(B), `tools/knowledge` 승격, 챗 오케스트레이터 본체(도메인 라우팅), 대화 메모리/히스토리.

## 2. 단계 전략 (확정)

최종 목표는 **C(하이브리드)**. 이번 단계는 **A(큐레이션 마크다운)** 로 시작하되, **스키마와 ingest 파이프라인을 B(자동 수집)를 나중에 꽂을 수 있게 열어둔다.** 일반 마케팅 지식과 데모 안정성은 큐레이션 마크다운으로 확보하고, Meta 공식 문서는 후속으로 자동 수집 어댑터를 붙이는 식이 가장 안전하다.

| 구분 | 내용 |
| --- | --- |
| **Phase 1 (이번)** | A. 큐레이션 마크다운. `domain/chat/knowledge/` 골격 + 신규 테이블 + 검색·답변·인용. |
| **Phase 2 (후속)** | B. Meta 공식 문서 자동 수집 어댑터 + 한국어 검색 품질 강화. |
| **최종** | C. 일반 지식(큐레이션) + Meta(자동 수집) 하이브리드. |

## 3. 위치 · 경계

- **Phase 1: `domain/chat/`** 새 바운디드 컨텍스트.
- 기존 management KB 코드(`kb_ingest.py`·`retriever.py`)는 **참고하되 직접 의존하지 않는다** (코드·데이터 모두 독립).
- 인터페이스는 작게 — `KnowledgeRetriever` / `KnowledgeIngestor` 두 포트 정도.
- 메타데이터 스키마(`source_url`·`retrieved_at`·`effective_from`·`content_hash`)는 **공용화 가능하게** 설계.

**왜 A(새 도메인)인가**
- 챗 RAG는 단순 "검색 유틸"이 아니라 챗 경험의 일부다. 어떤 지식을 어떤 톤·출처·우선순위로 가져올지는 챗 도메인 정책에 가깝다.
- management assistant 안에 넣으면 챗이 매니지먼트에 종속된다.
- 처음부터 공용 `tools/knowledge`로 만들면 추상화가 빨리 굳고 변경 조율 비용이 커진다.
- "내 브랜치에서 만들고 나중에 통합" 워크플로우엔 작업 자유도가 높은 A가 맞다.

**후속 승격 경로**
```
domain/chat/knowledge/  → 충분히 안정화
                        → tools/knowledge (또는 shared/knowledge)로 추출
                        → management·chat이 같은 포트 사용
```

## 4. 구조

```
backend/domain/chat/
├── contracts/
│   ├── ports.py        # KnowledgeRetriever · KnowledgeIngestor (Protocol, 작게 유지)
│   └── schemas.py      # KnowledgeChunk · RetrievedChunk · KnowledgeSource 메타
├── knowledge/
│   ├── kb/             # 큐레이션 마크다운 (marketing_*.md, meta_*.md)
│   ├── ingestor.py     # md → '## 섹션'(+길이제한) 청크 → 임베딩 → DB (content_hash 멱등)
│   ├── retriever.py    # 하이브리드(벡터+키워드 RRF) 검색
│   ├── normalize.py    # 마크다운 정규화 (content_hash 기준 단일 정의)
│   └── sources.py      # 출처 레지스트리 — B(자동수집) 끼울 seam
├── service/
│   └── chat_service.py # 질문 → 검색 → 근거 게이트 → 주입 LLM 인용 답변 (Gemini 어댑터·SSE는 후속)
└── wiring.py           # mock ↔ real 전환 단일 지점 (Composition Root)
```

**의존성 방향** `service → contracts(포트) ← knowledge(구현)`. mock↔real 전환은 `wiring.py`에서만.

## 5. 임베딩 모델 — 단일 출처 상수 + 교체 정책

**단일 출처 상수.** 임베딩 모델·차원은 **설정 상수 한 곳**에서만 정의하고, DB row·ingestor·retriever가 모두 같은 값을 본다. 세 곳이 따로 하드코딩하면 차원/모델 불일치로 검색이 조용히 깨진다.

```python
# domain/chat/knowledge/config.py (또는 core/config.py)
CHAT_KNOWLEDGE_EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_KNOWLEDGE_EMBEDDING_DIM = 1536
```

- ingestor: 이 상수로 임베딩 생성하고, 각 chunk row의 `embedding_model` 컬럼에 **상수 값을 기록**.
- retriever: 같은 상수로 쿼리를 임베딩 → 적재·검색이 항상 동일 모델.
- 차원 표준은 코드베이스(`ad_embeddings`·`management_kb_chunks`)와 동일한 **1536**. 챗 LLM(Gemini)과 임베딩 모델(OpenAI)은 별개 역할이므로 혼용 정상.

**모델 교체 정책 (중요).** `vector(1536)`은 마이그레이션에 차원이 박힌다. 임베딩 모델 교체는 *기존 테이블 재사용*이 아니라 **재색인(re-index)** 작업이다.

- 같은 차원 모델로 교체 → 전체 청크를 **새 모델로 재임베딩**(덮어쓰기), `embedding_model` 컬럼으로 구·신 혼재 검증.
- 다른 차원 모델로 교체 → **새 컬럼/테이블(또는 새 컬렉션)** 생성 후 재색인·전환. 한 컬럼에 차원 혼재 금지.
- `embedding_model`이 상수와 다른 row가 있으면 재색인 필요 신호.

**한국어 임베딩 (Phase 2 품질 레버).** `text-embedding-3-small`은 다국어라 작은 KB엔 충분하나 한국어 특화는 아니다. 품질이 부족하면 **BGE-m3(1024)** 또는 **Upstage solar-embedding** 등 한국어 강세 모델로 교체 검토 — 단 차원이 달라 위 **재색인/새 테이블 정책**이 발동한다. Phase 1 범위 아님.

## 6. 데이터 모델 (신규 테이블, Alembic)

management 스키마를 본떠 **공용화 가능한 메타데이터**를 갖는 챗 전용 테이블.

**`chat_knowledge_documents`** (청크의 부모)
- `id` · `source`(파일명) · `title` · `source_type` · `source_url`(없으면 NULL)
- `version`(빌드 시그니처: 모델·청킹버전·`max_chunk_chars`) · `language` · `status`(`active`|`deprecated`) · `content_hash`(전체 md에서 keywords 제외한 정규화 해시)
- `retrieved_at` · `effective_from` (TIMESTAMPTZ, tz-aware) — **B 자동수집 대비 버전 컬럼**
- `created_at` · `updated_at`

**`chat_knowledge_chunks`**
- `id` · `document_id`(FK, cascade) · `source` · `title` · `chunk`(TEXT) · `keywords`(TEXT, NULL 가능)
- `embedding vector(1536)` · `embedding_model` · `chunk_index` · `content_hash`(각 청크의 title+본문 정규화 해시)
- `search_vector`(tsvector 생성열) · `created_at`
- **`search_vector` 정의** `to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(chunk,'') || ' ' || coalesce(keywords,''))` STORED — title·chunk·keywords를 모두 키워드 검색 대상으로.
- > `source_type`은 chunks에 두지 않는다(아래 §9 필터는 documents join으로 처리).

**`source_type` enum (초기 4개).** 초기엔 늘리지 않되 필요해질 때만 추가 — provenance 정직성을 위해 "큐레이션 요약"과 "공식 원문"을 분리한다.

| 값 | 의미 |
| --- | --- |
| `meta_official` | Meta 공식 **원문/발췌** — **Phase 2 자동수집 전용**, 큐레이션 요약엔 쓰지 않음 |
| `meta_curated_summary` | 사람이 요약한 Meta 정책 큐레이션 (공식 참고 URL 보유, 권위 단정 금지) |
| `marketing_general` | 일반 마케팅 지식 (큐레이션) |
| `internal` | 내부 작성 정책/메모 |

> ⚠️ **공통부 주의** `core/models.py`·Alembic 마이그레이션은 협업 규칙상 공통부다. 본인 브랜치에선 자유롭게 추가하되, **통합 시 사전 공지 + Alembic 리비전 조율** 항목으로 표시한다. 신규 테이블이라 기존 테이블 변경은 없음(충돌 위험 낮음).

> **DB 확장·UUID 전략** 마이그레이션은 `CREATE EXTENSION IF NOT EXISTS vector`와 함께 **`pgcrypto`** 도 보장한다(테이블 기본값 `gen_random_uuid()`용 — PG13+는 코어 내장이라 보통 불필요하나 이식성 대비). ORM insert는 앱 측 `uuid.uuid4`(코드베이스 표준)를 쓰므로 DB 기본값은 폴백이다.

## 7. 큐레이션 마크다운 형식 (한국어 키워드 보강)

각 `## 섹션` 바로 아래에 선택적 `keywords:` 줄을 둔다. ingestor가 이 줄을 파싱해 `keywords` 컬럼에 저장(본문 임베딩엔 제외, 키워드 검색에만 사용). 한국어 정확 키워드·동의어·영문 대응어를 함께 적어 `simple` tsvector의 한국어 약점을 저비용으로 보강한다.

```markdown
## 리타게팅
keywords: 리타게팅, 리마케팅, retargeting, remarketing, 방문자 재타겟팅, 장바구니 이탈

리타게팅은 ... (본문)
```

## 8. 포트 (작은 인터페이스)

```python
# contracts/ports.py
class KnowledgeIngestor(Protocol):
    async def ingest(self) -> int: ...        # 적재된 청크 수 반환, content_hash 멱등

class KnowledgeRetriever(Protocol):
    async def search(
        self, query: str, k: int = 4, source_type: str | None = None
    ) -> list[RetrievedChunk]: ...            # source_type으로 meta만/마케팅만 필터
```

- `RetrievedChunk` = `{chunk_id, source, title, chunk, source_url, score, similarity}`.
  - `score` = RRF 융합 점수(상대 랭킹). `similarity` = 벡터 코사인 유사도(절대값, 근거 게이트용).
- 포트가 작아 나중에 `tools/knowledge`로 옮길 때 시그니처 그대로 이동 가능.

## 9. 적재 파이프라인 (Phase 1 = A)

1. `kb/*.md`를 정규화 후 `## 섹션` 단위로 청크화(섹션의 `keywords:` 줄 분리). **섹션이 길면 하위 분할**(청킹 정책).
2. `sources.py` 레지스트리에서 파일별 `(source_type, source_url)` 매핑.
3. **`title + 섹션 본문`**(keywords 제외)을 상수 모델(`text-embedding-3-small`)로 임베딩. title은 주제 신호가 강해 검색 정확도를 높이고, management 패턴(`title + 본문`)과도 일치.
4. **문서 본문 `content_hash` 비교 → 재임베딩 여부 결정**. 메타데이터만 바뀐 경우 별도 처리(아래).
5. `chat_knowledge_documents` + `chat_knowledge_chunks`에 적재. chunk row의 `embedding_model`에 상수 기록.

**청킹 정책 (`##` + 최대 길이).** `## 섹션` 기준으로 자르되, 한 청크가 **최대 길이(초기값 약 1500자 / ≈500토큰)** 를 넘으면 문단(빈 줄) → 문장 순으로 **하위 분할**(인접 청크 소폭 overlap 허용). **한 문장 자체가 한도를 넘으면(긴 약관·URL) 마지막 폴백으로 하드 분할**해 모든 청크가 한도 내가 되도록 보장한다. 최대 길이는 설정 상수로 둬 튜닝 가능. **하위 분할 시 그 섹션의 `keywords`를 모든 하위 청크에 복사**한다(안 하면 뒤쪽 청크가 키워드 검색에서 약해짐).

**content_hash 기준 (정규화 마크다운, 확정).** `normalize.py`의 정규화 함수를 단일 기준으로(원문 그대로 해시 금지).
- 정규화: ① CRLF→LF, ② 줄 끝 공백 제거, ③ 연속 3줄+ 빈 줄 → 1줄, ④ 앞뒤 빈 줄 제거.
- **문서 해시(`documents.content_hash`)** = `sha256`(전체 md에서 `keywords:` 줄 제외 후 정규화). 재임베딩 판단의 본문 기준(여러 `## 섹션` 포함).
- **청크 해시(`chunks.content_hash`)** = `sha256`(정규화 title + 청크 본문, keywords 제외). 청크 단위 추적용.
- title은 임베딩 입력에 포함되므로 두 해시 모두 title 변경에 반응한다(keywords는 임베딩 비대상이라 제외).

**재임베딩 판단 = 문서 해시 + 빌드 시그니처.** 본문이 같아도 임베딩 모델·청킹 설정이 바뀌면 기존 벡터를 재사용하면 안 된다(§5 교체=재색인). skip은 아래를 **모두** 만족할 때만 허용:
- `documents.content_hash` 동일, **그리고**
- **빌드 시그니처 동일** = 임베딩 모델 + 청킹 알고리즘 버전 + `max_chunk_chars`. 시그니처는 `documents.version`에 저장·비교(동치: 모든 기존 `chunk.embedding_model` == 현재 모델 + 청킹 설정 동일).
- 시그니처가 다르면(모델/청킹 변경) 재색인 경로로 떨어진다.

**변경 종류별 처리 (불필요한 재임베딩 차단).**
- **title/본문 변경**(`embedding_content_hash` 달라짐) → 해당 출처 문서·청크 재생성 + 재임베딩.
- **keywords만 변경**(임베딩 해시 동일) → **재임베딩 skip**, `chunks.keywords`만 UPDATE → `search_vector`(생성열) 자동 갱신.
- **메타데이터만 변경**(`source_url`·`source_type`·`effective_from`·`version`) → 재임베딩 skip, 문서 row UPDATE.
- 셋 다 동일 → 완전 skip.

**동시 실행 방지 (cron/수동 겹침).** ingest는 출처별 *delete 후 recreate* 라 동시 실행 시 문서가 순간적으로 비거나 중복될 수 있다.
- 전체 ingest를 **PostgreSQL advisory lock**(고정 키)으로 보호 → 동시 1개만.
- **`pg_advisory_xact_lock` 권장** — 트랜잭션 종료 시 자동 해제라 unlock 누락 사고가 없다. 전체 ingest를 한 트랜잭션으로 묶기 어려우면 `pg_advisory_lock` + `finally` unlock 폴백.
- 출처별 delete+recreate는 **단일 트랜잭션** 안에서 → 커밋 전까지 빈 상태 노출 없음.

**B 끼우는 seam** — `ingestor`는 "텍스트 + 출처 메타"를 공급하는 추상에 의존.
- Phase 1: `LocalMarkdownSource` (kb/*.md 읽기).
- Phase 2: `MetaDocsFetchSource`(크롤러)가 **같은 모양**(텍스트 + source_url + retrieved_at)으로 공급 → ingestor는 출처가 파일인지 웹인지 모른다.

## 10. 검색 (하이브리드 + RRF)

management `retriever.py` 패턴 차용.
- **벡터 채널** 쿼리 임베딩 → pgvector 코사인 거리.
- **키워드 채널** `websearch_to_tsquery('simple', q)`로 GIN 검색 (title+chunk+keywords 대상).
- **융합** Reciprocal Rank Fusion(K=60)으로 두 랭킹 합산.

**documents-join 필터 = 양 채널 모두 (`status` + `source_type`).** `status`·`source_type`은 documents에만 있으므로, 벡터·키워드 쿼리 **둘 다 `chat_knowledge_documents`를 join**해 **항상 `documents.status = 'active'`** (deprecated 제외), 지정 시 `documents.source_type = :st`로 필터한다(융합 전). 한쪽만 필터하면 융합 시 다른 범위가 섞인다. (작은 KB라 join 비용 무시 가능.)

**한국어 키워드 검색 한계 (Phase 1 보강 + Phase 2 점검).** `simple` config는 한국어 형태소 분석을 못 한다. Phase 1은 ①벡터 채널이 의미를 커버 + ②`keywords` 컬럼으로 정확 토큰을 보강해 수용한다. Phase 2에서 **pg_trgm·pg_bigm·외부 검색엔진(OpenSearch/Nori 등)** 을 비교 검토하되, **pg_bigm은 사용 DB(NeonDB) 환경의 확장 지원 여부를 먼저 확인**한다.

## 11. 답변 흐름 — 근거 게이트 + "근거 없음" 정책

1. 사용자 질문 → `chat_service`.
2. `retriever.search(query, k, source_type?)` → 관련 청크 top-k.
3. **근거 게이트** — 통과 못 하면 LLM 호출 전에 단락.
4. 통과 시 청크(+출처)를 프롬프트에 넣어 **Gemini 2.0 Flash**가 인용하며 답변(provider 토글 `CHAT_PROVIDER`, gemini 기본).
5. **SSE 스트리밍** 전송, 답변 본문에 `[1][2]` 인용 마커 + 끝에 출처 매핑.

**근거 게이트 — 코사인 유사도(절대값) 기준.** RRF 점수는 상대 랭킹이라 절대 임계 부적합 → 벡터 코사인 유사도로 게이트.
- **변환식** pgvector `<=>`는 코사인 **거리**(작을수록 유사). 따라서 `similarity = 1 - cosine_distance`. (threshold 반대 해석 방지용 명시.)
- **임계값** 검색된 청크의 **최대 코사인 유사도 `max(similarity) < 0.35`** → "근거 없음". (top-1만 보면 RRF에서 keyword-only(similarity=0)가 1위일 때 false negative가 나므로 max로 판정.) **0.35는 초기 설정값** — 임베딩 모델·정규화·문서 길이에 따라 흔들리므로 **운영 전 소규모 eval로 조정**(설정 상수).
- 검색 0건도 동일 처리.

**근거 없음 정책 (강하게 유지).**
- 게이트 탈락 시: LLM 호출 안 함 — "현재 지식 베이스에 해당 내용이 없습니다"로 응답(또는 다른 경로 안내).
- 호출 시에도 시스템 프롬프트에 **"제공된 컨텍스트에 근거해서만 답하라. 컨텍스트에 없으면 모른다고 답하라. 추측·일반지식으로 채우지 마라."** 명시.

**인용 구조 (chunk id 기반).** 답변 본문에서 사용한 청크를 `[1]`,`[2]`로 표기하고 끝에 **`[n] → {chunk_id, source, title, source_url}`** 매핑을 첨부 → 문장-근거 추적 가능. **응답 후처리에서 유효 인용 마커(1~k 범위 `[n]`)를 검사**하고, 없거나 범위 밖 번호만 있으면 **안전 문구로 내리되 출처는 제공**한다(없는 번호 날조·인용 누락 방지).

> **구현 범위 경계.** 설계 의도는 위 흐름 전체(Gemini 2.0 Flash + SSE)다. 단, **Phase 1 구현(구현계획 Task 8)은 LLM을 주입받는 answer service**(검색 → 게이트 → 인용)까지를 제공하고, **구체 Gemini 어댑터·SSE 엔드포인트 배선은 즉시 후속**으로 분리한다(§13 범위·구현계획 후속 섹션 일치).

## 12. 주기적 업데이트

- **Phase 1** `ingestor`를 **스케줄(cron)** 로 주기 실행. 본문 `content_hash` 멱등이라 바뀐 md만 재임베딩, 메타만 바뀌면 update. advisory lock으로 중복 실행 안전.
- **Phase 2** Meta는 `MetaDocsFetchSource` fetch + ingest를 스케줄링.

## 13. 테스트

| # | 검증 | 기준 |
| --- | --- | --- |
| 1 | 적재 멱등성 | 같은 md로 `ingest()` 2회 → 2회차 전부 skip, 청크 수 불변. |
| 2 | 정규화 멱등성 | 줄 끝 공백/빈 줄만 바꾼 md → content_hash 불변, 재임베딩 skip. |
| 3 | 메타만 변경 | 본문 동일 + source_url 변경 → 재임베딩 skip, 문서 메타 UPDATE 반영. |
| 3b | keywords만 변경 | 본문 동일 + keywords 변경 → 재임베딩 skip, `keywords`/`search_vector`만 갱신. |
| 4 | 긴 섹션 하위분할 | 최대 길이 초과 섹션 → 2개+ 청크로 분할, keywords 전 청크 복사. |
| 5 | keywords 검색 | `keywords`에만 있는 동의어로 질의 → 해당 청크 검색됨. |
| 6 | 관련 청크 검색 | 알려진 질문 → 기대 출처 청크가 top-k에 포함. |
| 7 | source_type 필터 | `meta_curated_summary` 검색 → 양 채널 documents join 필터, 마케팅 일반 청크 미포함. |
| 8 | 근거 게이트 | `max(similarity)` < 0.35인 무관 질문 → "지식 베이스에 없음", LLM 미호출. |
| 9 | 인용 추적 | 답변에 `[n]` 마커 + `chunk_id` 매핑 반환. |
| 9b | 인용 검증 | LLM 응답에 유효 `[n]` 마커 없으면 안전 문구로 내리고 출처 제공. |
| 10 | 동시 실행 | ingest 2개 동시 → advisory lock 직렬화, 중복/공백 없음. |

## 14. 범위 정리

- **포함** chat 도메인 골격, 신규 2테이블 + 마이그레이션, 임베딩 단일 상수 + 교체 정책(빌드 시그니처), 정규화 문서/청크 해시 멱등 + 메타·keywords-only update, `##`+길이제한 청킹(문장→하드 분할 폴백), `keywords` 보강 + title/chunk/keywords search_vector, 포트(`KnowledgeRetriever`/`KnowledgeIngestor`), documents-join 양채널 `status`+`source_type` 필터 하이브리드 검색, `1 - cosine_distance` `max(similarity)` 근거 게이트(초기 0.35), **LLM 주입 answer service**(게이트+chunk-id 인용), advisory lock cron 재적재, 큐레이션 md(마케팅+Meta 요약).
- **제외(후속)** **구체 Gemini 어댑터·SSE 엔드포인트 배선**, 자동 크롤링(B), 한국어 특화 임베딩(BGE-m3/Upstage, 재색인 동반)·한국어 FTS(pg_trgm/pg_bigm/외부엔진), `tools/knowledge` 승격, 챗 오케스트레이터 본체, 대화 메모리/히스토리.
