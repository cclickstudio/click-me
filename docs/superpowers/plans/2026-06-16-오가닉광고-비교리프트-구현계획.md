# 오가닉↔광고 비교·리프트 검증 백엔드 Implementation Plan (🅰)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** management 도메인에 "오가닉 게시물 vs 광고 집행 게시물" 성과 비교·증분 리프트 판정 백엔드를, 🅰 역할 경계(읽기·분석, Writer 미호출) 안에서 공유 `contracts/` 무변경으로 구현한다.

**Architecture:** 신규 A-소유 서브패키지 `domain/management/comparison/`(A-로컬 DTO·Port + 순수 계산 + service). 오가닉 어댑터 `adapters/meta/organic_reader.py`는 기존 `client.py` 재사용, 광고측은 기존 `reader.get_metrics` 재사용. 데모는 `adapters/mock.py`의 `MockOrganicReader`로 성립(`use_mock` 게이트 유지).

**Tech Stack:** Backend FastAPI + pydantic v2(Contract 베이스 재사용) + pytest. 순수 계산은 `asyncio.run`으로 동기 테스트(추가 러너 의존 없음). 검증: `uv run pytest tests/management -q` + `uv run ruff check .`.

---

## File Structure

**신규 (🅰 단독)**
- Create: `backend/domain/management/comparison/__init__.py`
- Create: `backend/domain/management/comparison/schemas.py` — `PostInsights·LiftResult·PostType·LiftVerdict`
- Create: `backend/domain/management/comparison/ports.py` — `OrganicInsightsReader`
- Create: `backend/domain/management/comparison/lift.py` — `compute_lift()`
- Create: `backend/domain/management/comparison/service/__init__.py`
- Create: `backend/domain/management/comparison/service/comparison_service.py` — `ComparisonService`
- Create: `backend/domain/management/adapters/meta/organic_reader.py` — `MetaOrganicReader`
- Test: `backend/tests/management/test_lift.py`

**수정**
- Modify: `backend/domain/management/adapters/mock.py` — `MockOrganicReader` 추가 (🅰)
- Modify: `backend/domain/management/wiring.py` — `build_organic_reader`·`build_comparison_service` (🤝 append-only)

**공유 `contracts/`는 변경하지 않음.**

---

## Task 1: A-로컬 계약 (schemas + ports)

- [ ] **Step 1:** `comparison/schemas.py` 작성 — `PostType`·`LiftVerdict`(StrEnum), `PostInsights`·`LiftResult`(Contract 상속, frozen·extra=forbid).
- [ ] **Step 2:** `comparison/ports.py` 작성 — `OrganicInsightsReader` Protocol(`get_post_insights(post_id) -> PostInsights`).
- [ ] **Step 3:** `comparison/__init__.py`·`comparison/service/__init__.py` 생성.

## Task 2: 리프트 계산 (순수 함수) — TDD

- [ ] **Step 1: 실패 테스트** `tests/management/test_lift.py` — 통과(×3+)/주의(×1.5~3)/미달(<1.5)/오가닉 도달 0 케이스.
- [ ] **Step 2:** 테스트 실패 확인 (`compute_lift` 미구현).
- [ ] **Step 3:** `comparison/lift.py` 구현 — 분모 max(reach,1), 배수→판정, 증분 도달·노출 산출.
- [ ] **Step 4:** 테스트 통과 확인.

## Task 3: 비교 서비스 (합성)

- [ ] **Step 1:** `comparison/service/comparison_service.py` — `ComparisonService(organic_reader, ad_reader)` + `compare(organic_post_id, campaign_id, since)`. 광고 `MetricsSnapshot`→`PostInsights(paid)` 매핑 후 `compute_lift`.
- [ ] **Step 2:** 서비스 테스트(mock organic + fake ad)로 왕복 검증 — `asyncio.run`.

## Task 4: mock + 실어댑터

- [ ] **Step 1:** `adapters/mock.py`에 `MockOrganicReader` 추가(결정론 시드, `PostInsights` 반환).
- [ ] **Step 2:** `adapters/meta/organic_reader.py` — `MetaOrganicReader`, `client.get("{post_id}/insights", {"metric": ...})` IG 미디어 인사이트 파싱.

## Task 5: 조립 + 검증

- [ ] **Step 1:** `wiring.py`에 `build_organic_reader`(use_mock 분기)·`build_comparison_service` 추가(append-only).
- [ ] **Step 2:** `uv run pytest tests/management -q` 전체 회귀.
- [ ] **Step 3:** `uv run ruff format . && uv run ruff check . --fix`.
- [ ] **Step 4:** 커밋 — `add: 오가닉↔광고 비교·리프트 검증 백엔드 (comparison 서브패키지, 🅰)`.

## (후속, 본 PR 밖)

- 라우터 `GET /api/management/compare` 노출 (공유 파일 — append + A 합의 후).
- FB 페이지 게시물 insights·여러 게시물 일괄(테이블 뷰 B).
- 신뢰구간(CI) 산출 — 집계 외 데이터 필요(exploratory).
- 비교 산출물이 A↔B 계약이 되면 `comparison/schemas.py` → `contracts/`로 승격.
```
