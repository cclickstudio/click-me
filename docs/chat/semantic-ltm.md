# 채팅 롱텀 메모리 시맨틱 검색 — 계획·체크리스트·컨텍스트

> 목표: 롱텀 메모리(`chat_long_term_memory`) 조회를 "최신 N개"에서 "질문과 의미적으로 가까운 top-k"로 바꿔 채팅 답변 품질을 올린다.

## 배경 (현황)

- 숏텀: `chat_messages`(DB, 매 턴 영속) + LangGraph 체크포인터(로컬 Windows는 `MemorySaver`, 운영 Linux는 Neon). — 이미 동작.
- 롱텀: `chat_long_term_memory`에 sim/gen 입력·`session_summary`·프로파일 누적. — 저장은 됨.
- 한계: 조회가 `created_at DESC LIMIT 3` (recency)뿐. 임베딩 검색 없음. 주입은 `advise_node`에만.
- 기존 패턴 재사용: `ClioKbRetriever`(pgvector 코사인), `EMBEDDING_MODEL = text-embedding-3-small`, `Vector(1536)`.

## 설계

1. `ChatLongTermMemory`에 `embedding Vector(1536)` nullable 컬럼 추가(기존 행/코드 무영향).
2. Alembic `026` — 컬럼 추가(`ADD COLUMN IF NOT EXISTS`).
3. `save_long_term_memory` — 내용 텍스트화→임베딩 생성(풀모드+키 best-effort) 후 함께 저장.
4. `search_long_term_memory(project_id, query, k)` — 질문 임베딩 코사인 top-k. 임베딩/키 없으면 `get_long_term_memory` 최신순 폴백.
5. `orchestrator._ask_full` 진입부의 `get_long_term_memory(limit=3)` → `search_long_term_memory(question, k=4)`로 교체. `session_summary` 보강 로직 유지.

## 범위 밖 (후속)

- 메모리 주입을 sim/gen/management 도메인 노드까지 확대 → 서브에이전트 계약 변경 필요, 별도 작업.

## 체크리스트

- [x] models.py 컬럼 추가
- [x] alembic 026 작성
- [x] history.py 임베딩 저장 + 시맨틱 검색 함수(`ChatSessionSummary`/`search_long_term_memory`, pgvector 코사인, `text-embedding-3-small`)
- [x] orchestrator.py 진입부 시맨틱 교체 — 이후 `domain/chat/orchestrator.py` 자체가 삭제(2026-06-30 `4c3e7c8f`)되고 통합 딥에이전트로 전환됐으나, 시맨틱 검색 배선은 유지됨
- [x] ruff format + check
- [x] import/pytest 검증 — 실 DB+임베딩 라운드트립까지 완료("예산" 쿼리 top-1 회수 확인, `docs/chat/deep-agent-migration/checklist.md` 4단계)
