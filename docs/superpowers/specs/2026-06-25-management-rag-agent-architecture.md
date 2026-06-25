# 매니지먼트 RAG 에이전트 — 현황과 구조 (2026-06-25)

- 날짜: 2026-06-25
- 상태: **구현 완료**(검증: 매니지먼트 451 passed / 4 skipped · eval 4종 게이트 통과 · 회귀 0). 분기 `feat/management-3k`에 15커밋.
- 영역: `backend/api/routers/chat.py`, `backend/api/assistant/*`(intent·orchestrator), `backend/domain/management/assistant/*`(agent·graph·retriever·web_search·memory_store·kb_ingest·source_refresh·history), `backend/domain/management/scheduler.py`·`notifications.py`, `backend/core/models.py`, Alembic `025`, 프론트 `app/(app)/chat/page.tsx`
- 목적: 오늘 합의·구현한 개념들로 **현재 RAG 에이전트가 어떻게 구성돼 있는지** 한눈에 이해.

---

## 0. 한 장 요약 — 요청 한 건의 흐름

```
사용자 질문
  │
  ▼  [1] 의도 분류 (LLM, OpenAI gpt-4o-mini)          ← 키워드 아님(폴백만)
  ├─ ADVISE(광고 무관) ─────────────────► Gemini CLIO (일반 채팅)
  └─ MANAGE(광고 운영 도메인)
        │
        ▼  [2] ReAct 에이전트 (LangGraph, OpenAI)
        │     도구를 스스로 골라 최대 5라운드
        ├─ live_* ............. 실측 숫자(Meta) — 환각 금지
        ├─ search_kb .......... 지식 검색 + [3]자기교정(CRAG)
        ├─ web_search ......... KB 부족 시 웹 폴백(advisory)
        └─ propose_action ..... 운영 변경 '제안' → [4]HITL
        │
        ▼  [5] 답변 + 근거(trust 라벨) + (제안 시) 승인 게이트
        │     장기기억 회수·적재 / 대화·도구·인용 관측 적재
        ▼
   프론트: trust 색상 배지 · 👍/👎 → [6]피드백 루프
```

핵심 원칙: **숫자는 실측 도구에서만, 해석·정책은 KB에서**(환각 방지). 운영 변경은 **제안만**, 실행은 사람 승인 경로.

---

## 1. 라우팅 — LLM 의도 분류 (키워드 → 의미)

**무엇** — 채팅이 들어오면 "이게 매니지먼트(광고 운영) 질문인가, 일반 질문인가"를 판정해 RAG로 보낼지 Gemini CLIO로 보낼지 결정한다.

**구조**
- `api/routers/chat.py` `_is_management(body)` → `api/assistant/intent.py` `classify_intent(req, [MANAGE], llm)`.
- **주 경로 = LLM 의미 분류**(`_get_classifier()` = OpenAI `gpt-4o-mini`). 광고 성과·정책·최적화·빈도·CTR/CPM·벤치마크·타깃·소재·플랫폼 질문이면 `MANAGE`, 광고와 무관하면 `ADVISE`.
- **폴백 = 키워드**(`intent.py` `_MANAGE_KW`). OpenAI 키 없거나 LLM 실패 시에만 결정론 분류(채팅 안 끊김, 테스트 재현).

**왜 이렇게** — 예전엔 `chat.py`에 키워드 38개를 나열했는데, 목록에 없는 질문("프리퀀시 높으면?")이 Gemini로 새어 RAG를 못 썼다(두더지잡기). LLM이 **의미로** 판단하므로 키워드가 없어도 광고 도메인이면 RAG로 온다. 키워드는 비상 폴백으로만 잔존.

> 검증: "프리퀀시 높으면?"·"광고 왜 반응 없을까?"(키워드 0개) → RAG, "김치찌개 레시피" → Gemini.

---

## 2. ReAct 에이전트 + 도구 세트

**무엇** — LangGraph `MessagesState` 기반 ReAct 루프. LLM이 스스로 도구를 골라 실측·지식을 모은 뒤 답한다(최대 5라운드).

**구조** (`domain/management/assistant/graph.py` `build_graph`)
- 노드: `agent`(도구 선택) → `tools`(실행) → 조건분기(도구호출 있으면 tools, 없으면 END).
- 읽기 도구 6종: `live_campaigns`·`live_budget`·`live_campaign_detail`·`live_before_after`(실측), `search_kb`(지식·자기교정), `web_search`(웹 폴백).
- 쓰기 의도: `propose_action`(제안만, §4).
- 진입점 `agent.py` `build_management_agent(settings)` — 키+실모드면 풀 그래프, 키 없거나 use_mock이면 **키워드 라우팅 폴백**(LLM·임베딩 없이 실측 요약, 데모 재현용).

**모델** — 전 구간 OpenAI: 분류 `gpt-4o-mini`, ReAct `gpt-4o-mini`, KB 임베딩 `text-embedding-3-small`, CRAG 평가 `gpt-4o-mini`. (Gemini는 §1의 일반 CLIO 채팅에만.)

---

