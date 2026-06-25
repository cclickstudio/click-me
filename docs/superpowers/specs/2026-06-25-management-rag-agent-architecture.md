# 매니지먼트 RAG 에이전트 — 설계·구현·품질 개선 (포트폴리오)

- 날짜: 2026-06-21 설계 → 2026-06-24 eval → 2026-06-25 완성
- 상태: **구현 완료** (검증: 매니지먼트 451 passed / 4 skipped · eval 4종 게이트 통과 · 회귀 0). 분기 `feat/management-3k` 15커밋.
- 영역: `backend/api/routers/chat.py`, `backend/api/assistant/*`(intent·orchestrator), `backend/domain/management/assistant/*`(agent·graph·retriever·web_search·memory_store·kb_ingest·source_refresh·history), `backend/domain/management/scheduler.py`·`notifications.py`, `backend/domain/management/evals/*`, `backend/core/models.py`, Alembic `019`·`020`·`025`, 프론트 `app/(app)/chat/page.tsx`

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

핵심 원칙: **숫자는 실측 도구에서만, 해석·정책은 KB에서** (환각 방지). 운영 변경은 **제안만**, 실행은 사람 승인 경로.

---

## 1. 배경과 문제

매니지먼트 챗봇은 LangGraph ReAct + HITL 기반 에이전틱 RAG로, **숫자는 실측 도구(live_*), 해석·정책은 KB**에서 가져온다. 골격은 있었으나 운영급으로 가기엔 4가지 갭이 있었다.

- **검색 품질 미측정** — 벡터 단독 검색이 ROAS·PENDING_REVIEW 같은 정확 토큰을 놓치는지 알 수 없었다.
- **상태 비영속** — 체크포인터가 인메모리(MemorySaver)라 재시작 시 HITL 승인 대기·대화 맥락이 소실. 멀티턴도 매 요청 새 thread.
- **관측 부재** — 대화·도구·인용·피드백이 어디에도 안 쌓여 품질 회귀를 잴 수 없었다.
- **품질이 "감"** — "리랭커·CRAG를 넣어야 하나"를 수치 없이 판단하고 있었다.

**목표**: 검색·답변 품질을 수치로 측정하고, 개선을 before/after로 입증한다. "무엇을 넣을지"를 데이터로 결정한다(감 금지).

---

## 2. 핵심 설계 원칙

| 결정 | 선택 | 이유 |
|---|---|---|
| KB 검색 | **하이브리드(벡터+GIN 키워드, RRF 융합)** | 벡터가 놓치는 정확 토큰을 키워드가 보강. 점수 정규화 불필요. |
| 체크포인터 | **AsyncPostgresSaver(Neon)**, Windows는 MemorySaver 폴백 | 운영(Linux) 영속, 로컬(psycopg-async 비호환)은 즉시 폴백. |
| 메모리 저장소 | **STM=체크포인터 / LTM=전용 테이블(asyncpg)** | LangGraph PostgresStore는 psycopg라 Windows 폴백 → `history.py`와 동일 asyncpg로 일관·이식성. |
| 평가 judge | **Gemini Flash(환각 중심 채점)** | 측정대상(에이전트=OpenAI)과 분리. 저비용. "KB에 다 있어야"가 아니라 "환각·거짓·지어낸 수치"만 감점. |
| 측정 정밀도 | **eval 27케이스 + judge×3 평균 + 증분 JSONL 적재** | 단일 judge·소표본 노이즈 제거. 중단돼도 부분 결과 보존. |
| 리랭커/풀CRAG | **도입 보류(데이터 근거)** | 검색 recall@3=0.93 → 고칠 노이즈가 없음. 코퍼스 확대 시 재검토. |

**운영 원칙**:
- **숫자는 실측, 판단은 지식** — CTR·소진·ROAS는 항상 실시간 툴(Meta 실측). 원인·방법·정책은 KB에서 근거 인용.
- **스케일 환산 금지** — 예측(상대 지표 0~1)과 실측(절대 지표 CTR·ROAS)은 수치 환산 없이 방향성만 비교.
- **읽기 + 행동 제안** — 조회·분석에 더해 행동 의도는 추천 액션으로 **제안만**. 실행은 승인→실행기 경로로.
- **무키 폴백** — LLM·임베딩 키 없거나 mock 모드면, 키워드 라우팅 + 실시간 툴 요약으로 동작(재현성 게이트 유지).

