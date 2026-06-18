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
- **토론(④/10)** — 토론자 **6명 + 주최자(Judge) 1명**, **2~4턴 유동**(churn·dispersion 게이트, MIN 2/MAX 4). 토론자 엔진 Haiku 2(피벗 포함)/GPT 2/Gemini 2, Judge=Opus. (사용자가 한때 "5명·2턴"이라 했으나 **철회 — 6명·2~4턴이 최신·확정**.) **※ Judge·구성·배정은 §4-2에서 변경(Judge=Sonnet, 도메인2/마케팅2/일반4=8명, 역할 라운드로빈, Gemini 제거→Haiku/GPT).**
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
  - **일반인 선발** = 우선순위 **피벗 → 비판자 →(4명)완주자 → 미온** 배타 선발, slot 5,6,… **연속** 배정(빈칸 없어 엔진 라운드로빈 균등: 6명 Haiku3/GPT3, 8명 Haiku4/GPT4). 피벗=신뢰-행동 갭, 비판자=`min(stance_score)`(항상 1명), 완주자=action 전형(클릭0%면 최대 긍정), 미온=미전환 중 피벗과 trust 차 최대.
  - **(보류) 타겟 적합 선발** — "과자면 10·20대 타겟에서 일반인 선발"은 반응 데이터에 나이·성별이 없어(=`PersonaReaction`에 인구통계 부재) 보류. 추후 reaction에 age/gender(Optional) 추가 + `detected_target` 규칙 파싱 필요.
  - **전문가 4** = 합성(실제 반응 없음). 도메인 2는 `ad_analysis`의 카테고리(`detected_industry`/`mismatch_detail.category.declared`)를 `{category}` 슬롯에 끼운 **고정 프롬프트 템플릿**(LLM 생성✗), 마케팅 2는 카테고리 무관 고정(퍼포먼스/브랜드). **분석결과(8·9)에 grounded** — "수치 밖 사실 금지" 프롬프트 제약.
  - **grounding 두 갈래** — 일반인=자기 실제 반응(1인칭), 전문가=분석 결과(3인칭 진단). 소비자 4 : 전문가 4 균형.
- **모델 배정 변경** — 전문가는 stance가 없어 기존 "입장순 교차" 불가 → **역할 기반 라운드로빈**(`PANEL_ENGINE`, `(slot-1)%2`). 토론자 8명 **Haiku4/GPT4**(엔진⊥역할). 피벗 Haiku 고정 규칙 폐기. **Gemini 제거**(`gemini-2.5-flash` 응답 실패 잦음 — 어댑터 코드는 복구용 잔존, `wiring`은 ANTHROPIC·OPENAI 키만 요구).
- **Judge 모델** — **Opus 4.8 → Sonnet 4.6 다운그레이드**(비용). Judge는 호출 3~4회라 비용영향 작고 종합추론 신뢰가 중요 → Haiku 대신 Sonnet 절충. `models.judge` = `claude-sonnet-4-6`.
- **코드 반영 완료** — `contracts/debate_schemas.py`(`is_expert`·전문가 `persona_profile`·`judge_engine="sonnet"`), `tools/debate/selector.py`(전문가4 합성+`detect_category`+일반인 `pick_pivot`/`pick_finisher`/`pick_critic`/`pick_second_undecided`, **`select_panel(reactions, ad_analysis, lay_count=4)`** 연속 slot), `assigner.py`(`PANEL_ENGINE=["haiku","gpt"]` slot 라운드로빈·Gemini 제거·`JUDGE_ENGINE="sonnet"`·전문가 프로필 승계), `adapters/llm_debate.py`(`SONNET_MODEL`·Judge engine 파라미터·`_expert_system` grounding 분기), `mock_debate.py`(역할 reason·비판자 dissent), `service/debate_service.py`(ad_analysis·**lay_count 전파**), **`api/routers/debate.py`(`POST /start?lay_count=2|4` 쿼리·422 검증)**, `wiring.py` 주석, `verify.py`(lay_count 2/4 둘 다)·`verify_debate`·`verify_stream`·`verify_persist`.
  - **미검증(잔여)**: 실 LLM 토론(`use_llm=true`)은 비용 때문에 안 돌림 — 전문가 grounding 실동작은 다음에 1회 확인 권장. GPT 쿼터 이슈는 그대로(§5-1).

## 4-3. 새 데이터 포맷 통합 + 메시지갭(②) + 타깃선발(①) + 포맷 스키마 (2026-06-17 세션)

