# 채팅 통합 아키텍처 & KB-RAG 설계 구조도 (2026-06-28 전면 개정)

> 작성: 보은(Phase 1 RAG 설계) · 종합·검증: 경구
> 범위: 채팅 4-4 전체 — Deep Agent 오케스트레이터 + management 서브에이전트(경구 베이스 + 보은 카드/RAG 강점) + 미래 시뮬·제너 툴 연결
> 상태: **코드·DB·브랜치·.env 실측 검증 완료 (2026-06-28)**. 구현 갭 목록은 §11.
> 검증 방식: 실제 파일 `file:line` 직접 확인 + Neon DB 라이브 조회 + 3개 브랜치 트리 확인. 추측 없음.

---

## 0. 설계 원칙 (이 문서의 판단 기준)

1. **메인 오케스트레이션은 Deep Agent(LLM tool-calling)** — 키워드 라우팅 금지(멘토 가이드). LLM이 스스로 도구를 고른다.
2. **management = 경구 베이스 + 보은 강점** — 경구의 CRAG ReAct + HITL 위에 보은의 TurnEnvelope 카드 계층과 RAG 게이트 설계를 더한다.
3. **시뮬·제너는 미래 툴** — 도연·태호(시뮬), 요한·윤섭(제너)이 완성하면 `ask_simulator`/`ask_generator` 도구로 붙인다. 지금 구조만 열어둔다.
4. **도메인 경계 준수** — 시뮬레이터 지식을 management KB에 섞지 않는다(검색 오염 방지, §7).
5. **단일 출처** — 체크포인터·정책·임베딩 모델은 한 곳에서만 정의(중복 금지).

---

## 1. 전체 아키텍처

```
사용자 (frontend chat/page.tsx)
   │  POST /api/chat/complete  (SSE)
   ▼
api/routers/chat.py  ─ chat_complete()
   │
   ▼
api/assistant/wiring.py ─ build_deep_agent(settings).run(req)
   │
   ├─ classify_intent (LLM gpt-4o-mini, intent.py)  ※ 키워드 아님
   │     MANAGE / GENERATE / ADVISE  (enum엔 SIMULATE·RETRIEVE도 이미 존재)
   │
   ├─ MANAGE / GENERATE ──▶ Deep Agent 루프 (deep_agent.py, LangGraph 3노드)
   │                          orchestrate ⇄ dispatch, MAX_ITER=3
   │                          ├─ ask_management 도구 ─▶ management 서브에이전트
   │                          │     (agent.py → graph.py: CRAG ReAct + interrupt HITL)
   │                          └─ ask_generator 도구 ─▶ generator 챗 에이전트
   │
   └─ ADVISE ──▶ [현재] return None → CLIO 폴백
                 [목표] KB 게이트 → cosine≥0.35면 인용 답변, 아니면 CLIO

   ▼ (미래)
   ├─ SIMULATE ─▶ ask_simulator 도구 (도연·태호 완성 후)
   └─ (generator 실연동 후 ask_generator 교체: 요한·윤섭)
```

**두 오케스트레이터가 공존한다(중요).**
- `build_deep_agent` (deep_agent.py) — **chat.py가 실제로 쓰는 것**. LLM tool-calling 루프.
- `build_assistant` (wiring.py:80, Orchestrator 클래스) — 단일 패스. **chat.py 미사용(레거시)**. 혼동 주의.

---

## 2. 현재 코드 실측 인벤토리 (검증 완료)