---

## 3. 구현 상세

### 3.1 라우팅 — LLM 의도 분류

**구조**
- `api/routers/chat.py` `_is_management(body)` → `api/assistant/intent.py` `classify_intent(req, [MANAGE], llm)`.
- **주 경로 = LLM 의미 분류**(`_get_classifier()` = OpenAI `gpt-4o-mini`). 광고 성과·정책·최적화·빈도·CTR/CPM·벤치마크·타깃·소재·플랫폼 질문이면 `MANAGE`, 광고와 무관하면 `ADVISE`.
- **폴백 = 키워드**(`intent.py` `_MANAGE_KW`). OpenAI 키 없거나 LLM 실패 시에만 결정론 분류(채팅 안 끊김, 테스트 재현).

**왜 이렇게** — 예전엔 `chat.py`에 키워드 38개를 나열했는데, 목록에 없는 질문("프리퀀시 높으면?")이 Gemini로 새어 RAG를 못 썼다(두더지잡기). LLM이 **의미로** 판단하므로 키워드가 없어도 광고 도메인이면 RAG로 온다.

> 검증: "프리퀀시 높으면?"·"광고 왜 반응 없을까?"(키워드 0개) → RAG, "김치찌개 레시피" → Gemini.

### 3.2 ReAct 에이전트 + 도구 세트

**구조** (`domain/management/assistant/graph.py` `build_graph`)
- 노드: `agent`(도구 선택) → `tools`(실행) → 조건분기(도구호출 있으면 tools, 없으면 END).
- 읽기 도구 6종: `live_campaigns`·`live_budget`·`live_campaign_detail`·`live_before_after`(실측), `search_kb`(지식·자기교정), `web_search`(웹 폴백).
- 쓰기 의도: `propose_action`(제안만, §3.4).
- 진입점 `agent.py` `build_management_agent(settings)` — 키+실모드면 풀 그래프, 키 없거나 use_mock이면 **키워드 라우팅 폴백**.

**모델** — 전 구간 OpenAI: 분류 `gpt-4o-mini`, ReAct `gpt-4o-mini`, KB 임베딩 `text-embedding-3-small`, CRAG 평가 `gpt-4o-mini`. (Gemini는 일반 CLIO 채팅에만.)

### 3.3 검색 — 하이브리드 + 신뢰도 라벨 + 자기교정(CRAG)

**하이브리드 검색**
`retriever.py` `KbRetriever` — pgvector 코사인(의미) + PostgreSQL GIN `tsvector`(정확 토큰) → **RRF**(Reciprocal Rank Fusion, k=60)로 융합. 임베딩 없는 `keyword_search`도 있어 키 없는 폴백/데모에서 동작.

**신뢰도(trust) 라벨**
모든 KB 청크는 부모 문서(`management_kb_documents`)의 trust를 달고 인용된다.
- **system_backed** — 코드 기준값 근거(CPM 앵커 ₩10,800·CTR 1.71% 등). **단정 가능.**
- **advisory** — 외부 참고(타 플랫폼 등). **"참고이며 직접 측정·관리는 Meta"** 단서 필수, 단정 금지.
- **reference** — 출처 있는 구성·통계(세그먼트). 인용하되 층별 효율 단정 금지.
- 라벨은 `kb_ingest._SOURCE_META` → `doc_metadata` JSONB에 적재, `retriever`가 chunk⨝document 조인으로 답변까지 전달(`Citation.trust/source_url/as_of`).

**자기교정 검색 (CRAG-lite)**
`graph.py` `search_kb`가 검색 후 **스스로 품질을 평가**한다:
1. top-k 검색 →
2. **`_grade_kb`(LLM)**: "이 근거가 질문에 충분한가?" 판정 →
3. 충분 → 그대로 답 / 부족 → **쿼리 재작성 + 재검색 1회**(병합·재평가) →
4. 여전히 부족 → **`_insufficient` 신호** → 에이전트가 `web_search`로 보강하거나 정직히 모른다고.

