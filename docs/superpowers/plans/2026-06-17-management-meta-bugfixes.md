# management Meta 연동 버그 수정 Implementation Plan (🤝 A+B 코드 리뷰 후속)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status: ✅ 완료 (2026-06-17).** 10건 전부 처리, management 테스트 126 통과·ruff 통과. 커밋 `c1b3d71`(수정)·`758d785`(KRW 검증)·`6edb241`(검증 로그). 두 브랜치(`feat/management-3k`·`feat/management`) 푸시 완료.

**Goal:** 2026-06-17 코드 리뷰(`/code-review high`)에서 확인된 management 도메인 Meta 연동 버그 10건을, Meta 실호출 전에 수술적으로 수정한다. 동작 불능(High 5) 우선, LIVE 전 리스크(Medium 5) 후속.

**Architecture:** 전부 `domain/management/` 내부 + 자기 라우터(`api/routers/management.py`) 범위. 공유 `contracts/`는 무변경(`platform.py` Port 시그니처는 이미 async 정본 — mock 구현을 Port에 맞추는 방향). 도메인 경계·다른 도메인 영향 없음. 어댑터 예외→FailureReason 번역은 executor가 아니라 어댑터(writer)가 담당(executor는 어댑터 비의존 유지).

**Tech Stack:** Backend FastAPI + httpx + pydantic v2 + pytest. 검증: `cd backend && uv run pytest tests/management -q` + `uv run ruff format . && uv run ruff check . --fix`. 각 수정은 가능하면 실패 테스트 선작성(TDD, CLAUDE.md §8).

---

## File Structure

**수정 (전부 기존 파일)**
- Modify: `backend/domain/management/adapters/mock.py` — `MockAdPlatform`에 Port 메서드(`get_metrics`/`get_state`/`get_estimate`) 추가 + `fetch_hourly_metrics` async화 [Fix 1·2]
- Modify: `backend/api/routers/management.py` — `fetch_hourly_metrics` await [Fix 2]
- Modify: `backend/domain/management/demo.py` — mock 호출 `asyncio.run` 래핑 [Fix 2]
- Modify: `backend/domain/management/detection/service/detection_service.py` — `run_detection_for_fault` mock 호출 `asyncio.run` 래핑 [Fix 2]
- Modify: `backend/domain/management/execution/executor.py` — 전량실패 시 멱등키 release + 부분실패 비례 예산 커밋 [Fix 3·9]
- Modify: `backend/domain/management/execution/db_stores.py` — `DbIdempotencyStore.release` 추가 [Fix 3]
- Modify: `backend/domain/management/adapters/meta/client.py` — `normalize_ad_account`·rate-limit 분류(`is_rate_limited`)·비JSON 방어 [Fix 4·6]
- Modify: `backend/domain/management/adapters/meta/reader.py` — `get_metrics` time_range 반영, `act_` 중복 제거 [Fix 5·6]
- Modify: `backend/domain/management/adapters/meta/writer.py` — Meta 예외→FailureReason 번역, `act_` 중복 제거, KRW 단위 주석 [Fix 4·6·10]
- Modify: `backend/domain/management/execution/audit_log.py` — 예산·소재 마스킹 + list 재귀 [Fix 7]
- Modify: `backend/domain/management/detection/deterministic_dx.py` — 0 나눗셈 가드 [Fix 8]

**테스트 (신규/보강)**
- Add: `backend/tests/management/test_comparison_wiring.py` — wiring 경유 compare 비크래시 [Task 1]
- Add: `backend/tests/management/test_audit_log.py` — 예산/소재/중첩 list 마스킹 [Task 7]
- Add: `backend/tests/management/test_deterministic_dx.py` — 0-기대구간 비크래시 [Task 8]
- Modify: `backend/tests/management/test_executor_gates.py` — 전량실패 재시도·부분실패 예산 [Task 3·9]
- Modify: `backend/tests/management/test_create_campaign.py` — `act_` 이중부착 금지 [Task 6]