| 컴포넌트 | 파일·위치 | 상태 |
|---|---|---|
| 채팅 엔드포인트 | `api/routers/chat.py:99` `chat_complete` | SSE `token`/`meta`/`done` raw 스트리밍 |
| 오케스트레이터 조립 | `api/assistant/wiring.py:90` `build_deep_agent` | intent 분류 → MANAGE/GENERATE/ADVISE |
| Deep Agent 그래프 | `api/assistant/deep_agent.py:116` `build_deep_agent_graph` | 3노드 루프, **MemorySaver 하드코딩(:244)** |
| 의도 분류 | `api/assistant/intent.py:107` `classify_intent` | **LLM 분류(키워드 폴백 제거됨)** |
| management 진입 | `domain/management/assistant/agent.py:98` `build_management_agent` | full=CRAG, fallback=키워드+live |
| management 그래프 | `domain/management/assistant/graph.py:121` `build_graph` | **CRAG-lite + interrupt() HITL 구현됨** |
| KB 하이브리드 검색 | `domain/management/assistant/retriever.py` | **cosine_score + status=active 완료** |
| KB 적재 | `domain/management/assistant/kb_ingest.py:127` | **`glob("*.md")` — 서브디렉토리 미탐색(버그)** |
| 카드 컴포저 | `domain/management/assistant/composer.py` | 보은 체크아웃, `compose_turn`/`stream_turn` **미배선** |
| 카드 계약 | `domain/management/assistant/chat_cards/models.py` | EVIDENCE/RESULT/REVIEW/ACTIONBAR |
| 체크포인터(영속) | `domain/management/assistant/checkpointer.py:21` `init_pg_checkpointer` | **AsyncPostgresSaver 싱글턴 — main.py lifespan에서 기동** |
| 체크포인터(주입) | `domain/management/wiring.py:122` `build_checkpointer` | PG 싱글턴 or MemorySaver 폴백 |
| 체크포인터(중복) | `api/assistant/checkpointer.py` `build_async_checkpointer` | **이전 세션 생성 — 위와 중복, 미배선** |
| RAG 평가 | `domain/management/assistant/rag_eval.py` | Hit Rate@5 0.95 / MRR 0.86 / CP 0.86 / Faith 1.00 |

---

## 3. Neon DB 실태 (라이브 조회, 2026-06-28)

```
management_kb_documents : 15 (전부 active)
management_kb_chunks    : 64
management_kb_eval_cases: 29
```

| source_type | 문서 수 | 성격 |
|---|---|---|
| meta_official | 6 | Meta 공식 정책·지표 |
| playbook | 4 | 운영 플레이북 |
| benchmark | 3 | KPI 벤치마크 |
| internal_policy | 2 | 내부 정책 |
| **일반 광고·마케팅 지식** | **0** | **← ADVISE KB 게이트 항상 Miss 원인** |

- 15개 문서는 **전부 `kb/` 루트 파일**(chunk.source에 서브디렉토리 prefix 없음 = `glob` 버그 실증).
- 로컬엔 `kb/external/` 3개 + `kb/persona/` 2개가 체리픽돼 있으나 **DB에 0개**(적재 안 됨).
- `ManagementKbChunk`에 **`keywords` 컬럼 없음**. `search_vector`는 기존 컬럼(title/chunk) 기반 DB 생성열 → 별도 키워드 큐레이션 불가·불필요.

---

## 4. 팀 자산 통합 결정표 (브랜치 실측 기반)

### 4-1. 보은 (`feat/chat-boeun`)

| 자산 | 성격 | 결정 | 이유 |
|---|---|---|---|
| `composer.py` + `chat_cards/` | TurnEnvelope 카드 계약 | **흡수(완료)·배선 필요** | Deep Agent와 직교. 카드 UI의 핵심 강점 |
| RAG 설계(cosine 게이트·인용검증·근거없음 정책) | 설계 문서 | **흡수 → §6 적용** | 환각 방지 게이트가 ADVISE 품질의 핵심 |
| `api/orchestration/contracts.py` (`DomainAgent.ask(ctx, step)`) | plan-execute 계약 | **거부** | 시그니처가 plan-execute 전용. 우리 핸들러는 `(SubagentRequest)→SubagentResult` |
| `registry.py` (`AgentRegistry`) | domain→agent | **개념만 차용(선택)** | Deep Agent는 이미 LLM 도구로 서브에이전트 등록. dispatch 노드 if/elif 정리에만 패턴 참고 |
| `routing.py`·`bootstrap.py` (`KeywordMatcher`/`Router`) | **키워드 라우팅** | **거부** | 멘토 가이드(키워드 금지) 위반 + LLM intent 분류와 충돌 |
| `context.py` (`TurnContext` 블랙보드) | plan-execute 상태 | **거부** | Deep Agent는 `sub_results` dict로 동등 기능 보유 |
| `policy.py` (`PIPELINE_ORDER` 등) | 멀티스텝 정책 | **거부** | plan-execute 멀티스텝 전용. Deep Agent 루프와 무관 |
| `planner.py`·`executor.py`·`turn.py` | plan→execute 본체 | **거부** | LLM tool-calling 루프와 아키텍처 충돌 |

