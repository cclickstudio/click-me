# 작업 인수인계 노트 (세션 이어가기용)

> 노트북 세션을 집 데스크탑 새 세션에서 그대로 이어가기 위한 맥락 전체.
> 같은 디렉토리의 `pipeline-piece.md`(파이프라인 조각)와 `persona-debate-pipeline.md`(토론 설계)와 함께 읽을 것.

## 0. 프로젝트 한 줄

ClickMe — 집행 전 AI 가상 소비자에게 광고를 테스트하고 집행 후 성과를 추적하는 광고 전주기 플랫폼. 작업 브랜치 `feat/simulation-doyeon`. 지금 다루는 영역은 **시뮬레이터 도메인(`backend/domain/simulation/`)의 페르소나 토론 파이프라인**.

## 1. 전체 시뮬레이션 순서 (사용자 확정)

```
0 프로젝트 생성
1 광고 사용자 데이터 입력
2 데이터 파싱·전처리(광고 해석)
3 인구 분포·남녀 비율 고정
4 연령대별 성격·한국 정서(트렌드) 입력
5 페르소나 생성
6 타겟(설정 시 타겟 90% + 임의 10% / 미설정 시 합성 인구 100%)
7 반응 출력  ← 더미 5개가 여기
8 반응 분석        ← 토론 전 필수
9 수치 평균(KPI 확정)
10 페르소나 토론(LLM, 2~4턴, 토론자 8명 + 주최자 1명)
11 리포트 생성
```

## 2. 지금까지 한 작업 (요청 순서)

1. **프로젝트·시뮬레이션 도메인 파악** — 헥사고날 구조(contracts/adapters/graph/service/tools/wiring), LangGraph 2겹(run_graph + reaction_graph), 집계는 `BasicAggregator`(가중 부트스트랩 CI). 프론트(`api.ts`)가 구 `/api/simulate/*` 경로라 백엔드 `/api/simulation/*`와 불일치하는 문제 발견(별건, 미해결).
2. **`persona-debate-pipeline.md`(토론 설계) 검토** — 더미로 ①~⑤ 진행 가능한지 점검. ① 집계는 더미와 일치하나, ②(선발) 규칙에 모순·미정의가 있어 그대로 코딩하면 안 됨을 확인.
3. **선발 로직(②) 결정론화 — `persona-debate-pipeline.md` 수정 완료**:
   - 피벗 기준을 'stance 0에 가장 가까운'(→ 우연히 P-00009) 에서 **'신뢰-행동 갭'**(미전환자 중 trust 최고 → `trust − purchase_intent` 최대 → id순)으로 재정의. `stance_score`는 ③ 모델 배정 전용으로 분리.
   - 슬롯 **배타 배정**(우선순위 순, 이미 뽑힌 사람 제외) 명문화.
   - **슬롯6**(미온 다수 2) = 피벗과 trust 차 최대로 결정론화. **완주자** = `pick_representative`로 통일.
   - `stance_score`의 `stage_rank`에 `.get(stage, 1)` + AISAS 전 단계 매핑(미정의 `drop_stage` KeyError 방어).
   - 더미로 검증: 규칙대로 6명 선발 시 문서 표(P-00006/P-00011/P-00000/P-00013/P-00010/P-00009)와 정확히 일치 확인.
4. **토론 DB 테이블 재설계** — NeonDB 실측 결과: 기존 `debate_sessions`·`debate_statements`·`debate_results` 전부 0행이고 우리 6인·다라운드 토론과 구조 불일치(1:1·2인대립). 그래서:
   - 신설(`simulations` 1:N): `persona_debates` / `persona_debate_participants` / `persona_debate_utterances`. (SQL은 `docs/db-schema.md` v3.1에 반영)
   - 기존 `debate_*` 3개 DROP 쿼리 제공. `persona_id`는 더미 문자열·실 UUID 둘 다 받게 VARCHAR(50).
   - `docs/db-schema.md` 갱신(버전·목록 30개·Full Schema·관계도), `backend/api/routers/projects.py`의 삭제 SQL을 새 테이블로 교체(테이블 DROP 시 깨짐 방지).
