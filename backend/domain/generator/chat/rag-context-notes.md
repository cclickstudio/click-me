# generator 챗봇 RAG 컨텍스트 노트

> 작성 2026-06-25. generator 챗봇에 KB 근거 답변(RAG)을 붙이는 작업의 배경·결정·주의점.
> 진행 체크리스트는 rag-checklist.md.

## 무엇을 / 왜

- 목표(시연 항목): "챗봇 기능 구현 ★", "챗봇에 RAG 사용해보기 ★".
- 챗봇 골격은 이미 동작 — `api/routers/chat.py`가 SSE 스트리밍 + 오케스트레이터(의도분류→서브에이전트) + 세션 저장까지 함.
- RAG도 매니지먼트는 이미 완성형(`domain/management/assistant/`: kb/*.md → kb_ingest → pgvector(ManagementKbChunk) → retriever 코사인 top-k).
- generator 챗봇은 슬롯필링만 있고 RAG·답변 분기가 없음 → 여기에 RAG를 붙이는 게 목표와 도메인 소유(현 브랜치 feat/generator-*)에 맞음.

## 현재 코드 사실관계(확인됨)

- generator 챗봇 실제 진입점 = `domain/generator/chat/slot_agent.py`의 `build_generation_chat_agent`.
  - 오케스트레이터 wiring(`api/assistant/wiring.py`)이 `Intent.GENERATE`에 이걸 등록.
  - slot_agent는 `ASK`(슬롯 되묻기) / `TRIGGER`(생성 시작)만 반환 — **질문에 답하는 브랜치 없음**.
- `domain/generator/chat/agent.py`의 `run_agent`(일반질문 응답 포함)는 오케스트레이터에 연결 안 된 사실상 죽은 경로. 이번에 재사용/정리 여부는 구현 시 판단(우선 건드리지 않음).
- 설정: `settings.openai_api_key` 있음, `settings.generator_chat_model = "gpt-4o-mini"`. 별도 임베딩 모델 설정 없음 → 매니지먼트처럼 `text-embedding-3-small` 하드코딩.
- `numpy>=1.26` 이미 의존성(인메모리 코사인용). pgvector는 이번에 불필요.

## 핵심 결정

- **저장 방식 = 인메모리 임베딩**(테스트 우선). 근거: KB 단일 파일(~840줄, ~50청크)이라 1배치 임베딩이면 충분하고, DB 변경·Alembic·공통부 마찰 0. retriever 반환 형태를 매니지먼트와 동일하게 맞춰 추후 pgvector 승격 시 인터페이스 호환.
- **답변 위치 = A안(generator 안 advice 핸들러)**. CLIO 폴백(B안)은 도메인 경계가 흐려져 제외.

## 주의점 / 열린 항목

- 매니지먼트 retriever 반환 형태를 기준 삼을 것: `{source, title, chunk, score}`. score = `1 - cosine_distance`.
- 매니지먼트 청킹은 `## 헤딩` 단위. KB 문서는 `##`(대섹션)+`###`(하위) 구조 → 청크 입자 크기 결정 필요(너무 크면 검색 정밀도↓). 구현 시 `###`까지 분해하는 쪽으로 시작.
- "질문 vs 슬롯 정보" 분기 판정 방식 미확정 — 슬롯 추출 결과가 비고 + 질문형(물음표/의문어) 휴리스틱으로 시작, 과하면 LLM 분류로 승격.
- citations는 매니지먼트 meta 형태(`citations: [{kind, source, title}]`) 참고해 프론트 호환 유지.
- 협업 규칙: 공통부(`core/models.py`·`api/main.py`·공용 tools) 무수정 — 이번 작업은 generator 도메인 내부로 한정.