> **핵심 정정:** 이전 세션이 보은의 `contracts/context/registry/policy` 4개 체리픽을 계획했으나, 실측 결과 이들은 **키워드 라우팅 기반 plan-execute 모델**이라 경구의 LLM Deep Agent와 충돌한다. 진짜 강점은 **카드 계층 + RAG 게이트 설계**뿐이며 그것만 흡수한다.

### 4-2. 도연 (`feat/chat-doyeon`)

| 파일 | 내용 | 결정 |
|---|---|---|
| `domain/chat/kb/advertising_general_knowledge.md` | 광고·마케팅·브랜딩·퍼포먼스 **일반 개념** | **흡수 → ADVISE KB** |
| `domain/chat/kb/marketing_terms.md` | STP·4P·USP·ROAS·CPM 등 **용어 사전** | **흡수 → ADVISE KB** |
| `domain/chat/kb/meta_platform_policy.md` | Meta 플랫폼 정책 | 후보(기존 `meta_ad_policy.md`와 중복 점검 후) |
| `domain/generator/assistant/kb/*` | 카피 전략 등 | **거부** — generator 도메인 소유 |

> 두 파일은 헤더가 "CLIO 광고 일반 질문 KB"로 **ADVISE 경로를 정확히 겨냥**. 도메인 실행지식과 중복 회피 의도까지 명시돼 있어 management KB에 안전하게 추가 가능.

### 4-3. 태호 (`feat/chat-yeotaeho`) — 이미 로컬에 체리픽됨, 재검토 결과

| 파일 (현재 `kb/`에 존재) | 실제 내용 | 결정 |
|---|---|---|
| `external/meta_reference.md` | Meta 지표 정의·심사·정책 | **유지·적재** — management 적합 |
| `external/evidence.md` | 한국갤럽 **브랜드 선호도**(페르소나 샘플링용) | **적재 제외** — 시뮬 도메인 |
| `external/kobaco_baseline.md` | KOBACO **구매의향 베이스라인**(시뮬 대조군) | **적재 제외** — 시뮬 도메인 |
| `persona/persona_methodology.md` | 페르소나 생성 방법론(OCEAN·KISDI) | **적재 제외** — 시뮬 도메인 |
| `persona/simulation_trust.md` | 시뮬 신뢰지표(CI·effective_n) | **적재 제외** — 시뮬 도메인 |

> **새 발견(설계 구멍):** 체리픽된 5개 중 **4개가 시뮬레이터 도메인 지식**이다. management KB에 적재하면 "리타게팅 뭐야"류 질문에 페르소나·구매의향 청크가 섞여 검색 정밀도를 떨어뜨린다. §7 거버넌스로 차단.

### 4-4. 태호 — domain/chat/ 전체 구조

`domain/chat/` DDD 골격 + Alembic 3개 → **거부**(우리 `api/assistant/` 구조와 충돌, 공통부 변경). 아이디어만:
- `context_ids` non-null 리듀서 패턴 → Deep Agent `_OState`가 이미 `session_id`/`context_ad_id`를 캐리. 멀티턴 맥락 유지가 필요해지면 참고.

---

## 5. RAG 적재·검색 파이프라인

### 5-1. 적재 (kb_ingest.py)

```
kb/**/*.md  ──▶  ## 섹션 청크화  ──▶  OpenAI text-embedding-3-small(1536)  ──▶  Neon
              (content_hash 멱등: 동일 해시 skip)                            management_kb_*
```

- 임베딩 모델 단일 상수: `retriever.EMBEDDING_MODEL = "text-embedding-3-small"` (벡터 컬럼 `vector(1536)`과 일치).
- 멱등: 같은 출처 active 문서가 동일 `content_hash`면 재임베딩 skip(`kb_ingest.py:122~`).
- **현재 버그:** `glob("*.md")`는 루트만 → 서브디렉토리 미적재. §11-G1.

### 5-2. 검색 (retriever.py — 하이브리드 RRF)

```
쿼리 ──┬─ 벡터 채널: 임베딩 → pgvector 코사인거리 → cosine_score = 1 - dist
       └─ 키워드 채널: websearch_to_tsquery('simple') → GIN(search_vector)
                  └─ RRF(K=60) 융합 → top-k
   (양 채널 모두 management_kb_documents JOIN, status='active' 필터)
```