5. **더미 5개 구조 통일** — `reaction-dummy1~5.json`(사이다/몬스터/칸쵸/다우니/삼성세탁기, 반응 수 10/20/28/40/18). dummy3/4/5에 `mismatch_detail.category`(declared=과자/생활/가전)와 `rubric` `category_alignment`를 dummy1/2와 동일 구조로 추가. 5개 전부 구조 일치 검증 완료. **이 더미는 7번(반응 출력) = 반응+집계까지 끝난 상태**.
6. **파이프라인 조각화** — 7번(더미) 다음의 8(반응 분석)→9(수치 평균)→10(토론)→11(리포트)을 stream으로 묶는 조각 분해. → `pipeline-piece.md` 작성.

## 3. 핵심 결정 (결론)

- **선발(②)** — 피벗 = 신뢰-행동 갭(캠페인 목표에서 파생). `stance_score`는 모델 배정 전용. 배타 배정·슬롯6·완주자 규칙 전부 결정론. (상세 = `persona-debate-pipeline.md`) **※ §4-2(2026-06-17)에서 도메인2+마케팅2+일반인4(총 8명)로 재편 — 아래 참조.**
- **토론(④/10)** — 토론자 **6명 + 주최자(Judge) 1명**, **2~4턴 유동**(churn·dispersion 게이트, MIN 2/MAX 4). 토론자 엔진 Haiku 2(피벗 포함)/GPT 2/Gemini 2, Judge=Opus. (사용자가 한때 "5명·2턴"이라 했으나 **철회 — 6명·2~4턴이 최신·확정**.) **※ Judge·구성·배정은 §4-2에서 변경(Judge=Sonnet, 도메인2/마케팅2/일반4=8명, 역할 라운드로빈).**
- **DB** — 새 3테이블, `simulations` 1:N(`UNIQUE` 없음), `ON DELETE CASCADE`. `persona_id` VARCHAR.
- **더미** — 7번 반응 출력. 토론 전 **8(반응 분석) 단계 필수**(바로 토론 금지).
- **구현 순서** — 결정론 조각(8·9·10-a·10-b) 먼저 → stream 골격 → LLM 토론(10-c)·리포트(11).
- **persona_name** — 더미는 factory를 안 거쳤으니 조각 10-b(배정) 시점에 결정론 부여.

## 4. 확인·미해결 사항

- [ ] 위 **CREATE(persona_debate*) / DROP(debate_*) SQL을 실제 NeonDB에 적용했는지** 확인. (권장: CREATE 먼저 → DROP 나중. Alembic 마이그레이션으로 하는 게 팀 규칙에 맞음.)
- [ ] **미커밋 변경 커밋·push** — `docs/db-schema.md`, `backend/api/routers/projects.py`, `backend/domain/simulation/dummy/*`, `docs/simulation/debate/persona-debate-pipeline.md`, 본 `docs/simulation/debate/*`. (커밋 2~3개로 분리 제안: 토론 테이블 재설계 / 더미·선발 / 파이프라인 문서)
- [ ] 프론트 `api.ts`의 `/api/simulate/*` 경로 불일치(별건).
- [x] 토론 인원 — §4-2(2026-06-17)에서 **8명**(도메인2+마케팅2+일반인4)으로 확정. selector 슬롯(전문가4 + 일반인4) 동기화 완료.

## 4-1. 조각 8~11 + wiring·라우터·DB영속화 구현 완료 (2026-06-16 세션)

**8~11 결정론 파이프라인 + mock 토론 + API 노출 + DB영속화 코드까지 구현·검증했다.** (커밋 8개, 전부 `feat/simulation-doyeon`)

