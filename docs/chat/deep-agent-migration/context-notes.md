# context-notes — Chat을 Deep Agent 방식으로 전환 (작업 노트)

> 1단계(분석·계획) 산출물. 코드 수정 없음. 우리 chat 전체 vs Deep Agent 자산 전수 비교 결과와 위젯 보존 설계를 담는다.
> 작성 2026-06-29 · 브랜치 feat/chat-simulation (1edaacc, 미푸시)

---

## 0. 한 줄 결론 (먼저)

분석 결과, 작업 지시의 전제 두 가지가 실제 코드와 어긋난다. **"Deep Agent로 전체 치환"은 우리가 만든 거의 전부(위젯 14개·엔드포인트 22개·SSE·LTM·개선루프)를 버리는 후퇴**가 된다. 올바른 방향은 **치환이 아니라 "흡수 통합"** — 우리 chat 인프라를 골격으로 두고 Deep Agent의 핵심 가치(멀티도메인 한 턴 합성 + 추천 조치 카드)만 우리 오케스트레이터의 한 경로로 흡수한다.

---

## 1. 가정 정정 (분석으로 뒤집힌 전제)

### ① management dev 전환 → **불필요/유해**
- 지시: "management가 ours라 장기기억(memory_context/memory_store) 미지원 → dev management로 전환 필요".
- **실제**: ours(현재)가 `memory_store.py`(SqlMemoryStore + ManagementMemory.remember/recall)와 `AskRequest.memory_context` 주입(`agent.py:167-178`)을 **완전 구현**했다. dev 브랜치에는 `memory_store.py`가 **없고**(`git show dev:...` 확인) agent.py가 `memory_context`를 쓰지 않는다.
- **결론**: dev로 바꾸면 장기기억을 오히려 **잃는다**. management는 **ours 유지**가 맞다. 배선만 추가하면 된다(아래 4.3).

### ② Deep Agent "추천카드(meta.cards) 중심" → **카드는 Deep Agent 본체 산물이 아님**
- meta.cards(EVIDENCE/RESULT/REVIEW/ACTIONBAR)는 `domain/management/assistant/composer.py`의 `compose_turn()`이 생성한다. Deep Agent 오케스트레이터 본체(`deep_agent.py`)는 카드를 직접 만들지 않고, management 하위 서브그래프 결과의 meta를 합칠 뿐이다.
- 게다가 **프론트에는 meta.cards 렌더가 아예 없다**(우리 UI는 meta.widget 기반). 카드를 살리려면 프론트에 신규 렌더를 추가해야 한다.

---

## 2. 핵심 사실 — Deep Agent는 "오케스트레이터 함수"일 뿐, 인프라가 없다

| 구성요소 | 우리 chat (ours, 작동 중) | Deep Agent (보존만, 미사용) |
| --- | --- | --- |
| chat 엔드포인트 | **22개** (complete·approve·loop-state·sessions·notifications·widget-messages·read·pin·image·result-summary·kb-chunk·feedback·keywords·templates·report·sim-batch) | **0개** (라우터 없음) |
| SSE 스트리밍 | progress·meta·text·approval·done | **없음** (SubagentResult 1개만 반환) |
| 위젯 | 14개 (sim_form/gen_form/sim_result/debate_stream/debate_summary/sim_list/gen_list/batch/report/...) | **없음** (도구 2개만: ask_management·ask_generator) |
| 라우팅 | classify_intent(LLM 1회) → route → 단일 도메인 노드 + 결정론 분기 10종 | **LLM tool-calling 루프(MAX_ITER=3, act-first)** ← Deep Agent의 진짜 장점 |
| 멀티도메인 한 턴 합성 | 약함(단일 라우팅, 개선루프는 승인 왕복) | **강함**(management→generator management_context 전달, 한 턴에 엮음) |
| 장기기억(LTM) | 시맨틱 검색 완비(history.py + memory_store.py) | memory_context 주입 훅만(handler가 받음) |
| 개선 루프 HITL | loop_state(0~3턴) + approval + /approve | 없음(requires_approval 플래그만) |
| 추천 조치 카드 | 없음 | meta.cards(단 management composer 산물) |

**핵심**: 양쪽은 같은 목표(3도메인 한 창구)의 **다른 라우팅 구현**이다. 우리는 분류+결정론, Deep Agent는 LLM 도구루프. 정본 `docs/chat/architecture.md`의 to-be(도구 오케스트레이터)는 사실 Deep Agent 쪽 그림에 가깝다 — 단 우리는 그 위에 위젯·SSE·LTM·개선루프를 **이미 다 올려놨다**.

---

## 3. 공유 계약 (이미 양쪽을 잇는 다리)

- `core/assistant_contracts.py`: **SubagentRequest / SubagentResult / Action(ASK·TRIGGER·ANSWER)** — Deep Agent와 도메인 핸들러가 공유.
- `domain/management/assistant/contracts.py`: AskRequest(**memory_context 포함**) / AskResult.
- 우리 orchestrator.py의 management_node도 AskRequest를 쓴다 → **계약은 이미 호환**. 어댑터 비용이 작다.