- `cosine_score`는 **벡터 채널만** 보유(키워드 전용 히트는 None). RRF score(최대 ≈ 0.033)와 **별개**.
- 키워드 채널은 "ROAS·CPM·BID_LOSS" 같은 **정확 토큰** 보조용. 주축은 의미(벡터) 검색 = 멘토 가이드 부합.

### 5-3. ADVISE 근거 게이트 (보은 설계 → 적용)

```python
hits = await KbRetriever().search(query, k=4)
# top-1이 keyword-only(cosine=None)일 때 false negative 방지 → max로 판정
top_cosine = max((h.get("cosine_score") or 0.0 for h in hits), default=0.0)
if top_cosine < 0.35:        # 0.35 = 초기 설정값, eval로 조정
    return None              # → CLIO 폴백 (LLM 호출 안 함 = 비용↓·환각↓)
# 통과 → gpt-4o-mini가 [1][2] 인용하며 답변 (채팅 전체 OpenAI 정책)
```

- **인용 마커 검증:** 응답에 `[n]`이 없거나 범위 밖이면 안전 문구(`*(출처: …)*`)로 강등 → 번호 날조 방지.
- threshold 판단은 **반드시 cosine_score**. RRF score에 0.35 적용 시 항상 미통과(과거 버그).

> **참고:** management 풀모드(graph.py)의 `search_kb`는 이미 **CRAG-lite 자기교정**(근거 부족 시 쿼리 재작성·재검색·web_search 폴백)을 갖췄다(graph.py:148~181). ADVISE 게이트는 그보다 단순한 "있으면 인용/없으면 CLIO" 1차 게이트다.

---

## 6. KB 콘텐츠 거버넌스 (도메인 경계)

**원칙: management KB에는 management/일반-광고 지식만. 시뮬·제너 도메인 지식 금지.**

| 카테고리 | 적재 대상 | 출처 |
|---|---|---|
| management 운영 | 기존 15개(playbook·meta_official·benchmark·internal_policy) | 경구 |
| Meta 레퍼런스 | `external/meta_reference.md` | 태호 |
| 일반 광고·마케팅 | 도연 `advertising_general_knowledge.md` + `marketing_terms.md` | 도연 |
| Awareness·Meta 실전 | 신규 `marketing_basics.md`(도연과 중복 회피) | 경구 |
| ~~시뮬 페르소나·구매의향~~ | **적재 제외** | (태호 — 시뮬 도메인) |

**조치:** `kb/external/{evidence,kobaco_baseline}.md`, `kb/persona/*`는 적재 대상에서 제외한다. 방법 2택 —
- (A·권장) 시뮬 도메인 파일을 management `kb/`에서 제거(원 소유 도메인으로 환원). 가장 깨끗.
- (B) retriever에 `source_type` 제외 필터 추가(보은 설계 §10의 documents-join 필터 차용). 코드 변경 수반.

> MVP는 (A) 권장. 적재 화이트리스트를 `_SOURCE_META` 등록 파일로 한정하면 미등록 파일은 기본값으로 들어가므로, **rglob + 화이트리스트** 조합이 안전(§11-G1).

---

## 7. 카드(TurnEnvelope) 프로토콜 & SSE

### 7-1. 카드 슬롯 (chat_cards/models.py — 검증)

| kind | payload.type | 용도 | 등장 조건 |
|---|---|---|---|
| EVIDENCE | rag_citations | KB/실측 인용 | citations 있으면 |
| RESULT | action_proposal | 추천 조치(draft, executable=False) | suggested_action 있으면 |
| REVIEW | policy_check | Tier·승인필요 판정 | suggested_action 있으면 |
| ACTIONBAR | actions | 버튼(승인·실행은 비활성=Plan2) | suggested_action 있으면 |

- `compose_turn(res: AskResult)` (composer.py:138)이 **suggested_action 유무로 카드 자동 분기** — ADVISE(인용만)는 EVIDENCE만, MANAGE(조치)는 4개 전부. 별도 분기 로직 불필요.

### 7-2. SSE 와이어 포맷

| 경로 | 이벤트 시퀀스 |
|---|---|
| MANAGE / ADVISE(KB통과) | `conclusion_delta`×N → `card_ready`×M → `final` (stream_turn, composer.py:178) |
| CLIO 폴백 | 기존 `meta` → `token`×N → `done` 유지 |

- 프론트는 **첫 이벤트 키**(`event` vs `token`/`meta`)로 두 포맷 분기.
- `compose_turn`은 **`AskResult` 입력**. Deep Agent는 `SubagentResult` 출력 → **어댑터 필요**(§11-G3).