추가 완료(파이프라인 위):
- **실 LLM 토론 엔진** — `adapters/llm_debate.py`(`LLMDebater`/`LLMJudge`). engine별 SDK 라우팅(haiku→Anthropic `claude-haiku-4-5`, gpt→OpenAI `gpt-4o-mini`, gemini→Google `gemini-2.5-flash`, Judge→`claude-opus-4-8`). 발화는 실제 반응 데이터에 grounded, JSON 유도·파싱, 실패 시 중립 fallback. `wiring.build_debate_service(use_mock=False)`로 교체, `DebateService`가 `run_debate`를 `asyncio.to_thread`로 분리. 라우터 `?use_llm=true`. **동작 확인: Haiku·Gemini·Opus 정상 / GPT는 OpenAI 계정 쿼터(429 insufficient_quota)로 fallback — 결제 충전 필요(코드 무관).**
- **wiring 연결** — `wiring.py`에 `build_debate_service(use_mock, session_factory)`·`build_debate_persistence`. mock·실 LLM·영속화 주입 Composition Root.
- **라우터 노출** — `api/routers/debate.py`(`POST /api/debate/start`·`/dummy/{name}/start`·`GET /{run_id}/stream`·`/result`) + `api/main.py` append-only 등록. mock으로 실 HTTP+SSE 동작 확인(TestClient).
- **DB 영속화(코드만, NeonDB 미적용)** — `core/models.py` ORM 3모델(공통부) + `alembic/versions/007_add_persona_debate_tables.py` + `repositories/debate_repository.py`(순수매핑 `build_debate_rows` + `DebateRepository.save`). `DebateService`에 `persistence`+`simulation_id` 주입 — **FK상 실 simulations 행 있는 운영 경로에서만 저장**(더미 데모는 인메모리). 검증 `verify_persist.py`(ORM 메타+매핑, 더미 5개 통과).
  - ⚠️ **NeonDB `alembic upgrade head` 미실행** — 도연님 적용 필요. 단 **기존 004 revision 중복**(`004_add_ad_campaign_logs`·`004_add_simulation_weight_socioeconomic` 둘 다 revision=004) 때문에 alembic 체인이 깨져 있어 **먼저 004 중복부터 해소**해야 함(별도 task로 분리해둠).

**8~11 결정론 파이프라인 + mock 토론** (파이프라인 본체):

- **조각 8 반응 분석** — `tools/debate/analyzer.py`. AISAS 퍼널(단계별 flag 합산, 비단조 대비)·병목(인접 단계 인원 최대감소)·이탈/거부/감정 분해·소비자 그룹(겹침 허용). → `ReactionAnalysis`.
- **조각 9 KPI+주제** — `tools/debate/kpi.py`. 기존 `BasicAggregator` 재사용(더미 `aggregate`와 일치 검증) + 주신호(rejection/trust_action_gap/early_attrition/mid_attrition) 분기 토론 주제. → `DebateTopic`.
- **조각 10-a 선발** — `tools/debate/selector.py`. 6슬롯 배타배정·빈슬롯 보충(fallback)·비판자 확보. 피벗=신뢰-행동 갭.
- **조각 10-b 배정** — `tools/debate/assigner.py`. 입장순 엔진 교차(haiku2/gpt2/gemini2, 피벗 haiku)·persona_id 결정론 이름(sha256, 중복회피).
- **조각 10-c 토론(mock)** — `tools/debate/runner.py`(유동 라운드 MIN2/MAX4 + churn·dispersion 게이트) + `contracts/debate_ports.py`(DebaterPort/JudgePort) + `adapters/mock_debate.py`(MockDebater/MockJudge). mock은 churn=0 → 2라운드 consensus. **실 LLM 붙이면 churn 발생 → 3~4턴 가능.**
- **조각 11 리포트** — `tools/debate/report.py`. KPI+분석+토론 결론·발언 인용 결정론 조립. → `SimulationReport`.
- **stream 오케스트레이션** — `service/debate_service.py`. 8→9→10-a→10-b→(10-c)→11 순차 실행, 단계 이벤트 SSE emit. 엔진 미주입이면 10-c placeholder. 기존 `simulation_service` store/SSE 패턴 재사용.
- **스키마** — `contracts/debate_schemas.py`에 전부 모음(공용 `schemas.py` 안 건드림).
- **검증(도메인 내부, pytest 밖)** — `tools/debate/verify.py`(8·9·10-a·10-b) / `verify_stream.py`(stream 골격) / `verify_debate.py`(게이트 단위 + mock 토론 + 리포트). 더미 5개 전부 통과. 실행: `cd backend && uv run python -m domain.simulation.tools.debate.<모듈>`.