**왜 에이전틱인가** — 이전엔 검색 결과를 무조건 믿고 답했다. 이제 에이전트가 자기 검색의 충분성을 추론해 능동 교정한다.

**웹 폴백 (Tavily)**
`web_search.py` — KB 부재·시의성 질문의 advisory 폴백. 키(`TAVILY_API_KEY`) 없으면 graceful 빈 결과. 결과는 `trust=advisory`+출처 URL.

Tavily가 호출되는 조건은 두 가지다.

- **① 시의성 키워드** — 시스템 프롬프트가 "최근·요즘·올해·이번 달·새로 바뀐·트렌드·발표" 키워드를 감지하면 `search_kb`와 `web_search`를 함께 호출한다.
  - `"요즘 Meta 광고 CPM 트렌드 어때?"`
  - `"최근 Meta 정책 바뀐 거 있어?"`
- **② KB 근거 부족 (CRAG-lite `_insufficient` 신호)** — `search_kb`가 재검색 후에도 충분한 근거를 못 찾으면 에이전트에게 `web_search`로 보강하라는 신호를 남긴다.
  - `"사우디 라마단 시즌 CPM 단가는?"`
  - `"유튜브 쇼츠 광고 완료율 평균이 어떻게 돼?"`

> 검증: "빈도 높으면?"(KB 충분) → search_kb만. "사우디 라마단 단가?"(KB 없음) → search_kb→web_search 자기교정.

### 3.4 행동 — 제안 → HITL 승인 → 실행

**구조**
- `propose_action`이 전 `ActionType`(PAUSE/ACTIVATE/INCREASE_BUDGET/DECREASE_BUDGET/REPLACE_CREATIVE/EXPAND_AUDIENCE/CHANGE_BID_STRATEGY/CREATE_CAMPAIGN) 커버. Tier는 정책 단일원천 `policy.TIER_POLICY`/`judge_tier`.
- Tier3(돈 늘어남) → `interrupt`로 그래프 멈춤(HITL, 체크포인터 필요).
- 채팅 실행 글루: `POST /api/chat/approve` → `finalize_proposal`→`approve`→`Executor.execute`. **모든 write는 Executor 단일경로**(멱등키·감사·Tier 재검증) 경유.

**안전 봉인** — `_resolved_execution_mode()`: `use_mock`이면 `MOCK`(Meta 미접촉), 아니면 `validate_only`/`live`. LIVE는 명시 opt-in일 때만. 어시스턴트는 writer/executor를 직접 부르지 않는다.

### 3.5 기억 — 단기(thread) vs 장기(cross-session)

| 종류 | 범위 | 저장 | 영속 |
|---|---|---|---|
| **단기(STM)** | 한 대화 세션(thread) 멀티턴·HITL 재개 | LangGraph 체크포인터(`AsyncPostgresSaver`/Neon, Windows는 MemorySaver 폴백) | ✅ |
| **장기(LTM)** | **세션을 넘는** (tenant, user) 맥락·결정 | `memory_store.py` `ManagementMemory` | ✅ |

**장기기억 구조**
- 식별자: 채팅에 `optional_user`(JWT) 부착 → 로그인 시 `(org, user)`, 비로그인은 `(global, anon)` 데모 네임스페이스.
- 흐름: 답변 전 `recall`로 회수 → LLM 맥락 주입, 턴 종료 시 `remember`로 적재.
- 영속: `build_memory_store`가 `use_mock`으로 분기 — 테스트/데모=InMemory(hermetic), 실행=**`SqlMemoryStore`(asyncpg → Neon `management_user_memory`)**. 마이그 `025`.

**원칙**: 숫자는 LTM에 넣지 않는다(실측은 항상 live tool). 정책·선호·결정만. 인용 시 `[기억]`/`[출처문서]` 구분.

**왜 asyncpg인가** — LangGraph `AsyncPostgresStore`는 psycopg 기반이라 Windows(ProactorEventLoop) 비호환. 지금 ORM이 쓰는 asyncpg로 직접 붙여 **Windows에서도 영속**.

### 3.6 관측·피드백 루프