---

## 8. HITL (Human-in-the-loop)

**이미 구현된 부분(graph.py:196~245):**
- management `propose_action` 도구가 위험 Tier면 `interrupt({"suggested_action": …})`로 그래프 정지.
- `agent.py:180`이 `__interrupt__`를 받아 `requires_approval=True` + `thread_id` 반환.
- `/api/chat/approve`(chat.py:255)가 승인 → Executor 단일경로(Tier 재검증·멱등) 실행.

**갭:** Deep Agent 오케스트레이터는 management의 `requires_approval`만 전달받고, **`suggested_action`을 `_state_to_result`에서 누락**(§11-G2). 카드가 안 뜨는 직접 원인.

> 완전한 `interrupt` 전파(오케스트레이터가 직접 멈춤)는 선택. 현재는 management 서브그래프 정지 + 플래그 반환으로 충분(MVP). 단 §11-G2 수정 없이는 RESULT/REVIEW/ACTIONBAR 카드가 영영 안 뜬다.

---

## 9. 체크포인터 (영속) — 단일화

| Saver | 위치 | 용도 | 상태 |
|---|---|---|---|
| `init_pg_checkpointer` 싱글턴 | `domain/management/assistant/checkpointer.py` | management 그래프 interrupt·멀티턴 | **AsyncPostgresSaver, lifespan 기동 완료** |
| `build_checkpointer` | `domain/management/wiring.py:122` | 위 싱글턴 주입 or MemorySaver 폴백 | 완료 |
| Deep Agent | `deep_agent.py:244` | 오케스트레이터 루프 | **MemorySaver 하드코딩** |
| `build_async_checkpointer` | `api/assistant/checkpointer.py` | (중복) | **삭제 대상** |

- Windows는 PG 스킵(MemorySaver), Linux EC2만 Neon 영속(checkpointer.py:26~30) — **의도된 설계**.
- **단일화:** Deep Agent도 `get_pg_checkpointer()` 싱글턴을 주입받게 하고, 중복 `api/assistant/checkpointer.py`는 삭제. 신규 lifespan 배선 불필요(이미 있음).

---

## 10. 미래 확장 — 시뮬·제너 툴 연결

```python
# Intent enum엔 이미 SIMULATE 존재(assistant_contracts.py:22) → enum 변경 불필요
# deep_agent.py에 도구 추가만:
_TOOL_SPECS += [{ "name": "ask_simulator", "description": "...", "parameters": {...} }]
# dispatch 노드 if/elif에 ask_simulator 분기 추가 (또는 핸들러 레지스트리로 정리 — 보은 패턴 차용)
# wiring.py: build_generation_chat_agent처럼 simulator_handler 주입
```

- 도연·태호 simulator는 `(SubagentRequest)→SubagentResult` 핸들러 계약만 맞추면 한 줄 등록.
- generator는 현재 `build_generation_chat_agent` 연결됨(요한·윤섭 실연동 시 내부만 교체).

---

## 10.5. 메모리 아키텍처 (단기·장기) — 재설계 필요

> 사용자 지적("무분별하게 가져온다")을 실측 검증한 결과, 실제 문제는 **무분별하게 *쌓기만* 하고 회수는 끊겨 있는** 것이다. 아래는 코드 근거 기반 현황과 재설계 방향.

### 10.5-1. 현재 2계층 구조 (검증)

| 계층 | 구현 | 키 | 백엔드 | 상태 |
|---|---|---|---|---|
| **단기(thread)** | 체크포인터 | Deep Agent `thread_id=session_id`(deep_agent.py:271) / management `mgmt-{session_id}` | MemorySaver / AsyncPostgresSaver | 이원화 |
| **장기(cross-session)** | `ManagementMemory`(memory_store.py:60) | `(mgmt_memory, tenant, user)` | InMemoryStore(mock) / `ManagementUserMemory`(Neon) | **write-only** |

### 10.5-2. 데이터 흐름 실측

**WRITE (chat.py:160~165)** — 매 management 턴마다 무조건:
```python
note = f"질문: {last_message[:60]}"          # 질문 첫 60자 (저품질 신호)
if sa: note += f" / 제안: {sa['action_type']}"
await _get_memory().remember(tenant_id, user_id, uuid4().hex, {"note": note})
#                                                ^^^^^^^^^^^^^ 매번 랜덤 키 = 멱등성 없음, 무한 증가
```