데이터 생성 측이 포맷 변경(전체 시뮬 결과 = `personas` 분리·인구통계 포함). 신라면.json 수령 → 3기능 구현·검증.

- **새 포맷 통합** — `loader`가 `personas` 파싱(`DummyReactionSet.personas`), `dummy/result-dummy-sinramyeon.json` 추가. 새 포맷 = ad/ad_analysis/simulation/**personas**/reactions/aggregate. `Persona` 스키마와 일치해 바로 파싱.
- **② 메시지 수신 갭** — `analyzer._analyze_message`: 의도 메시지(`detected_message`) 대비 저항 표현(과장·식상·무관심 사전) 비율(결정론) → `MessageReception`. `kpi` 주신호 `message_gap`(저항≥0.5, 거부 다음 우선). 해석은 토론(LLM). 신라면 저항 0.8 → message_gap. **한계**: 한국어 신호어 사전이라 거침(케이스 누적 시 보강).
- **① 타깃 적합 선발** — `selector._filter_on_target`: 반응 분포로 타깃층 역산(관심층=interest·비거부의 나이중심+다수성별), 타깃 밖(나이·성별 둘 다 불일치) 일반인 후보 **배제(강)**. 풀<필요면 허용범위 단계 완화. `select_panel(.., personas)`, `SelectedPanel.target_*`, 라우터 `DebateRequest.personas`. **personas 없으면 현행(graceful)**. ⚠️ **§4-5(2026-06-17)에서 전 연령형 예외 추가** — 라면처럼 타깃 불명확 제품은 배제를 끄고 연령 다양성 선발로 전환(아래 참조).
- **데이터 포맷 스키마(전달용)** — `docs/simulation/sim-result-schema.md`. 중복(structured_analysis≈detected_*, mismatch≡rubric, _source 40회)·키불일치(consumption 3/5키)·빈값(profile_narrative·weight)·asset_url 로컬경로 정리한 권장 스키마. **데이터 준 사람에게 전달용**.
- 검증 `verify`에 신라면 케이스(메시지갭·타깃선발) 추가. verify 4종 + Ruff 통과.

## 4-4. 토론 주제 유동 생성 (2026-06-17 세션)

결정론 `build_topic`이 신호별 고정 템플릿("거부율 높으면 → 무엇이 거부를 부르나")만 내 토론 주제가 다 비슷·진단 질문(논쟁 안 됨)인 문제. → **실 LLM이면 Judge가 주제를 유동 생성**.

- **`JudgePort.refine_topic(topic, digest)`** — 결정론 시드 주제를 데이터 기반 '논쟁적' 주제로 교체. `MockJudge`는 시드 그대로 반환(재현·무비용), `LLMJudge`는 Sonnet으로 생성.
- **digest**(`debate_service._topic_digest`) — KPI·병목·이탈사유·메시지저항 + **실제 발언 샘플 5개**를 요약해 주입. "수치·발언 밖 사실 금지", "진단 질문 말고 대립 쟁점" 프롬프트 제약.
- `_run`에서 topic emit 전 `await to_thread(judge.refine_topic, ...)` (엔진 주입 시만). headline/question/diagnosis만 교체, signal/focus는 유지.
- **mock passthrough라 결정론 verify 영향 없음**. 실 LLM 주제는 비용 때문에 미검증(구조·폴백만 확인).

## 4-5. 전 연령형(타깃 불명확) 선발 보정 (2026-06-17 세션)

§4-3 타깃 적합 선발이 **신라면(라면=전 연령 소비, `detected_target`="라면을 즐겨먹는 일반 대중", `target_filter`=None)** 에서 오작동. 관심층이 17~61세 고루 퍼져 있는데도 중앙값(38)±12로 좁혀 **6명(10·20대 초반·50·60대) 배제**, 일반인 4명이 29~45세에 몰림. "38세만 관심 있나? 라면은 전 연령인데" 지적에서 출발.

