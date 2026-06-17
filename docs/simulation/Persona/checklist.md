# 시뮬레이터 구현 — 체크리스트

> 원칙(§6): **완벽한 부품이 따로 노는 것보다, 어설퍼도 한 바퀴가 끝까지 도는 게 백 배 낫다.**
> 마감 2026-07-08 / 발표 2026-07-14. 결정·근거는 `context-notes.md` 참조.
>
> **진행 현황(2026-06-14)** — **P0~P9 ✅** + 테스트. grounding **real**(인구·지역·성격·소비가치·미디어·소득학력). 실 Gemini 반응·해석·루브릭(P4)·가중/층화 집계(§3.7)·검증데모(P9, 연령 미스매치 방향성 통과).
> 남음(비핵심): core/models 병합 · auth 도입 시 created_by 복원 · 광고 VLM(이미지) · LLM QA 비동기화 · 공개조사 직접대조. 데이터는 OCEAN 연령별(미공개)·MDIS 심층(발표 후)만.

## P0 — 계약 고정 (병렬 착수의 전제, ~0.5일)

- [x] §3.5 `페르소나반응` 스키마를 REPORT §2-3 enum과 1회 동기화 (`OVERPROMISE`·`EMPATHY` 추가)
- [x] `시뮬레이션집계` 컬럼 계약 확정(`click_intent_rate`·`ci_low/high`·`purchase_intent`·`trust_avg`·`rejection_rate`·`variance_warning`·`engine_version`)
- [ ] 두 계약을 분석팀과 공유(변경 시 동시 수정 합의)

## P1 — 데이터 레이어 (웹 확보분만 먼저)

- [x] `data/` 레이아웃 + 로더 설계 (`loader.py` + `data_status()`)
- [x] 인구 marginal — **real**(행안부 원본 CSV 적재·파싱 완료, 전국 5,109만 일치)
- [x] OCEAN 연령대별 JSON — 표본수·티어·5유형 real / **트레이트 mean·sd pending**(사용자 추출)
- [x] 소비가치 응답률 JSON — 대학내일 인용 실수치
- [x] raw 의존부(KISDI·MDIS)는 pending 표기 + `data/sources.md` 수집 가이드

## P2 — 샘플러 (단계 1~3, 코드·LLM✗)

- [x] 단계1 인구통계 뼈대 + `target_filter` 조건부 샘플링(Layer1 스킵 금지)
- [x] 단계2-α OCEAN 조건부 샘플링(연령 조건, `grounding_tier` 차등)
- [x] 단계2-β 미디어·소비 행동 — **stub**(KISDI raw 확보 후 교체)
- [x] 단계3 소비가치(Z세대 generation_specific)

## P3 — 패널 빌드 (4-a, 런타임과 분리)

- [x] 4-a 프로필 서사 생성 — MockNarrator + GeminiNarrator(gemini-2.5-flash, 실콜 검증)
- [x] 빌드 CLI(`build_cli`, 시드 고정, `panel-v1`) + 캐시 저장(gitignore)
- [x] 패널 로드 경로(`CachedPanelProvider`, 재생성✗, target_filter 부분집합)
- [x] 빌드 시점 QA(빈/실패 서사 제거)

## P4 — 광고해석 · 루브릭 · 반응 (런타임, 실 Gemini)

- [x] 반응 엔진(4-b) — `GeminiReactionEngine`, §3.5 구조화 JSON 강제, temperature↑(동질화 방지). 실콜 검증
- [x] 광고해석 어댑터 — `GeminiAdInterpreter`(ad_content 텍스트). VLM(이미지) 입력은 확장 여지
- [x] 루브릭 평가 — `GeminiRubricEvaluator`(광고 의존), 반응과 병렬
- [x] QA 게이트 — `RuleQaGate`(무콜, AISAS 깔때기·필수필드) + `GeminiQaGate`(LLM, 규칙 선검사 후 통과분만 광고무관·설정모순 검증, opt-in `use_llm_qa`). 실콜 검증
- [x] `wiring.use_mock=False` 연결 + 루트 `.env` 키 적재. mock↔real 토글 단일 지점
- [x] **`google-genai` SDK 이전** — `google.generativeai`(deprecated) → `google.genai` 전환(엔진·서사 어댑터·pyproject). 실콜 검증
- [x] **광고해석 VLM(이미지)** — `ad_image_url`(URL·로컬) → `Part.from_bytes` 멀티모달. 한글 이미지만으로 업종·타깃·메시지 추출 검증(`-vision`)
- [x] **전 호출 비동기화** — 반응·해석·루브릭·QA를 `client.aio`로 → fan-out 동시 진행(직렬화 제거). QA 인터페이스도 async

