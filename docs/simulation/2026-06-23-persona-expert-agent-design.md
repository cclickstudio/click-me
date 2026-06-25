# 페르소나 전문 tool 세트 설계안 (시뮬 서브에이전트 내)

> 작성일 2026-06-23 · 담당 yeotaeho(페르소나 생성)
> 채팅 오케스트레이터(스타 토폴로지) 안에서 시뮬 서브에이전트가 부를 **페르소나 전문 tool**을 정의한다.
> 레퍼런스: `backend/domain/management/assistant/`(에이전틱 RAG, ReAct) — 이 구조를 미러링한다.

---

## 합의된 전제 (선결정)

- 채팅은 **스타 토폴로지**: 공통 오케스트레이터가 프롬프트를 해석 → 도메인(생성/관리/시뮬) 서브에이전트 호출.
- 시뮬 도메인은 소유자 2명: **나=페르소나 생성, 동료=분석·토론**. 서로 로직 안 건드림.
- 시뮬 서브에이전트는 **하나** → **단일 에이전트 + tool 분담** 방식으로 나눈다(management처럼 LLM이 tool 자율 선택).
- 에이전트는 **답변만이 아니라 직접 실행도 한다** — 사용자가 "시뮬 돌려줘"/"토론 돌려줘"면 파라미터 수집 후 **실행(트리거)** 까지. tool 계층이 둘로 나뉜다:
  - **read tool**(조회·설명) — 페르소나 read는 read-only(조회 + 방법론 설명).
  - **execution tool**(실행·트리거) — `run_simulation`·`run_debate`. 비동기 잡 + SSE 핸드오프, 비용 발생 → 확인 게이트.
- 페르소나 데이터는 DB에 실제 적재됨 — `save_completed_run`이 완료 런을 `panels`·`personas`에 저장(단, `DATABASE_URL` 설정 + 런 완료 시).

---

## A. 전체 구조 (어디에 끼는가)

```
[공통] 오케스트레이터  ── route ──▶  시뮬 서브에이전트 (껍데기 = 동료와 1회 공동 합의)
                                       │  Tool-calling ReAct (management graph.py 미러)
                                       │  LLM이 tool 자율 선택
                                       ├─ read tool ─┬─ 페르소나 read ◀── 내 소유
                                       │             └─ 분석/토론 read ◀── 동료 소유
                                       └─ execution tool ─┬─ run_simulation ◀── 공유(껍데기)
                                                          └─ run_debate     ◀── 공유(껍데기)
```

- 시뮬 에이전트 **껍데기**(진입점 `build_simulation_agent(settings)` → `ask(req) -> AskResult`, ReAct 그래프, I/O 계약, execution tool)는 management의 `agent.py`/`graph.py`/`contracts.py`를 복제해 **동료와 1회 합의 후 단독 PR**. 이후 read tool은 각자 append.
- **read tool**(페르소나·분석/토론)은 read-only — 저위험·완전 추적.
- **execution tool**(`run_simulation`·`run_debate`)은 기존 서비스(`SimulationService`/`DebateService`)를 호출만 한다. 비용·비동기 잡이라 **확인 게이트(HITL)** 후 트리거(§C).

## B. 내 deliverable — tool 4종 + KB

### ① DB read tool (숫자는 여기서만, `personas`/`panels` 테이블)

| tool | 입력 | 반환 | 읽는 곳 |
|---|---|---|---|
| `panel_composition` | `panel_version` 또는 `simulation_id` | 연령·성별·지역·OCEAN **분포**, 표본수, grounding_meta | `panels`+`personas` |
| `persona_filter` | 속성 필터(연령대·성별·지역·OCEAN밴드) | 해당 수 + 대표 프로필 N건 | `personas` |
| `grounding_sources` | (없음) | 속성별 근거 데이터셋·상태(`data_status()`) | `grounding_meta`/로더 |

### ② KB/RAG tool (방법론·"왜/어떻게", pgvector)

| tool | 반환 |
|---|---|
| `search_persona_kb(query)` | `sources.md`·`Data_Collection.md`·페르소나 생성 전략·reachability 문서 청크 + 출처 |

- management의 `KbRetriever`(pgvector 코사인, `text-embedding-3-small` 1536) 그대로, 테이블만 `simulation_kb_chunks` 신설.
- `kb_ingest.py`로 페르소나 문서 청킹·임베딩.

## B-EX. 실행(트리거) tool — 답변을 넘어 직접 실행 (공유 껍데기)

사용자가 "시뮬 돌려줘"/"토론 돌려줘"면 read가 아니라 **잡을 띄운다**. 기존 서비스를 호출만 하고(비파괴), 진행률은 기존 SSE 스트림 재사용(스펙 §F1).

| tool | 호출 대상 | 입력(슬롯) | 반환(핸드오프 이벤트) | 비고 |
|---|---|---|---|---|
| `run_simulation` | `SimulationService.start(SimulationRunRequest)` | ad_id·project_id·타깃·표본수 | `{event:"simulation_started", run_id, stream_url, domain:"simulation"}` | 패널 빌드+반응+집계 전체 파이프라인 |
| `run_debate` | `DebateService.start(reactions, ad_analysis, personas, …)` | simulation_id(필수)·lay_count·topic | `{event:"debate_started", run_id, stream_url, domain:"debate"}` | **선행 시뮬 결과 의존** — reactions를 DB(`get_saved_report`)나 직전 런에서 로드 |

**실행 패턴 (슬롯형 + 확인 게이트)**
1. 에이전트가 필요한 슬롯을 채운다(부족하면 되묻기 — `action:"ask"`).
2. 슬롯 충족 시 **확인 게이트(HITL interrupt)** — "표본 300으로 시뮬 실행할까요?"(비용 고지). management `propose_action`의 interrupt 패턴 미러.
3. 사용자 승인 → 서비스 `start()` 호출 → `started_event` 반환(`action:"trigger"`). 프론트가 `stream_url` 구독.