## 4-2. 패널 구조 변경 (2026-06-17 세션) — **설계 + 코드 반영 완료**

토론 패널 구성(전문가4 + 일반인 2 또는 4)과 Judge 모델을 바꿨다. **문서 4개 + 코드 전부 반영하고 verify 4종(8·9·10-a·10-b / 10-c mock / stream / persist) 더미 5개 통과·Ruff 통과까지 확인했다. 일반인 2/4는 `lay_count` API로 분리.**

- **패널 구성** — 기존 "전원 실제 반응자 6명" → **전문가 4 + 일반인 N**. 일반인 수는 `lay_count`(API 파라미터, 기본 4)로 선택: **2명(피벗·비판자) / 4명(+완주자·미온)**. ⚠️ **2 vs 4 어느 쪽이 나은지 미검증 — 둘 다 돌려보고 결정(사용자 요청으로 API 분리).**
  - **일반인 선발** = 우선순위 **피벗 → 비판자 →(4명)완주자 → 미온** 배타 선발, slot 5,6,… **연속** 배정(빈칸 없어 엔진 라운드로빈 균등: 6명 2/2/2, 8명 3/3/2). 피벗=신뢰-행동 갭, 비판자=`min(stance_score)`(항상 1명), 완주자=action 전형(클릭0%면 최대 긍정), 미온=미전환 중 피벗과 trust 차 최대.
  - **(보류) 타겟 적합 선발** — "과자면 10·20대 타겟에서 일반인 선발"은 반응 데이터에 나이·성별이 없어(=`PersonaReaction`에 인구통계 부재) 보류. 추후 reaction에 age/gender(Optional) 추가 + `detected_target` 규칙 파싱 필요.
  - **전문가 4** = 합성(실제 반응 없음). 도메인 2는 `ad_analysis`의 카테고리(`detected_industry`/`mismatch_detail.category.declared`)를 `{category}` 슬롯에 끼운 **고정 프롬프트 템플릿**(LLM 생성✗), 마케팅 2는 카테고리 무관 고정(퍼포먼스/브랜드). **분석결과(8·9)에 grounded** — "수치 밖 사실 금지" 프롬프트 제약.
  - **grounding 두 갈래** — 일반인=자기 실제 반응(1인칭), 전문가=분석 결과(3인칭 진단). 소비자 4 : 전문가 4 균형.
- **모델 배정 변경** — 전문가는 stance가 없어 기존 "입장순 교차" 불가 → **역할 기반 라운드로빈**(`PANEL_ENGINE`, `(slot-1)%3`). 토론자 8명 Haiku3/GPT3/Gemini2(엔진⊥역할). 피벗 Haiku 고정 규칙 폐기.
- **Judge 모델** — **Opus 4.8 → Sonnet 4.6 다운그레이드**(비용). Judge는 호출 3~4회라 비용영향 작고 종합추론 신뢰가 중요 → Haiku 대신 Sonnet 절충. `models.judge` = `claude-sonnet-4-6`.
- **코드 반영 완료** — `contracts/debate_schemas.py`(`is_expert`·전문가 `persona_profile`·`judge_engine="sonnet"`), `tools/debate/selector.py`(전문가4 합성+`detect_category`+일반인 `pick_pivot`/`pick_finisher`/`pick_critic`/`pick_second_undecided`, **`select_panel(reactions, ad_analysis, lay_count=4)`** 연속 slot), `assigner.py`(`PANEL_ENGINE` slot 라운드로빈·`JUDGE_ENGINE="sonnet"`·전문가 프로필 승계), `adapters/llm_debate.py`(`SONNET_MODEL`·Judge engine 파라미터·`_expert_system` grounding 분기), `mock_debate.py`(역할 reason·비판자 dissent), `service/debate_service.py`(ad_analysis·**lay_count 전파**), **`api/routers/debate.py`(`POST /start?lay_count=2|4` 쿼리·422 검증)**, `wiring.py` 주석, `verify.py`(lay_count 2/4 둘 다)·`verify_debate`·`verify_stream`·`verify_persist`.
  - **미검증(잔여)**: 실 LLM 토론(`use_llm=true`)은 비용 때문에 안 돌림 — 전문가 grounding 실동작은 다음에 1회 확인 권장. GPT 쿼터 이슈는 그대로(§5-1).