**관측 인프라** (`history.py`)
`record_turn`(세션·메시지·도구·인용·지연) + `record_feedback`(👍/👎·실패유형) best-effort 적재.

**피드백 소비**
- 적재: 프론트 👍/👎 → `POST /api/chat/feedback` → `management_kb_feedback`.
- 소비: `history.summarize_feedback` / `GET /api/chat/feedback/summary` — 좋아요율·**실패유형 분해**(wrong_tool/stale_doc/hallucinated_number/missing_citation)·최근 👎 리뷰 큐.
- **루프**: 사용자 피드백 → 집계·가시화 → 사람이 KB·프롬프트 개선 → 품질↑.

**지식베이스 스키마** (Alembic 019)
- `management_kb_documents`(테넌트·버전·출처·provenance) ← `management_kb_chunks`(임베딩 + `search_vector` GENERATED tsvector + GIN 인덱스).
- `management_chat_sessions`·`chat_messages`·`agent_runs`·`kb_feedback`·`kb_eval_cases`.

**증분 적재** (`kb_ingest.py`)
`content_hash` 변경감지 — 변경된 문서만 재임베딩. 운영자 트리거 `POST /management/kb/refresh`.

### 3.7 프론트 — 신뢰도 배지

`app/(app)/chat/page.tsx` — 근거를 색상 칩으로: **기준**(emerald=system_backed)·**참고**(amber=advisory, as_of+출처링크)·**구성**(gray=reference). 도구는 실측/KB/웹 칩. 백엔드가 SSE meta로 보내는 trust를 시각화.

### 3.8 능동 관제 — 스케줄러

`scheduler.py` — **APScheduler 인프로세스**(무SQS, 단일 EC2). 기본 off(`management_scheduler_enabled`), 운영에서만 기동. `api/main.py` lifespan에 게이트 연결.
기본 스캐너: 활성 캠페인 게재 점검(노출 0=미게재) → `notifications.py` `NotificationSink`(기본 로그 sink) 통지.
심화 진단(ROAS 목표·시계열)·SES/웹훅 알림은 seam.

---

## 4. eval 기반 품질 개선 (포트폴리오 핵심)

> **핵심 성과 — 답변 충실도(faithfulness) 0.615 → 0.852 (+23.7%p).** 동일 judge·동일 측정으로 잰 before/after.

측정 대상=OpenAI gpt-4o-mini 에이전트, judge=Gemini Flash. **measure → try → revert → fix → re-measure** 루프.

### 4.1 측정 기준 — Faithfulness

"답이 그럴듯한가"가 아니라 **"환각 없이 근거에 충실한가"** 를 잰다.

- **감점**: 근거와 모순되는 내용, 사실 오류, **근거에 없는데 지어낸 구체 수치**(지출·CTR·ROAS 등). 숫자는 근거(실측)에 있을 때만 인정.
- **감점 아님**: KB에 명시 안 됐어도 **사실이고 합리적인 일반 광고 지식**(거짓이 아니면 OK).
- **집계**: judge(Gemini Flash) **×3 반복** — `faithful`은 과반(2/3) 투표, `score`는 평균. n=27, 잔여 judge 표준편차 0.24(측정 안정).

### 4.2 검색 베이스라인 → 리랭커 기각

| 셋 | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| n=13(쉬움) | 0.92 | 1.00 | 0.96 |
| **n=28(패러프레이즈 포함)** | 0.78 | **0.93** | 0.85 |

recall@3=0.93 → **리랭커가 고칠 노이즈가 없음**을 수치로 확인하고 도입 보류.

### 4.3 Faithfulness — 무엇을 고칠지 데이터로 특정

1. **베이스라인(엄격 judge)**: 0.538. 실패 사유 분석: ① judge 과엄격(맞는 일반조언도 감점) ② 행동버그(개념질문에 live 덤프, KB 미사용).
2. **Grounding 게이트 시도** → 3회 측정 모두 0.538, **개선 0 → revert**(지연만 추가하는 음성 결과).
3. **judge 재보정**(환각 중심) + **프롬프트 라우팅 수정**(개념질문→search_kb, live 덤프 금지).
4. **클린 before/after**(동일 judge): **0.615 → 0.852**.

