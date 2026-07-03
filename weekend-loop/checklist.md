# 주말 루프 백로그 — 시뮬레이션 중점 → 전체 확대

> 판정 게이트: `python weekend-loop/verify.py --scope <범위>` 가 GREEN 이어야 커밋.
> 원칙: **검증 가능한 것만** 루프에 맡긴다. 프롬프트 문구·LLM 응답 품질·페르소나 현실성은 손대지 않는다(판정 기준 없음).
> 각 항목은 "① 현 상태 재현/확인 → ② (필요시) 실패 테스트 작성 → ③ 통과시키기 → ④ verify GREEN → ⑤ 커밋" 순으로 처리한다.
> 확신이 안 서는 항목은 건드리지 말고 `context-notes.md` 에 관찰만 남긴다.

---

## 범위 1 — 시뮬레이션 (토요일, `--scope simulation`)

### A. 문서·주석 정합 (안전, 낮은 위험 · 먼저)
- [ ] **A1** `backend/domain/simulation/contracts/schemas.py:190` — "ci_low/high·variance_warning 의 정식 산출(부트스트랩 등)은 추후 구현" 주석이 stale. 부트스트랩 CI는 이미 `tools/aggregation/aggregator.py:44` `_weighted_bootstrap_ci` 로 구현됨. 주석을 현행 구현에 맞게 수정(제거 또는 "구현됨: weighted_bootstrap" 명시).
- [ ] **A2** `schemas.py:112` "캐시는 추후 구현" — `tools/panel/builder.py` 의 `CachedPanelProvider` 존재 여부 확인 후 주석 정합. 실제 구현됐으면 문구 갱신.
- [ ] **A3** `backend/domain/chat/__init__.py` 설명이 실제 구현 위치(`api/assistant/`)와 어긋남 (CLAUDE.md Open Issues 명시). docstring/주석만 정정, 코드 이동 없음.

### B. 집계 엔진 엣지케이스 커버리지 (핵심 로직 · 실패테스트→통과)
- [ ] **B1** `aggregator.py` — 아래 경계에서 예외 없이 합리적 값을 반환하는지 테스트 추가:
      가중치 전부 0 / 단일 표본(n=1) / 가중치 편차 극단(effective_n ≪ n) / 구매의도 전부 동일(variance_warning=True).
      먼저 `test/backend/simulation/test_aggregator.py` 현 커버리지 확인해 겹치지 않는 것만 추가.
- [ ] **B2** QA 통과 0건 경로(`aggregator.py:70-83`) 반환값 테스트 — variance_warning=True, effective_n=0.0, payload note 확인.
- [ ] **B3** `_effective_n` Kish 공식 — 균일 가중이면 == n, 편차 크면 < n 임을 수치로 assert.

### C. 반응 파이프라인 견고화 (부분 실패 경로 · 실패테스트→통과)
- [ ] **C1** `graph/run_graph.py:122-135` 반응 fan-out — 페르소나 1명 실패는 로그만 하고 진행, **전원 실패 시 RuntimeError**. 이 두 경로에 테스트가 있는지 확인하고 없으면 추가.
- [ ] **C2** `adapters/reaction_fallback.py` FallbackReactionEngine — primary 성공 / primary 실패→GPT 폴백 / 전부 실패→raise 3경로. `test_reaction_fallback.py` 갭만 보강.
- [ ] **C3** reaction QA 재시도 — MAX_ATTEMPTS 소진 후 강제 포함(qa_passed=True) 경로. `test_reaction_graph.py` 갭 확인.

### D. 패널 버전 추적 (관찰 먼저 · 확신 서면 수정)
- [ ] **D1** 인메모리 폴백은 `panel_version="panel-v1"` 문자열, DB 경로는 UUID 혼용(`simulation_service.py` / `schemas.py:114`). 실제로 run 결과 조회·비교에서 문제를 일으키는지 **먼저 재현**. 재현되면 버전 식별 일관화, 아니면 notes에만 기록하고 스킵.

---

## 범위 2 — 백엔드 전체 (일요일, `--scope backend`)
- [ ] **E1** 전체 pytest 그린 유지선에서 management/generator/chat 각 도메인 stale 주석·문서 정합 스윕(코드 이동 없이 주석만).
- [ ] **E2** 각 도메인 테스트 커버리지 갭 중 "결정적 로직"에 한해 엣지케이스 추가(LLM 호출 경로 제외).
- [ ] **E3** `ruff check --fix` 로 잡히는 것 정리(이미 그린이므로 신규 코드 한정).

## 범위 3 — 프론트·문서 (`--scope all`)
- [ ] **F1** `pnpm lint` / `pnpm build` 그린 유지. 신규 경고만 정리.
- [ ] **F2** docs 와 코드 정합(api-spec, db-schema 어긋남 스윕).

---

## 절대 하지 말 것 (루프 금지 영역)
- 프롬프트 문구·temperature·LLM 모델 파라미터 튜닝 (판정 기준 없음, 회귀 위험).
- 실 외부 API(Gemini/Meta/S3) 실연동 동작을 "개선"하려는 시도 (mock만 돌아 검증 불가).
- KPI 스케일 환산·캘리브레이션 (실측 데이터 필요, 기획서상 금지).
- `core/models.py`·`docs/db-schema.md` 단독 변경 (협업 규칙: 사전 공지 + Alembic 필요).
- `api/main.py` 라우터 등록 순서 변경 (append-only 규칙).