## 3. 검색(R) — 하이브리드 + 신뢰도 라벨 + 자기교정(CRAG)

### 3.1 하이브리드 검색
`retriever.py` `KbRetriever` — pgvector 코사인(의미) + PostgreSQL GIN `tsvector`(정확 토큰) → **RRF**(Reciprocal Rank Fusion, k=60)로 융합. 임베딩 없는 `keyword_search`도 있어 키 없는 폴백/데모에서 동작.

### 3.2 신뢰도(trust) 라벨
모든 KB 청크는 부모 문서(`management_kb_documents`)의 trust를 달고 인용된다.
- **system_backed** — 코드 기준값 근거(CPM 앵커 ₩10,800·CTR 1.71% 등). **단정 가능.**
- **advisory** — 외부 참고(타 플랫폼 등). **"참고이며 직접 측정·관리는 Meta"** 단서 필수, 단정 금지.
- **reference** — 출처 있는 구성·통계(세그먼트). 인용하되 층별 효율 단정 금지.
- 라벨은 `kb_ingest._SOURCE_META` → `doc_metadata` JSONB에 적재, `retriever`가 chunk⨝document 조인으로 답변까지 전달(`Citation.trust/source_url/as_of`). 프론트는 색상 배지로 렌더(§7).

### 3.3 자기교정 검색 (CRAG-lite) — 오늘의 핵심
`graph.py` `search_kb`가 검색 후 **스스로 품질을 평가**한다:
1. top-k 검색 →
2. **`_grade_kb`(LLM)**: "이 근거가 질문에 충분한가?" 판정 →
3. 충분 → 그대로 답 / 부족 → **쿼리 재작성 + 재검색 1회**(병합·재평가) →
4. 여전히 부족 → **`_insufficient` 신호** → 에이전트가 `web_search`로 보강하거나 **정직히 모른다고**.
- 신호는 인용에서 필터(tools_node), 평가 실패는 통과(보수적·채팅 안 막음).
- **왜 에이전틱인가** — 이전엔 검색 결과를 무조건 믿고 답했다. 이제 에이전트가 자기 검색의 충분성을 추론해 능동 교정한다. 제품 thesis("신뢰할 의사결정 근거")와 직결.

> 검증: "빈도 높으면?"(KB 충분) → search_kb만. "사우디 라마단 단가?"(KB 없음) → search_kb→web_search 자기교정.

### 3.4 웹 폴백 (Tavily)
`web_search.py` — KB 부재·시의성 질문의 **advisory 폴백**. KB 우선, "최근·요즘·트렌드·새로 바뀐" 시의성 질문은 KB+웹 함께. 키(`TAVILY_API_KEY`) 없으면 graceful 빈 결과. 결과는 `trust=advisory`+출처 URL.

---

## 4. 행동(A) — 제안 → HITL 승인 → 실행

**무엇** — 어시스턴트는 운영 변경을 **제안만** 한다. 실제 write는 사람 승인을 거쳐 단일 실행 경로로만.

**구조**
- `propose_action`이 전 `ActionType`(PAUSE/ACTIVATE/INCREASE_BUDGET/DECREASE_BUDGET/REPLACE_CREATIVE/EXPAND_AUDIENCE/CHANGE_BID_STRATEGY/CREATE_CAMPAIGN) 커버. Tier는 정책 단일원천 `policy.TIER_POLICY`/`judge_tier`.
- Tier3(돈 늘어남) → `interrupt`로 그래프 멈춤(HITL, 체크포인터 필요).
- 채팅 실행 글루: `POST /api/chat/approve` → `finalize_proposal`→`approve`→`Executor.execute`. **모든 write는 Executor 단일경로**(멱등키·감사·Tier 재검증) 경유.

**안전 봉인** — `_resolved_execution_mode()`: `use_mock`이면 `MOCK`(Meta 미접촉), 아니면 `validate_only`/`live`. LIVE는 명시 opt-in일 때만. 어시스턴트는 writer/executor를 직접 부르지 않는다.

---

## 5. 기억 — 단기(thread) vs 장기(cross-session)

| 종류 | 범위 | 저장 | 영속 |
|---|---|---|---|
| **단기(STM)** | 한 대화 세션(thread) 멀티턴·HITL 재개 | LangGraph 체크포인터(`AsyncPostgresSaver`/Neon, Windows는 MemorySaver 폴백) | ✅ |
| **장기(LTM)** | **세션을 넘는** (tenant, user) 맥락·결정 | `memory_store.py` `ManagementMemory` | ✅ |

**장기기억 구조** (오늘 구현)
- 식별자: 채팅에 `optional_user`(JWT, 이미 구현) 부착 → 로그인 시 `(org, user)`, 비로그인은 `(global, anon)` 데모 네임스페이스.
- 흐름: 답변 전 `recall`로 회수 → LLM 맥락 주입(`AskRequest.memory_context`, 폴백 라우팅 불변), 턴 종료 시 `remember`로 적재.
- 영속: `build_memory_store`가 `use_mock`으로 분기 — 테스트/데모=InMemory(hermetic), 실행=**`SqlMemoryStore`(asyncpg → Neon `management_user_memory`)**. 마이그 `025`.
- **왜 asyncpg인가** — langgraph `AsyncPostgresStore`는 psycopg 기반이라 Windows(ProactorEventLoop) 비호환. 지금 ORM이 쓰는 asyncpg로 작은 테이블에 직접 붙여 **Windows에서도 영속**(검증: 한 인스턴스 적재→다른 인스턴스 회수).