---

## 4. 설계안 — "흡수 통합" (추천)

우리 `domain/chat/orchestrator.py`를 골격으로 유지하고, Deep Agent의 멀티스텝 도구루프를 **한 경로로 흡수**한다.

### 4.1 라우팅 — deep 경로 신설
- classify_intent에 결과가 **여러 도메인을 엮어야 하는 복합 질의**(예: "성과 나쁜 캠페인으로 새 시안 뽑아줘")면 `intent="deep"`로 분기.
- deep_node에서 `build_deep_agent` 루프를 호출(ask_management/ask_generator tool-calling, act-first, MAX_ITER=3) → 최종 SubagentResult.
- 단일 도메인·결정론 트리거(시뮬/생성 실행, 템플릿, 리포트, 비교)는 **기존 경로 그대로** — 위젯이 여기서 나오므로 절대 건드리지 않는다.

### 4.2 위젯을 Deep Agent에 살리는 법 (가장 중요)
Deep Agent 응답을 우리 SSE/위젯 프로토콜로 **변환(adapt)** 한다. Deep Agent는 위젯을 모르므로, 변환은 chat.py(또는 deep_node)에서 한다.

| Deep Agent 산출 | 변환 → 우리 프로토콜 |
| --- | --- |
| SubagentResult.message | `text` 토큰 스트림(24자 청크) |
| meta(source·engine·citations·used_tools) | `meta` 이벤트 그대로 |
| meta.requires_approval / suggested_action | `approval` 이벤트 + (신규) meta.cards 렌더 |
| generator subagent가 Action.TRIGGER | **meta.widget = gen_form**으로 변환(우리 GenFormWidget 재사용) |
| simulation 트리거 의도 | **meta.widget = sim_form**으로 변환(우리 SimFormWidget 재사용) |
| 추천 조치(suggested_action) | **meta.cards**(신규 프론트 렌더) — 카드의 "행동 제안"을 우리 approval/위젯으로 매핑 |

→ **결과**: 위젯은 우리 것 100% 보존. Deep Agent는 "무엇을 할지" 결정만 하고, "어떻게 보여줄지"는 우리 위젯 레이어가 맡는다.

### 4.3 장기기억 배선 (ours 유지 + 훅 연결)
- 턴 시작: `ManagementMemory.recall(tenant, user, query)` → `SubagentRequest.memory_context`에 주입(Deep Agent가 이미 받음, `deep_agent.py:176-188`).
- 턴 종료: 유의미한 선호·결정 요약을 `remember(...)`로 적재(백그라운드).
- DB: `management_user_memory`(embedding vector(1536)) — alembic 029(user_memory_embedding) 적용 필요(아래 6).

### 4.4 엔드포인트 — 전부 유지
22개 chat 엔드포인트는 우리 라우터가 그대로 소유. Deep Agent는 complete/approve 안쪽의 **오케스트레이터 호출만 교체**(deep 경로). 나머지 20개(세션·알림·위젯메시지·이미지·...)는 무변경.

---

## 5. 대안 — "곧이곧대로 전체 치환" (비추천)
- chat.py를 build_deep_agent 단일 경로로 바꾸고 위젯을 Deep Agent SSE에 끼워 맞춘다.
- 비용: 위젯 14개·결정론 분기 10종·개선루프·LTM 검색을 Deep Agent 위에 **재구현**해야 함. Deep Agent엔 SSE조차 없어 스트리밍부터 새로 짠다.
- 리스크: 회귀 면적 거대, 발표 일정(2026-07-08 구현/07-14 발표) 압박. 위젯 보존(지시 필수조건)과 정면 충돌.

---

## 6. Alembic — multiple heads 정리 (4단계)
- 충돌 8지점: 019·020·024·025·026·027·028·029가 feat/chat-simulation ↔ dev 양쪽에 중복.
- 전략: dev를 primary로, feat 변경을 그 뒤에 선형 삽입 → 단일 head. 029(management_user_memory.embedding, M6) 포함.
- 상세 재번호 초안은 checklist.md의 4단계 표 참조.
- `alembic upgrade head` 현재 막힘(중복 revision) → 재번호 후 해제.

---

## 7. 결정 (2026-06-29 사용자 확정)
1. **전략**: ✅ **흡수 통합** — 우리 인프라 골격 유지 + Deep Agent 도구루프를 deep 경로로 흡수.
2. **management**: ✅ **ours 유지** — memory_store/recall/memory_context 그대로 쓰고 배선만 추가. dev 전환 안 함.
3. **추천 조치 카드(meta.cards)**: ✅ **이번에 프론트 렌더까지 추가** — EVIDENCE/RESULT/REVIEW/ACTIONBAR 카드를 ChatConversation에 신설.
