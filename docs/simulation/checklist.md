# 시뮬레이터 구현 — 체크리스트

> 원칙(§6): **완벽한 부품이 따로 노는 것보다, 어설퍼도 한 바퀴가 끝까지 도는 게 백 배 낫다.**
> 마감 2026-07-08 / 발표 2026-07-14. 결정·근거는 `context-notes.md` 참조.

## P0 — 계약 고정 (병렬 착수의 전제, ~0.5일)

- [ ] §3.5 `페르소나반응` 스키마를 REPORT §2-3 enum과 1회 동기화 (`contracts/schemas.py`·`enums.py` 이미 존재 → 검토·확정)
- [ ] `시뮬레이션집계` 컬럼 계약 확정(`click_intent_rate`·`ci_low/high`·`purchase_intent`·`trust_avg`·`rejection_rate`·`variance_warning`·`engine_version`)
- [ ] 두 계약을 분석팀과 공유(변경 시 동시 수정 합의)

## P1 — 데이터 레이어 (웹 확보분만 먼저)

- [ ] `data/` 레이아웃 + 로더 설계 (분포 JSON을 읽는 코드, LLM✗)
- [ ] 인구 marginal(연령×성별×지역) 근사 분포 JSON — KOSIS/행안부
- [ ] OCEAN 연령대별 분포 JSON — Nature 논문 수치(20~30대 P1 / 40대+ P2 라벨, 자기선택 편향 주석)
- [ ] 소비가치 응답률 JSON — 대학내일20대연구소 공개 %
- [ ] raw 의존부(KISDI 미디어 다이어리·MDIS 사회조사)는 stub + 수동 다운로드 TODO 명시

## P2 — 샘플러 (단계 1~3, 코드·LLM✗)

- [ ] 단계1 인구통계 뼈대 + `target_filter` 조건부 샘플링(Layer1 스킵 금지)
- [ ] 단계2-α OCEAN 조건부 샘플링(연령 조건, 신뢰도 차등)
- [ ] 단계2-β 미디어·소비 행동(우선 stub/근사, raw 확보 후 교체)
- [ ] 단계3 소비가치 3~4개만(부실 다수 금지)

## P3 — 패널 빌드 (4-a, 런타임과 분리)

- [ ] 4-a 프로필 서사 생성(LLM 1콜/명, `with_structured_output`)
- [ ] 기본 패널 v1 빌드 CLI(1,000명, 시드 고정, `panel-v1`) + 캐시 저장
- [ ] 패널 로드 경로(시뮬레이션 런에서 재생성✗, 로드만)
- [ ] 빌드 시점 사전 QA(모순 프로필 제거)

## P4 — 광고해석 · 루브릭 (런타임, 광고 의존)

- [ ] 광고해석(VLM) 어댑터 — 구조화 산출(`AdInterpretation`)
- [ ] 루브릭 평가(LLM, 광고만 의존) — 반응 fan-out과 **병렬**, 집계 직전 합류

## P5 — 반응 유닛 (LangGraph 서브그래프, 사이클)

- [ ] `react_subgraph`: `gen_reaction → qa_gate → (실패&재시도여유) gen_reaction / (통과·포기) return`
- [ ] §3.5 structured output 강제(자유 텍스트 금지, enum 직접 출력)
- [ ] 모델 버전 pin + `panel_version` 기록(재현성)
- [ ] 반응 캐시 금지 확인

## P6 — 오케스트레이션 그래프 (outer, 하이브리드)

- [ ] outer 선형 DAG: `interpret_ad`·`load_panel`·`rubric_eval` → `Send×N react_subgraph` → `aggregate`
- [ ] State TypedDict + `reactions: Annotated[list, operator.add]` 리듀서
- [ ] 체크포인터(긴 런 재개) + LangSmith 트레이스 확인
- [ ] `wiring.py`가 그래프 빌드 → `SimulationService` 주입, `_run`은 `ainvoke`만

## P7 — 집계 엔진 (코드, "숫자는 집계 엔진")

- [ ] QA 통과분만 집계(현 `BasicAggregator` 골격 존재)
- [ ] 부트스트랩 신뢰구간 `ci_low/high` 산출(현재 TODO placeholder)
- [ ] 분산 기반 `variance_warning` 산출
- [ ] "CTR 예측" 라벨 금지 확인(calibration 전)

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
