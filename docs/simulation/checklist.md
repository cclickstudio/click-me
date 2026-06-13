# 시뮬레이터 구현 — 체크리스트

> 원칙(§6): **완벽한 부품이 따로 노는 것보다, 어설퍼도 한 바퀴가 끝까지 도는 게 백 배 낫다.**
> 마감 2026-07-08 / 발표 2026-07-14. 결정·근거는 `context-notes.md` 참조.
>
> **진행 현황(2026-06-13)** — P0·P1·P2·P3·P5·P6·P7 ✅ + 테스트. 인구 grounding **real**(행안부 CSV 적재).
> 남음: P4(실 광고해석·루브릭 어댑터)·P8(영속화)·P9(검증데모). 미수집 raw: OCEAN 트레이트·KISDI·MDIS(`data/sources.md`).

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

## P4 — 광고해석 · 루브릭 (런타임, 광고 의존)

- [ ] 광고해석(VLM) 어댑터 — 구조화 산출(`AdInterpretation`)
- [ ] 루브릭 평가(LLM, 광고만 의존) — 반응 fan-out과 **병렬**, 집계 직전 합류

## P5 — 반응 유닛 (LangGraph 서브그래프, 사이클)

- [x] `react_subgraph`: `gen_reaction → qa_gate → (실패&재시도여유) gen_reaction / (통과·포기) return`
- [ ] §3.5 structured output 강제(자유 텍스트 금지, enum 직접 출력) — 실 LLM 어댑터(P4)에서
- [ ] 모델 버전 pin + `panel_version` 기록(재현성) — 실 LLM 어댑터(P4)에서
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

- [ ] `repositories/` 9테이블 CRUD(현 InMemoryStore 대체)
- [ ] ORM은 `domain/simulation/models.py` → 추후 `core/models.py` 병합(Alembic·공지, 협업규칙)
- [ ] In-memory store는 그대로 두고 DB store 어댑터를 `wiring.py`에서 교체

## P9 — 검증 데모 (발표 결정타)

- [ ] 공개 한국 조사 1건(KISDI 1순위) 방향성 재현 시연
- [ ] 정밀 수치 일치 추구 금지 — 방향만

## 완료 게이트

- [ ] `cd backend && uv run ruff check . --fix` 통과
- [ ] `cd backend && uv run pytest tests/ -v` 통과
- [ ] P1~P7 한 바퀴(광고→반응→집계) end-to-end 동작
