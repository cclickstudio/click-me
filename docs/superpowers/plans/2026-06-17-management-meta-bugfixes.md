# management Meta 연동 버그 수정 Implementation Plan (🤝 A+B 코드 리뷰 후속)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-06-17 코드 리뷰(`/code-review high`)에서 확인된 management 도메인 Meta 연동 버그 10건을, Meta 실호출 전에 수술적으로 수정한다. 동작 불능(High 5) 우선, LIVE 전 리스크(Medium 5) 후속.

**Architecture:** 전부 `domain/management/` 내부 + 자기 라우터(`api/routers/management.py`) 범위. 공유 `contracts/`는 가능한 무변경(`platform.py` Port 시그니처는 이미 async 정본 — mock 구현을 Port에 맞추는 방향). 도메인 경계·다른 도메인 영향 없음.

**Tech Stack:** Backend FastAPI + httpx + pydantic v2 + pytest. 검증: `cd backend && uv run pytest tests/management -q` + `uv run ruff format . && uv run ruff check . --fix`. 각 수정은 가능하면 실패 테스트 선작성(TDD, CLAUDE.md §8).

---

## File Structure

**수정 (전부 기존 파일)**
- Modify: `backend/domain/management/adapters/mock.py` — `MockAdPlatform`에 Port 메서드(`get_metrics`/`get_state`/`get_estimate`) 추가 + `fetch_hourly_metrics` async화 [Fix 1·2]
- Modify: `backend/api/routers/management.py` — `fetch_hourly_metrics` await [Fix 2]
- Modify: `backend/domain/management/demo.py` — mock 호출 async 대응 [Fix 2]
- Modify: `backend/domain/management/detection/service/detection_service.py` — `run_detection_for_fault` mock 호출 async 대응 [Fix 2]
- Modify: `backend/domain/management/execution/executor.py` — 실패 결과 캐시 금지 + 부분실패 예산 커밋 [Fix 3·10]
- Modify: `backend/domain/management/adapters/meta/client.py` — rate-limit/timeout → FailureReason 매핑 + status 우선 처리 [Fix 4]
- Modify: `backend/domain/management/adapters/meta/reader.py` — `get_metrics` since 반영·집계, `act_` 중복 제거 [Fix 5·6]
- Modify: `backend/domain/management/adapters/meta/writer.py` — `act_` 중복 제거, 예산 단위 주석/검증 [Fix 6·9]
- Modify: `backend/domain/management/execution/audit_log.py` — 예산·소재 마스킹 + list 재귀 [Fix 7]
- Modify: `backend/domain/management/detection/deterministic_dx.py` — 0 나눗셈 가드 [Fix 8]

**테스트 추가/수정**
- Modify: `backend/tests/management/test_meta_adapter.py` — get_metrics since/집계, act_ 경로, 에러 매핑
- Add/Modify: `backend/tests/management/test_executor_gates.py` — 실패 비캐시·부분실패 예산
- Add: `backend/tests/management/test_comparison_wiring.py` — wiring 경유 compare 비크래시
- Modify: `backend/tests/management/test_audit_log.py`(있으면) — 예산/소재 마스킹

**공유 `contracts/`는 변경하지 않음.**

---

## Task 1: 비교 기능 mock 크래시 [Fix 1 · High]

- [ ] **Step 1: 실패 테스트** `test_comparison_wiring.py` — `build_comparison_service(settings_mock).compare(...)`가 AttributeError 없이 LiftResult 반환.
- [ ] **Step 2:** `MockAdPlatform`에 async `get_metrics(campaign_id, since)` 추가 — 하루 생성 후 마지막 시간 스냅샷(누적 reach·impressions) 반환. Port 완성용 `get_state`(ACTIVE)·`get_estimate`(간단 DeliveryEstimate)도 추가.
- [ ] **Step 3:** 테스트 통과 확인.

## Task 2: fetch_hourly_metrics sync/async 통일 [Fix 2 · High]

- [ ] **Step 1:** `MockAdPlatform.fetch_hourly_metrics`를 `async def`로 전환(시그니처를 실어댑터와 일치).
- [ ] **Step 2:** 호출부 수정 — `api/routers/management.py:80` `await`; `demo.py`·`detection_service.run_detection_for_fault`는 `asyncio.run(...)` 래핑(동기 진입점).
- [ ] **Step 3:** `uv run pytest tests/management -q`로 회귀(특히 detection/gate eval).

## Task 3: 일시 실패 영구 박제 [Fix 3 · High]

- [ ] **Step 1: 실패 테스트** `test_executor_gates.py` — 첫 호출 FAILED 후 같은 승인 재실행 시 재시도되어야(캐시 FAILED 반환 금지).
- [ ] **Step 2:** `executor.execute` — `save_result`를 성공/PENDING일 때만 호출(또는 FAILED 시 멱등키 해제). 재생 가드는 성공 결과만 반환.
- [ ] **Step 3:** in-flight reserve 후 결과 NULL 영구 잠금 경로도 점검(관련) — FAILED 비저장과 정합.
- [ ] **Step 4:** 테스트 통과.