## 5. 다음 할 일 (외부 환경/개선)

결정론 8~11 + mock·실 LLM 토론 + API + DB영속화 코드까지 끝났다. 남은 건 환경·연결·개선.

1. **GPT 쿼터 충전** — OpenAI 계정 `429 insufficient_quota`로 gpt 토론자 2명이 fallback 중. 결제 충전하면 즉시 정상(코드 변경 불필요). 안 되면 `llm_debate.GPT_MODEL` 교체나 엔진 배분에서 gpt 제외 검토.
2. **NeonDB 적용** — (선결) 004 revision 중복 해소(별도 task) → `uv run alembic upgrade head`로 007 적용. 그 뒤 운영 경로(실 simulation_id)에서 `DebateService(persistence=...)` 저장 end-to-end 확인.
3. **운영 연결** — 실제 7번(반응 출력) 산출 → `/api/debate/start`에 reactions + simulation_id 전달(simulation_service 완료 후 토론 트리거). 현재 라우터는 더미·body 입력만.
4. **라운드별 실시간 stream(개선)** — 현재 `run_debate`를 `to_thread`로 돌려 라운드 emit이 사후. 실시간 노출하려면 `run_debate`에 라운드 완료 콜백(스레드세이프 emit) 추가.
5. **프론트 연동** — SSE 단계 이벤트(analysis→…→round_N→judge_final→report→completed) 소비 + 리포트 렌더.

## 6. 핵심 파일

| 무엇 | 경로 |
| --- | --- |
| 토론 설계(선발·배정·라운드 규칙) | `docs/simulation/debate/persona-debate-pipeline.md` |
| 파이프라인 조각(8~11) | `docs/simulation/debate/pipeline-piece.md` |
| DB 스키마(v3.1, 새 토론 테이블) | `docs/db-schema.md` |
| 더미 5개 | `backend/domain/simulation/dummy/reaction-dummy1~5.json` |
| **조각 8~11 코드** | `backend/domain/simulation/tools/debate/`(analyzer·kpi·selector·assigner·runner·report·loader·verify*) |
| **토론 DTO·포트** | `backend/domain/simulation/contracts/debate_schemas.py`·`debate_ports.py` |
| **mock 엔진** | `backend/domain/simulation/adapters/mock_debate.py` |
| **실 LLM 엔진** | `backend/domain/simulation/adapters/llm_debate.py`(모델 ID 상수 상단) |
| **오케스트레이션** | `backend/domain/simulation/service/debate_service.py` |
| **라우터(/api/debate)** | `backend/api/routers/debate.py` + `api/main.py` 등록 |
| **영속화·ORM·마이그레이션** | `repositories/debate_repository.py` · `core/models.py`(PersonaDebate*) · `alembic/versions/007_*` |
| **wiring** | `backend/domain/simulation/wiring.py`(`build_debate_service`·`build_debate_persistence`) |
| 시뮬 도메인 코드 | `backend/domain/simulation/` (service·graph·tools·adapters·wiring) |
| 프로젝트 삭제 SQL(토론 테이블 참조) | `backend/api/routers/projects.py` |