## P5 — 반응 유닛 (LangGraph 서브그래프, 사이클)

- [x] `react_subgraph`: `gen_reaction → qa_gate → (실패&재시도여유) gen_reaction / (통과·포기) return`
- [x] §3.5 structured output 강제(자유 텍스트 금지, enum 직접 출력) — `GeminiReactionEngine`(P4)
- [x] 모델 버전 pin(`gemini-2.5-flash`) — 실 어댑터. `panel_version` 기록은 영속화(P8)
- [x] 반응 캐시 금지 확인

## P6 — 오케스트레이션 그래프 (outer, 하이브리드)

- [x] outer DAG: `interpret_ad→load_panel→rubric_eval → Send×N react → aggregate` (불균등 join 회피 위해 preamble 직렬)
- [x] State TypedDict + `reactions: Annotated[list, operator.add]` 리듀서
- [ ] 체크포인터(긴 런 재개) + LangSmith 트레이스 확인 — P8(영속화)·실 어댑터와 함께
- [x] `wiring.py`가 그래프 빌드 → `SimulationService` 주입, `_run`은 `astream` 구동(SSE 진행률)

## P7 — 집계 엔진 (코드, "숫자는 집계 엔진")

- [x] QA 통과분만 집계
- [x] 부트스트랩 신뢰구간 `ci_low/high` 산출(순수 stdlib·결정적)
- [x] 분산 기반 `variance_warning` 산출(구매의도 집중도)
- [x] "CTR 예측" 라벨 금지 확인(집계는 `click_intent_rate`만, 실측 스케일 미환산)

## P8 — 영속화 (9테이블)

- [x] `repositories/` CRUD — panel·simulation 리포지토리 + 라운드트립 테스트(SQLite)
- [x] `SimulationPersistence`(orchestrator) — 패널+페르소나+실행을 한 트랜잭션 저장, service가 완료 시 호출
- [x] In-memory store(라이브 SSE)는 유지 + DB 저장은 `wiring.py`가 `session_factory`/`settings.database_url` 있을 때만 주입(없으면 생략)
- [x] **실 Neon 적용** — Alembic stamp 003 베이스라인 + `004`(socioeconomic·weight·effective_n 컬럼)·`005`(created_by nullable). 실 런 영속화 end-to-end 검증(스모크 후 정리)
- [x] 정본 정합 — 테이블명 `persona_responses`(←persona_reactions), 컬럼 `purchase_intent_avg`. FK 강제 대비 부모 단계적 flush
- [ ] ORM은 `domain/simulation/models.py` → 추후 `core/models.py` 병합
- [ ] (확장) auth 도입 시 `created_by` 재적용 + asyncpg SSL 인증서 경로(개발 Win/한글경로) 정리

## P9 — 검증 데모 (발표 결정타)

- [x] 연령×광고반응 미스매치 방향성 시연(`validation.py`) — 젊은-타깃 광고: 연령↑→거부율↑·구매의도↓. **비순환**(광고반응은 grounding 입력 아님). 실 Gemini로 가설통과 확인
- [x] `directional_verdict` 순수 판정 단위테스트(LLM✗) + `run_age_mismatch` 실행기·`main`
- [x] 정밀 수치 일치 추구 금지 — 방향만(전략서 §5)
- [ ] (확장) 공개 한국 조사 1건 직접 대조(추가 데이터 선정 시)

## 완료 게이트

- [ ] `cd backend && uv run ruff check . --fix` 통과
- [ ] `cd backend && uv run pytest tests/ -v` 통과
- [ ] P1~P7 한 바퀴(광고→반응→집계) end-to-end 동작