## Task 4: 재시도가 실어댑터에서 죽은 코드 [Fix 4 · High]

- [ ] **Step 1: 실패 테스트** `test_meta_adapter.py` — Meta rate-limit 코드(예: 4/17/32/613) 응답 → `MetaApiError`가 RATE_LIMITED 성질을 갖고, executor가 재시도하도록.
- [ ] **Step 2:** `client._handle` — `res.status_code`/error code를 분류해 `MetaApiError`에 분류 플래그 추가(또는 RateLimited/Timeout 서브클래스). `res.json()` 전에 status 확인(비JSON 에러 바디 방어).
- [ ] **Step 3:** `executor._call_with_retry` — 어댑터 예외를 RATE_LIMITED/TIMEOUT FailureReason으로 매핑(httpx.TimeoutException 포함).
- [ ] **Step 4:** 테스트 통과(재시도 카운트 확인).

## Task 5: get_metrics since 무시·하루치만 [Fix 5 · High]

- [ ] **Step 1: 실패 테스트** — `get_metrics`가 `time_range`(since~now)를 보내고, 다중 일자 행을 합산(누적)해 반환.
- [ ] **Step 2:** `reader.get_metrics` — params에 `time_range` 추가, rows 합산(impressions·spend·clicks 누적, reach는 마지막/최대 보수), `as_of`는 마지막 date_stop.
- [ ] **Step 3:** 테스트 통과 + `ComparisonService` 영향 확인.

## Task 6: act_ 접두사 이중 부착 [Fix 6 · Medium]

- [ ] **Step 1:** 계정 ID 정규화 헬퍼 1곳(`client` 또는 adapters/meta 공용) — `act_` 있으면 그대로, 없으면 부착.
- [ ] **Step 2:** `reader.get_estimate`·`writer.create_campaign`에서 헬퍼 사용. `test_create_campaign`·`test_meta_adapter`로 양쪽 형태(`act_…`/`…`) 검증.

## Task 7: 예산·소재 평문 감사 로그 [Fix 7 · Medium · CLAUDE.md 보안]

- [ ] **Step 1: 실패 테스트** — payload에 `amount_krw`·`creative_id`·list 안 민감키가 있으면 마스킹됨.
- [ ] **Step 2:** `mask_sensitive` — `_SENSITIVE_KEY_TOKENS`에 예산·소재 키 추가(`budget`·`amount`·`creative`), list 원소 재귀.
- [ ] **Step 3:** 테스트 통과.

## Task 8: 진단 0 나눗셈 [Fix 8 · Medium]

- [ ] **Step 1: 실패 테스트** — `expected_window==0`(무예산/저페이싱)일 때 `diagnose`가 크래시 없이 결과 반환.
- [ ] **Step 2:** `deterministic_dx` — `deficit_ratio` 계산을 0 가드 뒤로 이동(또는 분모 max(.,1)).
- [ ] **Step 3:** 테스트 통과.

## Task 9: 부분 실패 예산 미커밋 [Fix 10 · Medium]

- [ ] **Step 1: 실패 테스트** — 다중 타깃 중 첫 성공·둘째 실패(PARTIAL_FAILURE) 시, 성공분 지출이 `BudgetAuthority`에 반영.
- [ ] **Step 2:** `executor` — 부분 실패 시 집행된 타깃 수만큼 예산 커밋(또는 타깃별 커밋 구조).
- [ ] **Step 3:** 테스트 통과.

## Task 10: KRW 예산 단위 검증 [Fix 9 · Medium · LIVE 전]

- [ ] **Step 1:** Meta currency offset(KRW) 문서 확인 — 실제 minor unit 기대 여부.
- [ ] **Step 2:** 결론에 맞춰 `writer.adjust_budget` 단위 변환 + 주석 정정(불확실하면 TODO+가드만, LIVE 봉인 유지).

## 검증 + 마무리

- [ ] **Step 1:** `cd backend && uv run pytest tests/management -q` 전체 회귀.
- [ ] **Step 2:** `uv run ruff format . && uv run ruff check . --fix`.
- [ ] **Step 3:** 논리 단위 커밋 — `fix: management Meta 연동 버그 수정 (코드리뷰 후속, High/Medium)`.

## (주의 · 본 PR 밖)

- LIVE 모드 해금은 별도 — 본 수정은 DRY_RUN/SANDBOX 게이트 유지.
- 일부 파일은 B(kuk9096) 작성분 — 수정 범위 합의 필요 시 공유.
- cleanup(중복 `_to_int`·`dataclasses.replace`·`_stable_jitter`)는 버그 수정 후 별도.