**공유 `contracts/`는 변경하지 않음.**

---

## Task 1: 비교 기능 mock 크래시 [Fix 1 · High] — ✅

- [x] **Step 1: 실패 테스트** `test_comparison_wiring.py` — `build_comparison_service(use_mock).compare(...)`가 AttributeError 없이 LiftResult 반환.
- [x] **Step 2:** `MockAdPlatform`에 async `get_metrics`(하루 생성 후 마지막 시간 스냅샷=누적 reach·impressions) + Port 완성용 `get_state`(ACTIVE)·`get_estimate` 추가.
- [x] **Step 3:** 테스트 통과 확인.

## Task 2: fetch_hourly_metrics sync/async 통일 [Fix 2 · High] — ✅

- [x] **Step 1:** `MockAdPlatform.fetch_hourly_metrics`를 `async def`로 전환(실어댑터와 시그니처 일치).
- [x] **Step 2:** 호출부 수정 — `api/routers/management.py` `await`; `demo.py`·`detection_service.run_detection_for_fault`는 `asyncio.run(...)` 래핑.
- [x] **Step 3:** `uv run pytest tests/management -q` 회귀(detection/gate eval 포함) 통과.

## Task 3: 일시 실패 영구 박제 [Fix 3 · High] — ✅

- [x] **Step 1: 실패 테스트** `test_executor_gates.py` — 첫 호출 FAILED 후 같은 승인 재실행 시 재시도되어야(캐시 FAILED 반환 금지).
- [x] **Step 2:** `executor.execute` — 성공/PENDING만 `save_result`+예산 커밋. 전량 실패는 `idempotency.release(key)`로 선점 해제(재승인 없이 재시도 가능).
- [x] **Step 3:** in-flight reserve 후 결과 NULL 영구 잠금 경로 정합 — `release`로 해소. Protocol·InMemory·`DbIdempotencyStore`에 `release` 추가.
- [x] **Step 4:** 테스트 통과.

## Task 4: 재시도가 실어댑터에서 죽은 코드 [Fix 4 · High] — ✅

- [x] **Step 1:** (구현 변경) executor가 아니라 **어댑터(writer)가 번역** — 경계 유지. client에 `is_rate_limited`(코드 4/17/32/613/80000대) + 비JSON 응답 방어 추가.
- [x] **Step 2:** `writer._dispatch` — `httpx.TimeoutException`→TIMEOUT, `MetaApiError(is_rate_limited)`→RATE_LIMITED, 그 외 `httpx.HTTPError`→PLATFORM_ERROR로 FAILED 결과 반환.
- [x] **Step 3:** executor의 기존 재시도 분기(TIMEOUT/RATE_LIMITED)가 그대로 동작(어댑터가 올바른 FailureReason을 채움). executor 변경 없음.
- [x] **Step 4:** 회귀 통과(FakeWriter 재시도 테스트 유지).

## Task 5: get_metrics since 무시·하루치만 [Fix 5 · High] — ✅

- [x] **Step 1:** `reader.get_metrics` — params에 `time_range(since~today)` 추가, **time_increment 제거 → 단일 집계행**을 받는다(일별 다중행에서 rows[0]만 취하던 문제 해소). `as_of`는 date_stop.
- [x] **Step 2:** `ComparisonService`가 받는 누적 reach/impressions가 요청 구간 기준으로 정합.
- [x] **Step 3:** 계약 테스트 통과. 실 API로 요청 형태 유효 확인(아래 검증 로그) — 데이터 실증은 지출 캠페인 확보 후.

## Task 6: act_ 접두사 이중 부착 [Fix 6 · Medium] — ✅

- [x] **Step 1:** `client.normalize_ad_account` — `act_` 있으면 그대로, 없으면 부착(중복 방지).
- [x] **Step 2:** `reader.get_estimate`·`writer.create_campaign`에서 사용. `test_create_campaign`에 `act_…` 형태 이중부착 금지 테스트 추가.