---

## 6. 품질 루프 — 측정과 개선

### 6.1 eval 하니스 (`domain/management/evals/`)
- `retrieval_eval` — KB 검색 관련도(Hit@1=0.71·Hit@3=0.86). 리랭커/CRAG-검색 필요성 판정용.
- `assistant_eval` — 도구선택 정확도(1.0)·faithfulness(1.0, 수치 근거성 LLM-judge).
- `diagnosis_eval`·`regeneration_eval` — 진단·재생성(타 영역, 참고).

### 6.2 피드백 루프 (오늘 닫음)
- 적재: 프론트 👍/👎 → `POST /api/chat/feedback` → `management_kb_feedback`.
- **소비(신규)**: `history.summarize_feedback` / `GET /api/chat/feedback/summary` — 좋아요율·**실패유형 분해**(wrong_tool/stale_doc/hallucinated_number/missing_citation)·최근 👎 리뷰 큐. "어디서 실패하는가"를 수치로 → 개선 우선순위.
- **루프**: 사용자 피드백 → 집계·가시화 → 사람이 KB·프롬프트 개선 → 품질↑.

---

## 7. 프론트 — 신뢰도 배지
`app/(app)/chat/page.tsx` — 근거를 색상 칩으로: **기준**(emerald=system_backed)·**참고**(amber=advisory, as_of+출처링크)·**구성**(gray=reference). 도구는 실측/KB/웹 칩. 백엔드가 SSE meta로 보내던 trust를 시각화.

---

## 8. 능동 관제 — 스케줄러 + 알림
- `scheduler.py` — **APScheduler 인프로세스**(무SQS, 단일 EC2). 기본 off(`management_scheduler_enabled`), 운영에서만 기동. `api/main.py` lifespan에 게이트 연결.
- 기본 스캐너: 활성 캠페인 게재 점검(노출 0=미게재) → `notifications.py` `NotificationSink`(기본 로그 sink) 통지.
- 심화 진단(ROAS 목표·시계열)·SES/웹훅 알림은 seam.

---

## 9. "에이전틱 RAG"로서의 현 위치

| 요소 | 상태 |
|---|---|
| 도구 사용·다단계 추론(ReAct) | ✅ |
| 검색 여부 능동 판단 | ✅ |
| **검색 품질 자기교정(CRAG)** | ✅ (오늘) |
| 행동(answer 넘어 실행·HITL) | ✅ |
| 단기+장기 기억(영속) | ✅ (오늘 LTM 영속) |
| 근거·신뢰도(trust)·환각 방지 | ✅ |
| 측정·피드백 루프 | ✅ (오늘 피드백 소비) |

→ 단순 retrieve-generate가 아니라, **에이전트가 라우팅·검색품질·행동·기억·품질을 능동 관리**하는 구조.

---

## 10. 정직한 seam (보류된 선행조건)
- **장기기억 식별자** — auth는 구현됐고 채팅에 `optional_user` 연결도 됨. 유저별 기억은 로그인 시 동작, 비로그인은 데모 네임스페이스.
- **피드백 심화** — `corrected_answer`→KB 자동승격(프론트가 수정답안 미수집), 👎↔인용 청크 귀속(`agent_runs` 조인)은 데이터 누적 후.
- **스케줄러 진단** — 현재 게재점검만. campaign-queryable 진단 정비 후 ROAS·시계열 확장. SES/웹훅 알림.
- **마이그레이션 제로빌드** — `personas`·`simulation_aggregates`(SimBase, create_all 소유)를 core 마이그 004가 ALTER → 빈 DB 0부터 빌드 시 크래시. 기존 DB는 무관, 신규 환경만 영향. 시뮬팀 조율 사안(미수정).
- **장기기억 운영 영속** — Windows dev는 SqlMemoryStore로 동작. Linux/운영도 동일(asyncpg).

---

## 11. 환경 변수 (이 기능들 관련)
- `OPENAI_API_KEY` — 분류·RAG·임베딩·CRAG(필수, 풀모드).
- `TAVILY_API_KEY` — web_search(없으면 graceful 비활성).
- `GEMINI_API_KEY` — 일반 CLIO 채팅.
- `MANAGEMENT_ASSISTANT_MODEL` — 분류·RAG 모델(기본 `gpt-4o-mini`).
- `USE_MOCK` — true면 InMemory 기억·MOCK 실행(hermetic), false면 영속·실행 봉인 모드.
- `MANAGEMENT_EXECUTION_MODE` — `dry_run`|`validate_only`|`live`(실행 안전선).
- `MANAGEMENT_SCHEDULER_ENABLED` — 능동 스케줄러(기본 false).