| 단계 | faithful_rate | 판정 |
|---|---|---|
| 베이스라인(엄격 judge) | 0.538 | — |
| 라우팅 수정 후(n=13) | 0.846 | 큰 개선 |
| **정밀 측정(n=27·judge×3)** | **0.852** (평균 4.54/5, 잔여 std 0.24) | **개선 실재 확정** |

### 4.4 약점 추격 = 프롬프트 천장 입증

남은 약점 4건(빈도·CPM·예산소진·증상별, 전부 playbook 수치/조치 혼합)을 "인과·조치 근거 한정" 규칙으로 추격 → **빈도는 2.0→5.0 개선했으나 거절·구매의도가 5.0→회귀**. 순손해라 **revert**. **프롬프트 튜닝의 천장**(약점↔정상 트레이드오프)을 2라운드 측정으로 확정.

---

## 5. 에이전틱 RAG로서의 현 위치

| 요소 | 상태 |
|---|---|
| 도구 사용·다단계 추론(ReAct) | ✅ |
| 검색 여부 능동 판단 | ✅ |
| **검색 품질 자기교정(CRAG)** | ✅ |
| 행동(answer 넘어 실행·HITL) | ✅ |
| 단기+장기 기억(영속) | ✅ |
| 근거·신뢰도(trust)·환각 방지 | ✅ |
| 측정·피드백 루프 | ✅ |

검색 recall@3 **0.93**(n=28) · faithfulness **0.852**(n=27·judge×3, 잔여 std 0.24) · 매니지먼트 테스트 **451 passed** · Alembic head=`025`(Neon 적용·정합).

---

## 6. 엔지니어링 교훈 (포트폴리오 포인트)

1. **감 대신 측정** — 리랭커·CRAG·grounding 게이트를 모두 "넣기 전에 측정"해 **2개를 데이터로 기각**(과투자 방지).
2. **음성 결과도 결과** — grounding 게이트가 무효임을 측정으로 확인하고 되돌림(복잡도·지연 제거).
3. **측정 정밀도가 먼저** — 소표본·단일 judge 노이즈에 속지 않게 n 확대 + judge 평균 + 증분 적재로 신뢰구간 확보.
4. **천장 인지** — 같은 레버(프롬프트)로 트레이드오프가 반복되면 멈추고 레버를 바꾼다(KB/모델).

---

## 7. 한계 / seam (보류된 선행조건)

- **더 올리려면** — ① KB 보강(약점은 KB 갭: CPM 원인·예산페이스 조치) ② 상위 모델(gpt-4o-mini 파라메트릭 누수).
- **피드백 심화** — `corrected_answer`→KB 자동승격(프론트가 수정답안 미수집), 👎↔인용 청크 귀속(`agent_runs` 조인)은 데이터 누적 후.
- **스케줄러 진단** — 현재 게재점검만. campaign-queryable 진단 정비 후 ROAS·시계열 확장. SES/웹훅 알림.
- **RLS** — 정책만 준비(전용 롤·멀티테넌트 인증 전제).
- **마이그레이션 제로빌드** — `personas`·`simulation_aggregates`(SimBase, create_all 소유)를 core 마이그 004가 ALTER → 빈 DB 0부터 빌드 시 크래시. 기존 DB는 무관, 신규 환경만 영향. 시뮬팀 조율 사안(미수정).
- **자동수집 풀파이프라인** — 증분 엔진까지만(웹 fetch·스케줄러는 소스 결정 후).

---

## 8. 환경 변수

- `OPENAI_API_KEY` — 분류·RAG·임베딩·CRAG(필수, 풀모드).
- `TAVILY_API_KEY` — web_search(없으면 graceful 비활성).
- `GEMINI_API_KEY` — 일반 CLIO 채팅.
- `MANAGEMENT_ASSISTANT_MODEL` — 분류·RAG 모델(기본 `gpt-4o-mini`).
- `USE_MOCK` — true면 InMemory 기억·MOCK 실행(hermetic), false면 영속·실행 봉인 모드.
- `MANAGEMENT_EXECUTION_MODE` — `dry_run`|`validate_only`|`live`(실행 안전선).
- `MANAGEMENT_SCHEDULER_ENABLED` — 능동 스케줄러(기본 false).