## Task 7: 예산·소재 평문 감사 로그 [Fix 7 · Medium · CLAUDE.md 보안] — ✅

- [x] **Step 1: 실패 테스트** `test_audit_log.py` — `amount_krw`·`creative_id`·list 안 민감키가 마스킹됨.
- [x] **Step 2:** `mask_sensitive` — `_SENSITIVE_KEY_TOKENS`에 `budget`·`amount`·`creative` 추가 + `_mask_value`로 list 원소 재귀.
- [x] **Step 3:** 테스트 통과.

## Task 8: 진단 0 나눗셈 [Fix 8 · Medium] — ✅

- [x] **Step 1: 실패 테스트** `test_deterministic_dx.py` — `expected_window==0`일 때 `diagnose`가 크래시 없이 결과 반환.
- [x] **Step 2:** `deterministic_dx` — `deficit_ratio = ... if expected_window else 0.0` 가드.
- [x] **Step 3:** 테스트 통과.

## Task 9: 부분 실패 예산 미커밋 [Fix 10 · Medium] — ✅

- [x] **Step 1: 실패 테스트** `test_executor_gates.py` — 2타깃 중 1성공·1실패(PARTIAL_FAILURE) 시 성공분이 `BudgetAuthority`에 반영(`spent_krw == max_total * 1/2`).
- [x] **Step 2:** `executor` — PARTIAL_FAILURE는 결과 박제(자동 재시도 시 중복 집행 위험)하고 `_executed_target_count`로 집행 비율만큼 커밋.
- [x] **Step 3:** 테스트 통과.

## Task 10: KRW 예산 단위 검증 [Fix 9 · Medium] — ✅ (변환 불필요)

- [x] **Step 1:** 실계정 조회(2026-06-17) — currency=KRW, min_daily_budget=1521(≈$1.1) → **offset=1 확정**(100이면 최소예산 ₩15로 비현실적). `currency_offset`은 계정 노드 필드 아님(code=100).
- [x] **Step 2:** 결론 = 원 단위 그대로 전송이 정확 → 코드 무변경, 주석을 검증 결과로 정정.

## 검증 + 마무리 — ✅

- [x] **Step 1:** `uv run pytest tests/management -q` — 126 passed / 2 skipped.
- [x] **Step 2:** `uv run ruff format . && uv run ruff check . --fix` — All checks passed.
- [x] **Step 3:** 커밋 — `c1b3d71`(수정 10건)·`758d785`(KRW 검증)·`6edb241`(검증 로그). 두 브랜치 푸시.

## 실 API 검증 로그 (2026-06-17, System User 토큰)

계정 `act_882448327559337`(currency=KRW)에 실호출로 확인한 결과.

- **KRW offset = 1 확정 [Task 10]** — `min_daily_budget=1521`(≈$1.1)이라 원 단위 그대로가 정답. offset=100이면 최소예산 ₩15로 비현실적. `currency_offset`은 계정 노드 필드가 아님(code=100 에러)이라 `min_daily_budget`으로 역산. → 코드 무변경, 주석 정정.
- **get_metrics 요청 형태 유효 [Task 5]** — `time_range`(time_increment 없음) 요청을 Meta가 정상 수락(에러 없음). 다만 **계정에 캠페인·지출이 0이라 응답이 `[]`** → "단일 집계행 반환" 가정의 데이터 실증은 보류. 실 지출 캠페인 확보 후 `time_increment` 유무로 행 수 차이 재확인 필요(코드 문제 아님, 데이터 부재).

## (주의 · 본 PR 밖 · 후속)

- **남은 미검증 1건** — 실 지출 캠페인 확보 후 get_metrics 집계 동작 최종 실증.
- LIVE 모드 해금은 별도 — 본 수정은 DRY_RUN/SANDBOX 게이트 유지.
- 일부 파일은 B(kuk9096) 작성분 — 수정 범위 합의 필요 시 공유.
- cleanup(중복 `_to_int`·`dataclasses.replace`·`_stable_jitter`)는 별도.
