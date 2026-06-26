# Deep Agent 오케스트레이터 구현 완료 보고

날짜: 2026-06-27

## 개요

광고 매니지먼트 어시스턴트를 단일 pass Orchestrator에서 **LangGraph 3-node Deep Agent**로 교체했다. management·generator 두 서브에이전트를 도구(function calling)로 등록해 act-first 전략으로 호출하고, 결과를 합성해 최종 답변을 반환한다.

---

## 커밋 이력

| 태스크 | 커밋 | 내용 |
|--------|------|------|
| Task 1 | `1329004` | KB 인제스터 startup 자동 연결 |
| Task 2 | `885b456` | RAG 평가 시스템 — Hit Rate@k, MRR, Context Precision |
| Task 3 | `6dfb7ac` | Deep Agent 오케스트레이터 LangGraph 구현 |
| Task 4 | `ccc4655` | Wiring + chat.py Deep Agent 일원화, 키워드 분류 제거 |
| Task 5-7 | `a5c4208` | HITL 타입 보강 + /kb/eval/faithfulness 엔드포인트 |

---

## 구현 결과

### Task 1 — KB 인제스터 startup 연결

- `backend/api/main.py` lifespan에 `asyncio.create_task(ingest())` 추가
- 백엔드 기동 시 KB DB 자동 갱신, 실패해도 서버 기동 방해 없음

### Task 2 — RAG 평가 시스템

- `backend/domain/management/assistant/rag_eval.py` (신규)
  - `generate_qa_pairs(limit=50)`: gpt-4o-mini로 QA쌍 자동 생성
  - `evaluate(k=5)`: Hit Rate@k, MRR, Context Precision 계산
  - `evaluate_faithfulness(n=30)`: LLM as Judge faithfulness 측정
- `GET /api/management/kb/eval/run?k=5`
- `POST /api/management/kb/eval/generate?limit=50`
- `GET /api/management/kb/eval/faithfulness?n=30`
- 목표 기준: Hit Rate@5 ≥ 0.80, MRR ≥ 0.60, Context Precision ≥ 0.75, Faithfulness ≥ 0.85

### Task 3 — Deep Agent LangGraph 구현

- `backend/api/assistant/deep_agent.py` (신규)
- **3-node 구조**: `orchestrate → dispatch → orchestrate` 루프, `END`
- **MAX_ITER=3** — 비용 상한
- **act-first**: 첫 이터레이션에서 적합한 도구 즉시 호출 유도
- **HITL 처리**: `requires_approval=True` 감지 시 추가 도구 호출 없이 종료
- **State 필드**: messages, orig_messages, sub_results, iteration, thread_id, requires_approval, session_id, context_ad_id
- **Mock 핸들러**: `_mock_management`, `_mock_generator` — 실 구현 교체 전 fallback

### Task 4 — Wiring + chat.py 일원화

- `api/assistant/intent.py`: `classify_intent()` llm=None → Intent.ADVISE (키워드 폴백 완전 제거)
- `api/assistant/wiring.py`: `build_deep_agent()` 추가 — management+generator+llm 조립
- `api/routers/chat.py`: `_is_management()+_get_assistant()` 제거 → `_get_orchestrator()` 단일 경로
  - Deep Agent 응답 → SSE meta+tokens
  - management 응답 시 `record_turn()` + `_get_memory().remember()` 자동 호출
  - ADVISE → Gemini CLIO 폴백

### Task 5 — HITL thread_id 종단 검증

HITL 흐름 검증 완료:

```
agent.py interrupt() → AskResult(thread_id="mgmt-xxx", requires_approval=True)
    → wiring.py meta["thread_id"] = result.thread_id
    → deep_agent.py dispatch: _OState.thread_id 저장
    → _state_to_result: SubagentResult.meta["thread_id"]
    → chat.py SSE: {"meta": {"thread_id": "mgmt-xxx", "requires_approval": true}}
    → POST /api/chat/approve: Executor 실행
```

### Task 6 — QA 검토

- Ruff 전체 통과 (`All checks passed`)
- TypeScript 전체 통과 (`exit code 0`)
- 교차 도메인 import 없음 (wiring.py Composition Root 경유만)
- 미완성 코드 없음 (`...` / `# TODO` / `raise NotImplementedError` 0건)
- mock 핸들러 wiring.py 잔존 없음

### Task 7 — LLM as Judge Faithfulness

- `GET /api/management/kb/eval/faithfulness?n=30` 엔드포인트 추가
- `evaluate_faithfulness()` 함수 Task 2에서 구현 완료 (llm 지연 초기화)
- 판단 기준: ≥ 0.85 발표 가능, 0.70~0.84 개선 여지, < 0.70 RAGAS 미달

---

## 테스트 결과

```
tests/assistant/ + tests/management/test_chat_memory.py + tests/management/test_assistant*.py
30 passed, 2 warnings in 1.69s
```

Ruff: `All checks passed`
TypeScript: `exit code 0`

---

## 미검증 항목 (런타임 의존)

- `/api/management/kb/eval/run?k=5` Hit Rate@5 실측값 — DB에 QA쌍 생성 후 측정 필요
- `/api/management/kb/eval/faithfulness?n=30` 실측값 — 동일
- Deep Agent 실환경 동작 — GEMINI_API_KEY 설정 시 act-first 라우팅 검증 필요

---

## 아키텍처 요약

```
채팅 요청
    └─ chat.py _get_orchestrator()
        └─ build_deep_agent(settings) [wiring.py]
            └─ build_deep_agent_graph(llm, management_handler, generator_handler)
                ├─ orchestrate: LLM 도구 선택 (act-first, MAX_ITER 상한)
                ├─ dispatch: management / generator 서브에이전트 실행
                │   ├─ ask_management → _build_management_handler → AskResult
                │   └─ ask_generator → build_generation_chat_agent → SubagentResult
                └─ route: tool_calls → dispatch, 없음 → END
```