> **`run_debate` 의존성 처리** — 토론은 시뮬 reactions가 있어야 한다. 슬롯에 `simulation_id`가 오면 저장된 반응을 로드(`DebateService.get_saved_report`/persistence), 없으면 "먼저 시뮬을 실행하거나 simulation_id를 지정하라"고 되묻는다.

## B-DBG. 토론·분석 tool 정의 (동료 소유 — 합의용 제안)

> 내 코딩 범위 아님. 단일 에이전트 tool 레지스트리를 완성하기 위해 **정의만** 한다(스펙 §B 계약·§E1 코퍼스 분담 합의 대상). 동료가 자기 도메인(`service/debate_service.py`·`service/analysis_view.py`·`tools/debate/*`·`tools/objective_fit.py`)을 래핑.

**read tool (조회)**
| tool | 호출 대상 | 반환 |
|---|---|---|
| `get_analysis_summary` | `analysis_view`(+`compute_kpi`·`assess_objective_fit`) | KPI 분해(퍼널·구매의도·거부·감정)·alignment·목표 적합도 |
| `get_debate_result` | `DebateService.get_saved(debate_id)` | 토론 다이제스트(논제·발언 요약·판정) |
| `list_topics` | `tools/debate/kpi.build_topic_candidates` | 추가 토론용 논제 후보 |

**KB tool (방법론·"왜/어떻게")**
| tool | 반환 |
|---|---|
| `search_analysis_kb(query)` | KOBACO 베이스라인·AISAS·리포트 템플릿·진단 기준 문서 청크 + 출처 |

> KB 테이블은 `simulation_kb_chunks` **공용**으로 두고 `source` 메타로 페르소나/분석 코퍼스를 구분하는 방식 권장(테이블 1개·Alembic 1회). 분담은 §E1.

## C. 핵심 가드레일 (우리 도메인 특유)

management 시스템 프롬프트의 *"숫자는 live tool, 추정·환각 금지"*에 **우리 KPI 규칙을 추가**한다.

- 분포를 **평균 한 숫자로 단정 금지** — `panel_composition`은 분포(밴드별 비율)를 통째로 반환, LLM은 그대로 전달.
- **"예측 CTR" 등 실측 스케일 환산 금지** 문구를 시스템 프롬프트에 명시.
- grounding 출처 없으면 "모른다"고 답한다.
- **실행 tool은 확인 없이 자동 트리거 금지** — `run_simulation`/`run_debate`는 비용 발생 잡이므로 슬롯 충족 후 **사용자 확인(HITL)** 을 거친 뒤에만 `start()` 호출. read tool은 자율, execution tool만 게이트.

## D. 경계·추적 (조율 필요한 공통부)

- **pgvector KB 테이블**(`simulation_kb_chunks`, `core/models.py`) = 공통부 → 사전공지 + Alembic 단독 PR (스펙 E3).
- **추적**(스펙 D1) — raw `google.generativeai` 직접 호출 금지. 에이전트 LLM은 management처럼 계측 LLM(`ChatOpenAI`)이 가장 안전하나, **공통 오케스트레이터의 LLM 선택(팀 결정)에 종속** → 일단 미정 항목. `run_name="simulation.persona_agent"`, 메타에 `session_id` 주입.
- **오케스트레이터 본체·시뮬 껍데기 합의**는 내 단독 범위 밖 — 팀/동료 조율.

---

## 실제 내 코딩 범위 vs 조율 대상

| 구분 | 항목 | 비고 |
|---|---|---|
| **내 단독 코딩** | B-①·② 페르소나 read tool, C 가드레일(시스템 프롬프트), `kb_ingest.py`(페르소나 코퍼스) | `domain/simulation/` 내부 |
| **공유(동료와 1회 합의)** | 시뮬 에이전트 껍데기, B-EX 실행 tool(`run_simulation`·`run_debate`)·확인 게이트 | 시뮬 런·토론 둘 다 거는 진입점이라 공동 |
| **동료 소유(정의만)** | B-DBG 토론·분석 read/KB tool | 합의용 제안, 코딩은 동료 |
| **조율(공통부)** | D — `simulation_kb_chunks` 모델·Alembic, 오케스트레이터 LLM/추적 규칙 | 사전공지·단독 PR·팀 합의 |

## 미해결 / 확인 필요

1. **KB 범위** — `simulation_kb_chunks`를 페르소나 전용으로 둘지 vs 시뮬 공용(분석/토론 문서도 포함)으로 둘지. 공용이면 동료와 코퍼스 분담 합의(스펙 E1). → B-DBG에서 `source` 메타로 구분하는 공용안 권장.
2. **에이전트 LLM** — `ChatOpenAI`(management 검증·추적 안전) vs Gemini(프로젝트 챗 LLM). 오케스트레이터 결정에 종속.
3. **DB 미적재 폴백** — 개발/데모(`DATABASE_URL` 미설정·런 미완료)에서 `panel_composition`이 `panel-v1.json` 캐시로 폴백할지(management의 결정론 폴백 미러).
4. **실행 tool 소유·승인 UX** — `run_simulation`/`run_debate`를 공유 껍데기에 둘지, 확인 게이트를 오케스트레이터 레벨에서 통일할지(스펙 §F2 동기/비동기·§B2 출력 계약). 동료·팀 합의.
5. **`run_debate` 반응 소스** — 직전 시뮬 런 결과를 세션에 들고 갈지(상태 보관, 스펙 §C) vs 항상 `simulation_id`로 DB 재로드할지.