- **전 연령형 판정** — `selector._is_broad_target`: `detected_target`이 포괄어(`_BROAD_TARGET_TERMS`: 일반 대중·전 연령·누구나·남녀노소·온 가족·전 국민·모든) **또는** 관심층(interest·비거부) 나이 std ≥ `BROAD_TARGET_AGE_STD`(10.0, 좁은 타깃은 보통 5~8). 신라면 std 11.85 → broad.
- **배제 끄기** — broad면 `_filter_on_target`을 스킵(`excluded=0`, `target_age_center=None`). 좁은 타깃(가전 등)은 기존대로 좁혀 배제.
- **연령 다양성 타이브레이크** — broad면 `age_spread=True`. 각 pick(피벗·비판자·완주자·미온)의 **핵심 기준(stance·갭·전형)은 유지**하고, 남은 **동점만** `_final_pick`이 '기선발자와 나이 차 최대 → id순'으로 가른다. `select_panel`이 `chosen_ages`를 누적해 점진 확장. → 신라면 일반인 23·29·45·53세(폭 30).
- **스키마** — `SelectedPanel.broad_target` 추가. `target_age_center`는 좁은 타깃일 때만 채움.
- **선발 철학 보존** — 사용자 선택(옵션 B): 토론 4역할(피벗·비판자·완주자·미온, 입장 대립) 유지하면서 연령만 퍼뜨림. 연령축 전면 전환(연령대별 1명)은 채택 안 함(토론 입장 다양성 약화 우려).
- **한계** — 양 극단(17·61세)은 stance 동점 그룹에 들 때만 선발됨(무조건 포함 아님). verify 4종 + Ruff 통과.

**후속(같은 세션) — 새 더미 6개(`dummy/new/dummy1~6.json`, 전부 personas 포함) 수령·회귀 검증 통합:**
- **좁은 타깃 회귀 확보** — 지난 한계(personas 더미가 신라면뿐)가 해소. 6개로 broad/narrow 양쪽 확인: broad=라면·치킨·쿠팡·커피(배제0, 연령폭30~44), narrow=화장품(여성 역산)·스마트폰. 성별 역산도 동작(단 표본 부족 시 완화 — 아래).
- **치킨 경계 케이스 보정** — 치킨은 전 연령인데 `detected_target`="…일반 소비자…"·관심층 std 9.9로 narrow 오판(7명 배제). → **① `BROAD_TARGET_AGE_STD` 10.0→9.5, ② `_BROAD_TARGET_TERMS`에 "일반 소비자"·"전반" 추가**(둘 다, 사용자 선택). 치킨 broad 전환, 화장품(7.7)·스마트폰(7.9)은 narrow 유지(마진 충분).
- **성별 역산 표본 부족 완화** — 스마트폰(성중립 제품)이 관심층 M5:F1(n=6)로 쏠려 남성 역산→여성 14명 배제되던 문제. 성별 쏠림이 진짜 타깃인지(화장품) 표본 편향인지(스마트폰) 데이터만으론 구분 불가 → **표본 크기로 가름**. `_target_profile`에 `GENDER_MIN_SAMPLE`(8): 관심층 < 8이면 성별 쏠림 신뢰 안 하고 전체 성별 허용(나이로만 좁힘). 스마트폰(6) 완화→배제 14→6·여성 후보 복귀, 화장품(11) 유지. **나이 broad와 다름**: 나이는 '넓은데 좁힘=오류', 성별은 '쏠림=신호일 수도'라 표본으로만 구분.
- **verify 통합** — `verify.py`에 6개 broad/narrow 분류·선발 불변식(broad=배제0·타깃중심None / narrow=배제>0·타깃중심有) 자동 단언 + dummy1 메시지갭 단언(아래). 기대분류(`new_expect`) 비교 — 분류 달라지면 단언이 깨져 회귀 감지.
- **sinramyeon 삭제·메시지갭 이관** — 데이터 측이 `result-dummy-sinramyeon.json` 삭제(→`dummy/new/dummy1.json` 라면이 동일 케이스). verify의 sinramyeon 메시지갭 단언(저항 0.8→message_gap)을 dummy1로 이관, 죽은 sinramyeon 블록 제거.
- **참고(문서-코드 표현 차)** — §4-3은 "나이·성별 둘 다 불일치 배제(강)"라 적었으나 코드 `on_target`은 AND(나이·성별 둘 다 맞아야 적합)라 실제론 '하나만 틀려도 배제'. 표현 정정 필요(동작은 의도대로).
- **⚠️ 병렬 작업 공존** — 같은 시기 selector.py에 LLM 재랭킹 게이트(`RerankFn`·`ROLE_DEFS`·`_pick_or_rerank`·`adapters/llm_selector.py`·`trap_check.py`·`selection-traps.json`) + 프론트(`DebatePanel.tsx` 등)가 별도로 추가됨. 본 보정과 한 파일(selector.py)에 공존 — 커밋 단위 분리는 그 작업과 조율 필요.

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