**READ** — 회수 체인이 **프로덕션에서 끊김**:
- `recall()`(memory_store.py:80) — **호출 위치: 테스트뿐**(grep 확인). chat.py·wiring.py 미호출.
- `_format_memory()`(chat.py:91) — **정의만, 호출 0회**.
- `AskRequest.memory_context`(contracts.py:15) → `agent.py:171`이 주입 준비됨 — **그러나 wiring 핸들러가 채우지 않음**(composer.py 핸들러는 memory_context 미설정).

> 결과: 장기기억은 **적재만 되고 답변에 1도 반영되지 않는다**. 회수 부품(recall·_format_memory·memory_context)은 다 있는데 **중간 배선(chat.py가 recall→주입)만 빠졌다**.

### 10.5-3. 메모리 설계 구멍 (M-시리즈)

| ID | 구멍 | 근거 | 영향 |
|---|---|---|---|
| **M1** | 장기기억 write-only(회수 미배선) | recall 호출 0회(grep) | 기억해도 안 씀 — 기능 무효 |
| **M2** | 무분별 적재(salience·요약·dedup 없음) | chat.py:160~165, key=uuid4 | 저품질 노트 무한 증가, 토큰·비용·노이즈 |
| **M3** | anon 네임스페이스 충돌 | `_resolve_identity`→(None,None)→(global,anon) | 회수 배선 시 **타 사용자 기억 누출**(프라이버시) |
| **M4** | 단기 중복 적재 위험 | 풀히스토리 재전송(ChatRequest.messages) + 체크포인터 thread_id=session_id + add_messages(ID 없음) | 같은 프로세스 동일 세션 재호출 시 메시지 누적·맥락 오염 |
| **M5** | 체크포인터 이원화 | Deep Agent(session_id) vs management(mgmt-{session_id}) | 단기 상태 두 네임스페이스 — §9와 연동 |
| **M6** | 요약·압축 부재 | recall은 원시 노트 5건 나열 | 회수해도 LLM 맥락 효율 낮음 |

### 10.5-4. 재설계 방향 (salience 기반)

```
WRITE (선택적 적재 — 매 턴 덤프 금지)
  적재 대상: ① 사용자 선호(목표·플랫폼·톤) ② 반복 관심 캠페인 ③ 확정 결정(승인된 제안)
  비대상: 단발 현황 질문("이번 달 예산?")
  키: (tenant,user)+정규화 사실 → upsert(멱등) — uuid4 랜덤키 폐기
  요약: N턴/세션경계마다 running summary 1건 갱신(원시 노트 누적 대신)

READ (배선 복구 + 예산 제한)
  chat.py: 오케스트레이터 호출 전 recall(tenant,user) → _format_memory → AskRequest.memory_context
  회수량: recency/salience 상위 K + 토큰 budget 상한
  anon: 비로그인은 장기기억 비활성(또는 session_id 임시 네임스페이스) — cross-user 누출 차단

단기(체크포인터)
  택1: (A) 풀히스토리 재전송 신뢰 → 체크포인터는 interrupt 재개 전용(history 이중적재 금지)
       (B) thread 상태 신뢰 → 재전송은 마지막 turn만
  현재 (A)+(B) 혼재가 M4의 원인 → 한쪽으로 통일
```

### 10.5-5. 메모리 적용 단계 (Plan 후속)

```
M-Phase 1  M1+M3  recall 배선 복구 + anon 격리(비로그인 장기기억 비활성)
M-Phase 2  M2     적재 게이트(salience 분류) + 멱등 upsert 키
M-Phase 3  M4+M5  단기 history 모델 통일(재전송 vs thread 택1) + 체크포인터 단일화(§9)
M-Phase 4  M6     running summary 압축(세션경계 요약 1건)
```

> **권장 착수 순서:** KB-RAG·카드(G1~G8)를 먼저 끝내고 메모리(M1~M6)는 그 다음. 단 **M1+M3(회수 배선+anon 격리)는 작고 효과 커서** G 작업과 병행 가능. M3는 **회수 배선 전 반드시** 처리(누출 방지).

---

## 10.7. Deep Agents 표준 정합성 — "빠진 것" 정직 점검 (2026-06-28)

