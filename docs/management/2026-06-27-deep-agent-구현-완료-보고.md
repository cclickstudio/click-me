# Deep Agent 오케스트레이터 구현 완료 보고

날짜: 2026-06-27 (최종 업데이트: 루프 2차 — 실측 검증 포함)

## 개요

광고 매니지먼트 어시스턴트를 단일 pass Orchestrator에서 **LangGraph 3-node Deep Agent**로 교체했다.  
채팅 전체를 OpenAI GPT로 전환하고, faithfulness judge만 Gemini(자기교정 CRAG 구조)를 사용한다.

---

## LLM 전환 내역

| 구성요소 | 이전 | 현재 |
|----------|------|------|
| CLIO 어드바이저 | Gemini 2.5 Flash | OpenAI GPT-4o-mini |
| 의도 분류기 | Gemini 2.5 Flash | OpenAI GPT-4o-mini |
| Management 에이전트 | OpenAI GPT-4o-mini | 동일 (변경 없음) |
| Generator 에이전트 | Gemini (슬롯필링) | 동일 (변경 없음) |
| Faithfulness Judge | OpenAI GPT-4o-mini | **Gemini 2.0 Flash Lite** |

---

## RAG 평가 실측값 (2026-06-27)

| 지표 | 실측값 | 목표 | 달성 |
|------|--------|------|------|
| Hit Rate@5 | **0.95** | ≥ 0.80 | ✅ |
| MRR | **0.86** | ≥ 0.60 | ✅ |
| Context Precision | **0.86** | ≥ 0.75 | ✅ |
| Faithfulness (Judge: Gemini) | **1.00** | ≥ 0.85 | ✅ |

- QA쌍 수: 20건 (생성 모델: gpt-4o-mini)
- Miss 케이스(1건): "인지도 목표로 광고를 운영하면 어떻게 해야 하나요?"

---

## 채팅 3경로 실측 테스트 (2026-06-27)

| 경로 | 질문 예시 | source | engine |
|------|-----------|--------|--------|
| Generator | "광고 카피 만들어줘" | generator | Gemini · 슬롯필링 |
| Management | "이번달 Meta 캠페인 성과 어때" | management | OpenAI · 실측+KB |
| CLIO | "광고란 무엇인가요" | clio | OpenAI GPT |

---

## 커밋 이력

| 태스크 | 커밋 | 내용 |
|--------|------|------|
| Task 1 | `1329004` | KB 인제스터 startup 자동 연결 |
| Task 2 | `885b456` | RAG 평가 시스템 — Hit Rate@k, MRR, Context Precision |
| Task 3 | `6dfb7ac` | Deep Agent 오케스트레이터 LangGraph 구현 |
| Task 4 | `ccc4655` | Wiring + chat.py Deep Agent 일원화, 키워드 분류 제거 |
| Task 5-7 | `a5c4208` | HITL 타입 보강 + /kb/eval/faithfulness 엔드포인트 |
| LLM 전환 | `8f60717` | 채팅 전체 OpenAI 전환 + judge Gemini 분리 |
| 분류 개선 | `81a1fe8` | 의도 분류 3분류 프롬프트 명확화 + Unicode 수정 |

---

## 최종 종료 체크리스트

- [x] `pytest` 회귀 없음 (675 passed, 1 pre-existing SSR failure)
- [x] 채팅 management 경로 — 실측+KB 인용 응답
- [x] 채팅 generator 경로 — 슬롯필링 응답
- [x] 채팅 CLIO 경로 — OpenAI GPT 응답
- [x] `/api/chat/approve` — HITL executor 연결 (Meta 미연결 환경에서 platform_error 정상)
- [x] Hit Rate@5 ≥ 0.80 → **0.95**
- [x] MRR ≥ 0.60 → **0.86**
- [x] Context Precision ≥ 0.75 → **0.86**
- [x] Faithfulness ≥ 0.85 → **1.00** (judge: Gemini 2.0 Flash Lite)

---

## 아키텍처 요약

```
채팅 요청
    └─ chat.py _get_orchestrator()
        └─ build_deep_agent(settings) [wiring.py]
            ├─ 의도 분류: ChatOpenAI(gpt-4o-mini)
            │   generate → Deep Agent Graph → ask_generator
            │   manage   → Deep Agent Graph → ask_management
            │   advise   → OpenAI CLIO (폴백)
            └─ build_deep_agent_graph(llm, mgmt_handler, gen_handler)
                ├─ orchestrate: LLM 도구 선택 (act-first, MAX_ITER=3)
                ├─ dispatch: management / generator 서브에이전트 실행
                └─ route → END

RAG 자기교정 (CRAG) 구조:
    KB 검색 → 신뢰도 평가 → 불충분 시 웹검색 보강
    Faithfulness Judge: Gemini 2.0 Flash Lite (OpenAI 답변 vs KB 근거 비교)
```
