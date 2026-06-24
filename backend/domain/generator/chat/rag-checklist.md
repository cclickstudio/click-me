# generator 챗봇 RAG 체크리스트 — 인메모리 KB retriever + 답변 분기 (A안)

> 목표: generator 챗봇이 광고 크리에이티브 질문에 KB(`ad-image-knowledge-base.md`) 근거로 답하고 출처를 인용한다.
> 저장 = 인메모리 임베딩(테스트 우선, DB·Alembic·공통부 변경 0). 인터페이스는 매니지먼트 pgvector retriever와 동일 형태 → 추후 승격 가능.
> 상세 배경은 rag-context-notes.md 참고.

## ① KB 문서 반입

- [ ] `ad-image-knowledge-base.md`(현재 Downloads) → `domain/generator/chat/kb/`로 이동
- [ ] 첫 줄 한국어 헤더 주석은 마크다운 문서라 불필요(이미 제목/설명 존재) — 규칙 6은 .py 대상

## ② 인메모리 retriever (`domain/generator/chat/kb_retriever.py`, 신규)

- [ ] lazy 싱글턴: 최초 호출 시 `kb/*.md` 로드 → `##`/`###` 단위 청킹
- [ ] OpenAI `text-embedding-3-small`(1536) 1배치 임베딩 → 벡터를 메모리 보관(numpy)
- [ ] `search(query, k=4)` → 코사인 top-k, 반환 `{source, title, chunk, score}` (매니지먼트와 동일 형태)
- [ ] embed 클라이언트 주입 가능(테스트용 — 네트워크 없이 가짜 임베딩)
- [ ] (선택) 임베딩 결과 `.json` 캐시 → 재기동 시 재임베딩 skip

## ③ 답변 분기 연결 (A안 — generator 안 advice)

- [ ] 사용자 메시지가 슬롯 정보가 아니라 크리에이티브 질문일 때 분기(슬롯 추출 비어있음 + 질문형)
- [ ] KB top-k 검색 → LLM이 근거+인용으로 답변(`generator_chat_model` 재사용)
- [ ] 답변 `meta.citations`에 출처(source·title) 실어 프론트로 전달(매니지먼트 meta 형태 참고)
- [ ] 슬롯필링 루프(ASK/TRIGGER)는 그대로 — "질문이면 답, 정보면 슬롯" 분기만 추가

## ④ 테스트 (`tests/generator/test_kb_retriever.py`, 신규)

- [ ] 가짜 embed 클라이언트로 청킹 개수 검증
- [ ] 특정 질문이 기대 섹션을 top-1로 끌어오는지 검증(코사인 랭킹)
- [ ] 답변 분기 단위 테스트(질문 → citations 포함 결과)

## ⑤ 검증·마무리

- [ ] `cd backend && uv run ruff format . && uv run ruff check . --fix`
- [ ] `cd backend && uv run pytest tests/generator/ -v`
- [ ] 실제 챗봇에서 "클릭률 높이려면 이미지 어떻게?" 류 질문 → 인용 표시 확인
- [ ] 커밋: `add: generator 챗봇 KB RAG(인메모리) 추가`

## 범위·비범위

- DB·Alembic·`core/models.py`·`api/main.py` 변경 없음(공통부 무수정).
- 신규 파일 위주, 기존 수정은 답변 분기 한 곳(slot_agent 경로).
- pgvector 승격은 이번 범위 밖 — 인터페이스만 호환 유지.