> 사용자 우려: "딥에이전트 표준·유튜브를 봤을 때 이대로면 딥에이전트 채팅을 완벽히 구현한 게 맞나? 빠진 게 있을까?" → **공식 LangChain Deep Agents 정의(4대 구성요소)에 직접 대조**한 정직한 결과.

### 표준 — LangChain Deep Agents 4대 구성요소

[공식 정의](https://docs.langchain.com/oss/python/deepagents/overview) (Harrison Chase): 단순 tool-calling 루프와 deep agent를 가르는 4가지 —

| # | 표준 구성요소 | 역할 | 우리 현황 |
|---|---|---|---|
| ① | **계획 도구**(`write_todos`) | 50~100 도구콜 장기태스크에서 단계 분해·이탈 방지 | ❌ 없음 |
| ② | **가상 파일시스템**(ls/read/write/edit) | 컨텍스트 오프로드(긴 결과·노트를 토큰창 밖 디스크로) | ❌ 없음 |
| ③ | **서브에이전트**(격리 컨텍스트) | 서브태스크를 독립 컨텍스트창에 위임(토큰 격리) | ✅ 있음 |
| ④ | **상세 시스템 프롬프트**(Claude Code 스타일) | 개발자 의도 전달 — "prompt가 그 어느 때보다 중요" | ⚠️ 약함(10줄) |

### 정직한 판정

**우리 `deep_agent.py`는 엄밀히는 "Deep Agent"가 아니라 Supervisor(orchestrator-workers) 패턴이다.**

- ③ 서브에이전트 격리는 진짜로 있다 — management는 자체 ReAct 그래프(독립 컨텍스트·CRAG·HITL), generator도 별도. **이건 표준 부합.**
- ① 계획 도구·② 파일시스템은 **없다.** `MAX_ITER=3`(deep_agent.py:28)이라 50~100콜 장기태스크가 아니라 **의도적으로 얕은(shallow) 챗 루프**다.
- ④ 시스템 프롬프트는 10줄(deep_agent.py:30~39) — 표준이 강조하는 "예시 풍부한 상세 프롬프트"와 거리가 있다.

### 범위 결정 (빠진 게 실수인가, 의도인가)

| 표준 요소 | 우리 결정 | 근거 |
|---|---|---|
| ① 계획 도구 | **챗 MVP 비목표** | 우리 태스크 = "1개 도메인에 위임 + 구조화 답변". 단일/2스텝이라 todo 분해 불필요. 단 멀티스텝("생성하고 시뮬") 본격화 시 재검토 — 그땐 보은 PIPELINE_ORDER 가드레일(§plan-execute) 참고 |
| ② 가상 파일시스템 | **챗 MVP 비목표** | 결과는 `sub_results` dict + 롱텀 메모리(LTM)로 충분. 긴 문서 오프로드가 필요한 장기태스크가 아님 |
| ③ 서브에이전트 | **유지** | 이미 표준 부합 |
| ④ 상세 프롬프트 | **개선 대상 → G9** | 진짜 약점. 저비용 고효과 — 라우팅 정확도·환각에 직접 영향 |

> **결론:** 챗 어시스턴트(라우팅 + 카드 응답) 범위에선 **Supervisor 패턴이 정답**이고(도연 industry-standard ① 확인), 풀 deep-agent 기계장치(파일시스템·100콜)는 **과설계**다. ①②는 **문서화된 의도적 비목표**(실수 아님), ④만 실제 개선거리(G9). 즉 "이대로 진행해도 챗으론 표준 정합"이되, **딥에이전트라는 이름값(장기태스크)을 원하면 ①②가 추가로 필요**하다는 점을 명시한다.

### 추가로 표준이 권하나 우리가 이미/곧 갖춘 것

- **컨텍스트 요약**(긴 스레드 압축) → 메모리 M6(episodic 요약, 도연 session_summary)로 커버.
- **cross-session 영속 메모리** → LTM(§10.5) + 체크포인터(§9)로 커버.
- **astream_events 스트리밍** → P3 개선항목(도연도 표준 지목) — 우선순위↑.
- **LangSmith threads**(session_id=thread_id) → 이미 적용(deep_agent.py:271).

---

## 11. 설계 구멍 목록 (구현 갭 — 우선순위순)

| ID | 갭 | 근거(file:line) | 영향 | 수정 |
|---|---|---|---|---|
| **G1** | kb_ingest가 서브디렉토리 미탐색 | `kb_ingest.py:127` `glob("*.md")` | external/persona·도연 KB 적재 불가 | `rglob` + **적재 화이트리스트**(시뮬 파일 제외, §6) |
| **G2** | Deep Agent가 suggested_action 누락 | `deep_agent.py:300~316` `_state_to_result` | **RESULT/REVIEW/ACTIONBAR 카드 영영 안 뜸** | `combined_meta`에 `suggested_action` 캐리 |
| **G3** | SubagentResult↔AskResult 타입 불일치 | `composer.py:138` vs `chat.py:114` | compose_turn 호출 시 타입 에러 | `_sub_to_ask()` 어댑터 |
| **G4** | ADVISE가 KB 검색 전 None 반환 | `wiring.py:111~112` | 일반 질문 항상 CLIO(근거 없는 답) | KB 게이트 삽입(§5-3) |
| **G5** | 일반 광고 KB 0개 | DB 조회(§3) | G4 고쳐도 cosine 미달로 Miss | 도연 2파일 + marketing_basics 적재 |
| **G6** | chat.py가 카드 SSE 미배선 | `chat.py:127~170` raw token | 카드 UI 불가 | compose_turn/stream_turn 연결(§7-2) |
| **G7** | 체크포인터 중복 | `api/assistant/checkpointer.py` | 혼란·유지보수 | 삭제 + Deep Agent가 PG 싱글턴 주입(§9) |
| **G8** | 시뮬 지식 management KB 오염 | §4-3 | ADVISE/management 검색 정밀도↓ | 적재 화이트리스트(§6) |
| **G9** | 오케스트레이터 시스템 프롬프트 약함(10줄) | `deep_agent.py:30~39` | Deep Agents 표준 ④ 미달 — 라우팅 정확도·환각 영향 | 예시 풍부한 상세 프롬프트로 강화(§10.7) |

**의존 순서:** G1(+G8 화이트리스트) → G5 → G4 → G2 → G3 → G6 → (G7·G9 독립).
**G9는 환각 개선과 직결** — 라우팅·인용 규칙을 프롬프트에 명시하면 ADVISE 4지표에 반영되므로 환각 측정 루프와 함께 진행.

**메모리 갭(M1~M6)은 §10.5-3 별도 관리.** G 작업과 독립이나 **M3(anon 격리)는 M1(회수 배선)보다 먼저** — 누출 방지 선결.

---

## 12. 5가지 안전장치 (불변식)

```
환각 방지 ── 게이트(§5-3) cosine<0.35면 LLM 미호출 + 숫자는 live 도구만 인용(graph.py SYSTEM)
출처 추적 ── citations[] → EVIDENCE 카드(kind/trust/source_url) + [n] 마커 검증
도메인 경계 ─ management KB에 시뮬·제너 지식 금지(§6) + 타 도메인 직접 import 금지
HITL ────── 위험 Tier는 interrupt 정지 → 사람 승인 → Executor 단일경로(Tier 재검증)
비용·속도 ── 미리 임베딩 + 관련 청크만 LLM + MAX_ITER=3 + 근거없음 조기 단락
```

---

## 13. 적용 단계 (Plan 문서와 동기화)

```
Phase 0  G1+G8  kb_ingest rglob + 적재 화이트리스트(시뮬 파일 제외)
Phase 1  G5     도연 일반 KB 2개 + marketing_basics.md 적재
Phase 2  G4     ADVISE KB 게이트(cosine max + 인용검증) — wiring.py
Phase 3  G2+G3  suggested_action 캐리 + SubagentResult→AskResult 어댑터
Phase 4  G6     chat.py compose_turn/stream_turn 배선 + 프론트 카드 렌더러
Phase 5  G7     체크포인터 단일화(중복 삭제, PG 싱글턴 주입)
후속     —      simulator/generator 툴 연결(도연·태호·요한·윤섭)
```

검증 종료 조건:
- "ROAS가 뭐야" → `source=management`, EVIDENCE 카드 + 인용 (CLIO 아님)
- "오늘 날씨" → `source=clio` 폴백
- "이번 달 예산" → live 도구 응답(회귀 없음)
- 예산 증액 제안 → RESULT/REVIEW/ACTIONBAR 카드 렌더(G2 검증)
- management KB 검색에 페르소나·구매의향 청크 미혼입(G8 검증)
