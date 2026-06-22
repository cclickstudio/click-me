# 채팅 어시스턴트 — 매니지먼트 서브에이전트 (Agentic RAG, 에이전틱 RAG)

작성: 2026-06-21 · 도메인: management(4-2) · 역할: 🅰 (읽기·분석, Writer 미호출)

## Context (배경)

채팅 어시스턴트(4-4)를 **오케스트레이터(orchestrator, 조율자)** 로 두고, 시뮬레이션·생성·매니지먼트를 각각 **서브에이전트(sub-agent, 하위 에이전트)** 로 붙이는 구조를 지향한다. 공통 오케스트레이터 본체는 아직 소유자가 미정이므로, 매니지먼트는 **독립적으로 동작하는 서브에이전트**로 먼저 완성한다. 추후 오케스트레이터는 이 서브에이전트를 **툴(tool, 도구) 하나로 등록**만 하면 된다 — 화면·API 변경 없이.

설계 결정: **하이브리드 검색(hybrid retrieval) + CRAG-lite 자기교정(self-correction)** 기반 **에이전틱 RAG**.

## 핵심 원칙

- **숫자는 실측, 판단은 지식** — 수치(CTR·소진·ROAS)는 항상 실시간 툴(live tool, Meta 실측)에서 가져오고, 원인·방법·정책은 지식베이스(KB, knowledge base)에서 근거로 인용한다. LLM이 숫자를 지어내지 못하게 하는 **환각 방지(grounding, 근거기반)** 장치.
- **스케일 환산 금지** — 예측(prediction, 상대 지표 0~1·1~5·0~100)과 실측(actual, 절대 지표 CTR·CVR·ROAS)은 단위가 달라 수치로 환산하지 않는다. 방향성(directional)만 비교.
- **읽기 + 행동 제안(read + suggest)** — 조회·분석에 더해, 행동 의도(일시중지·게재시작·증액 등)는 추천 액션(action_type·Tier·근거)으로 **제안만** 한다. 실제 실행은 직접 하지 않고 기존 **승인(approval)→실행기(executor) 경로**(Tier 게이트)로 사람 확인 후 처리.
- **무키 폴백(keyless fallback)** — LLM·임베딩 키가 없거나 데모(mock) 모드면, 키워드 라우팅 + 실시간 툴 요약으로 동작(재현성 게이트 유지).

## 검색 두 갈래 (Hybrid Retrieval)

1. **실시간 툴 검색 (structured / live)** — 캠페인 목록·예산 페이싱(pacing)·캠페인 상세·집행 전후 비교(before/after)를 Meta 실측으로 조회. 기존 reader·comparison·prediction 자산을 재사용한다(중복 구현 없음).
2. **벡터 검색 (unstructured / vector)** — 정책(policy)·최적화 플레이북(playbook)·KPI 측정 규칙을 마크다운으로 큐레이션해 청크(chunk)·임베딩(embedding) 후 **pgvector 코사인 유사도(cosine similarity)** 로 검색. 답변에 출처(citation, 인용)를 단다.

## 그래프 흐름 (CRAG-lite, LangGraph)

```
route(라우팅) → retrieve(검색: live + vector) → grade(근거 채점)
   → (부족 시 재검색, 최대 1회) → generate(근거 기반 생성·인용)
```

- **route** — 질문을 분류: 실시간 수치가 필요한가, 지식이 필요한가, 특정 캠페인인가.
- **retrieve** — 분류에 따라 실시간 툴 호출 + 벡터 검색.
- **grade** — 모은 근거가 답하기에 충분한지 평가. 부족하면 검색 폭을 넓혀 한 번 더(self-correction) → 이것이 단순 ReAct와 구분되는 "agentic" 지점.
- **generate** — 검색된 근거만으로 한국어 답변 + 인용. 수치는 실시간 근거에서만.

## 인터페이스 (오케스트레이터 연결 seam)

- 단일 진입점 `build_management_agent(settings) → ask(question, context) → AskResult`.
- 결과(AskResult): 답변(answer) + 인용(citations: live/kb 출처) + 사용한 툴(used_tools) + 실측 근거(evidence).
- 검증·데모용 HTTP 엔드포인트도 제공 — 채팅 UI 없이 단독 호출 가능.
- 오케스트레이터 확정 시: 이 진입점을 "management 서브에이전트" 툴로 등록. **시뮬·생성도 동일 패턴으로 각자 서브에이전트를 만들어 붙이면 됨.**

## 스택 재사용 (추가 의존성 최소)

- **pgvector** (NeonDB, vector 1536) — 기존 임베딩 테이블과 동일 차원.
- **임베딩** — OpenAI `text-embedding-3-small`.
- **LLM** — 설정 분기(기본 OpenAI, Gemini 가능). route·grade·generate에 사용.
- **추적/평가** — LangSmith 트레이싱(연결됨), 평가셋(evals)으로 회귀 측정 가능.

## 운영 메모

- 적용 순서: DB 마이그레이션 → 지식베이스 인제스천(ingestion) → 엔드포인트 사용.
- Meta 요청 한도(rate limit)는 `{error: rate_limited}`로 표면화해 "데이터 없음"과 구분. 공통 클라이언트의 GET 캐시(TTL)로 호출량 절감.
- 지식베이스 미적재 시에도 실시간 툴만으로 답하도록 degrade(우아한 저하).

## 범위 밖 (후속)

- 공통 채팅 오케스트레이터 본체 · 시뮬/생성 서브에이전트 · 세션 영속화(session persistence) · 프론트 채팅 UI 연동 · 예측 보정(calibration).
