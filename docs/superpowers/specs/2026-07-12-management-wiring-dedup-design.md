# management 이중 배선 정리 — 실행 확정 롱텀 기록 배선 + 죽은 챗 집행 브릿지 제거

날짜: 2026-07-12 / 브랜치: feat/management-boeun / 상태: 설계 확정(사용자 승인), 구현 계획 대기

## 배경

management 집행 배선이 라우터(`api/routers/management.py`)와 wiring(`domain/management/wiring.py`)에 이중으로 존재한다. git 이력 조사 결과:

- 라우터 `_get_executor()`는 2026-06-15(`73f25d5d`)부터 자란 원조 단일 지출 경로. Tier 게이트·승인 원장·예산 캡·감사 로그가 전부 여기 붙어 있다.
- wiring의 `build_executor`·`resolve_execution_mode`·`state_version_v1`은 2026-06-24(`3fd740ce`) "챗 집행 브릿지"의 일부로 추가됐으나, 유일 소비자(`domain/chat/adapters/execution.py`)가 2026-06-29 병합(`4927c386`, 챗 헥사고날 구조 폐기)에서 삭제되며 고아가 됐다. 현재 `build_executor` 호출자는 테스트 포함 0곳.
- 이후 챗 아키텍처는 "어시스턴트는 제안만, 집행은 승인 화면→라우터"로 확정(`domain/management/assistant/contracts.py:36`, `graph.py:6`).

### 발견된 버그(깨진 전제)

`build_executor`에만 배선된 `history_recorder=build_history_recorder()`(실행 확정 → `chat_execution_history` 롱텀 메모리 기록)가 라우터 `_get_executor()`에는 없어서, **executor 기반 집행 경로(집행의 유일한 지점)에서 실행 확정 기록이 남지 않는다.** 정작 `api/assistant/subagent_tools.py:951` 주석은 "폼 시점 = '요청' 기록(실행 확정은 executor가 별도 기록)"이라고 executor 기록을 전제하고 있어, 챗이 요청만 남기고 실행 확정은 영영 안 남는 상태다. 이 정리는 데드코드 청소가 아니라 이 깨진 전제의 수리를 겸한다.

> 구분: 스케줄러도 `record_execution`을 호출하지만(scheduler.py `record_finding`) 그것은 자동 점검 **발견** 기록이며 실행 확정 기록이 아니다. 같은 테이블에 feature_type="management"로 적재되므로 혼동 주의.

### CREATE_CAMPAIGN 역추적 공백 (리뷰 P1 반영)

`resolve_project_id`는 `target_object_ids`를 캠페인 id로 보고 `created_campaigns`를 조회하지만, CREATE_CAMPAIGN 제안의 `target_object_ids`는 **광고계정 id**다(management.py:2320, "옵션 A"). 게다가 recorder는 `executor.execute()` 내부에서 호출되고 `_record_created_campaign()`(created_campaigns 적재)은 그 **뒤에** 실행되므로(management.py:891→894), 캠페인 id였더라도 그 시점엔 row가 없다. 따라서 배선만 추가하면 CREATE_CAMPAIGN은 실행 확정 기록이 계속 빠진다 — 커밋 1에 전용 분기를 포함한다(아래).

## 결정 사항 (사용자 확정)

| 결정 | 선택 |
| --- | --- |
| 실행 모드 해석·state version 정본 위치 | **wiring 정본** — 라우터는 wiring 함수를 호출 (CLAUDE.md "mock↔실연동 전환은 wiring에서만" 정합) |
| history_recorder 부착 범위 | **전역 싱글턴 + org 스코프 분기** — `_demo_executor`는 제외(시연 DB 격리 원칙 유지) |
| 부수 정리 | `_BUDGET` 리터럴 3_000_000 → `policy.DEFAULT_MONTHLY_TARGET_KRW` 상수 참조 |
| 진행 방식 | **3커밋 시퀀스**(fix → edit → delete), 각 커밋 독립 green |
| 동작 테스트 | executor 호출 시맨틱은 기존 테스트(`test_history_recorder.py`) 활용, **`history_link` 콜백 계약 + CREATE_CAMPAIGN 분기 + 집행 경로 도달(통합형) 테스트 신규 추가**(커밋 1 포함) |

## 커밋 1 — `fix: 실행 확정 롱텀 기록 배선`

### 변경

`backend/api/routers/management.py`

- 상단 import에 `from domain.management.history_link import build_history_recorder` 추가.
- `_get_executor()`의 두 `Executor(...)` 생성부(org writer 주입 분기 약 :280, 전역 싱글턴 분기 약 :291)에 `history_recorder=build_history_recorder(),` 추가.
- `_demo_executor()` 무변경.

`backend/domain/management/history_link.py` — CREATE_CAMPAIGN 분기 (리뷰 P1, 2차 리뷰에서 체인으로 확장)

- CREATE 제안은 생성 경로별로 귀속 단서가 다르다 — 수동 폼=`campaign_config.creative_ad_id`, 시뮬 기반=`simulation_snapshot.source_ad_id`(management.py:2842), 후보 기반=`candidate_snapshot.generation_id`(:2481). creative_ad_id만 보면 시뮬·후보 기반(주요 자동 생성 경로)이 전부 생략된다.
- 신규 helper 2종: `resolve_project_id_from_ad(ad_id)` — `ads.project_id` 직조회 / `resolve_project_id_from_generation(generation_id)` — `ad_generations.project_id` 직조회(core/models.py:546). 둘 다 best-effort, 기존 스타일 동일.
- `build_history_recorder` 콜백: CREATE_CAMPAIGN이면 **우선순위 체인** `creative_ad_id → source_ad_id → generation_id`로 귀속, 그 외 액션은 기존 `resolve_project_id(target_object_ids)`. 모든 단서 부재·비UUID면 기록 생략(기존 "연결 불가면 생략" 원칙).
- 대안이었던 "제안 생성 시 project_id를 evidence에 적재"는 라우터 3개 엔드포인트 수정이 필요하고 이미 발행된 제안에 소급이 안 돼 미채택. `platform_response_snapshot` 경유도 미채택 — snapshot의 Meta campaign id는 recorder 시점엔 `created_campaigns`에 없어(적재가 execute 이후, management.py:894) 역추적 불가.

### 동작 흐름 (executor에 이미 내장 — 배선만 추가)

1. 결과가 SUCCESS 또는 SUBMITTED_PENDING_REVIEW일 때만 콜백 호출 — 멱등 재생·거부 제외 (`executor.py:287`).
2. 콜백 예외는 `contextlib.suppress`로 삼켜 실행 결과 불변 — best-effort (`executor.py:291`).
3. 콜백 내부: 캠페인 id → `created_campaigns.creative_ad_id` → `ads.project_id` 역추적, 실패 시 조용히 생략. 성공 시 `chat_execution_history`에 actor(auto/user)·실행 모드·상태 포함 기록 (`history_link.py`).

### 테스트 (`test/backend/management/`)

배선 검증 (hermetic, 신규 `test_executor_wiring.py`):

- `_get_executor()._history_recorder is not None` (전역 분기)
- `_get_executor(fake_writer)._history_recorder is not None` (org 분기)
- `_demo_executor()._history_recorder is None` (데모 격리)
- 주의: `_executor`·`_demo_executor_instance` 모듈 전역 캐시 → 테스트 리셋 fixture 필요(기존 스위트의 싱글턴 리셋 패턴 확인 후 동일하게).

`history_link` 콜백 계약 (신규 `test_history_link.py`, `resolve_project_id`·`record_execution` monkeypatch 캡처 — `test/backend/generator/test_execution_history_record.py`·`test/backend/chat/test_management_history_record.py` 선례 패턴):

- 역추적 성공 시 `record_execution` 호출 계약 — feature_type `"management"`, action_type 소문자화, summary 구성(라벨·대상·hypothesis, 500자 절단)
- `approver_id == AUTO_APPROVER` → `actor: "auto"`, 아니면 `"user"`
- `resolve_project_id` None → 기록 생략(조기 반환)
- **CREATE_CAMPAIGN 전용 (리뷰 P1)**: 수동 폼(`creative_ad_id`)·시뮬 기반(`source_ad_id` 폴백)·후보 기반(`generation_id` 폴백) 세 경로 각각 기록됨 / 모든 귀속 단서 부재 시 생략 / `created_campaigns` 미적재 시점에도 동작(순서 독립)

집행 경로 도달 검증 (리뷰 P2 — 배선 검증만으로는 "recorder는 붙었는데 기록은 생략" 회귀를 못 잡음):

- `_get_executor()`가 만든 executor로 승인 발행(`test_approval_ledger_gate.py` 패턴 재사용)→`execute()`까지 태우고, `history_link.record_execution`(monkeypatch 캡처) 도달을 확인하는 통합형 단위 테스트 — PAUSE 1건 + **CREATE 실물 제안 형태(campaign_config + simulation_snapshot) 1건**(2차 리뷰 반영: PAUSE만으로는 CREATE 역추적 공백 회귀를 못 잡음).

executor 쪽 호출 시맨틱(성공 1회·재생/거부 미호출·콜백 예외 무해)은 `test_history_recorder.py`가 이미 고정 — 재작성 불필요.

## 커밋 2 — `edit: 실행 모드 해석·state version wiring 정본 통합`

### 변경

`backend/api/routers/management.py`

- `_resolved_execution_mode()` 본문을 `return resolve_execution_mode(settings)`로 교체. 함수는 얇은 래퍼로 존치(라우터 내 호출부 10여 곳 무변경). docstring을 "정본은 wiring.resolve_execution_mode"로 갱신.
- 로컬 `_state_version` 삭제, wiring `state_version_v1` import 후 executor 생성부 3곳(`_get_executor` 두 분기·`_demo_executor`)에 전달.
- `_BUDGET = TenantBudgetRegistry(default_limit_krw=DEFAULT_MONTHLY_TARGET_KRW)` — policy 상수 참조로 교체(값 동일 300만, 행동 불변).

`backend/domain/management/wiring.py`

- `resolve_execution_mode` docstring의 "라우터의 `_resolved_execution_mode()` 미러" 문구를 정본 선언으로 갱신.

### 테스트

- 행동 불변이 목표 — 기존 스위트 green이 1차 검증.
- 모드 해석 테스트는 **기존 `test_live_mode_gate.py`를 래퍼 경유 검증으로 유지** (리뷰 P3 반영 — MOCK 봉인·live·validate_only·garbage→DRY_RUN 폴백 4케이스가 이미 존재). 커밋 2 후 래퍼가 wiring 정본을 호출하므로 기존 테스트가 그대로 wiring 로직을 커버한다. 신규 테스트 불필요.

### 리스크

- import 방향 라우터→wiring 단방향, 순환 없음.
- 커밋 순서가 고아 방지: 커밋 2에서 wiring 두 함수의 새 소비자(라우터)가 생긴 뒤 커밋 3에서 옛 소비자(build_executor)를 지운다.

## 커밋 3 — `delete: 죽은 챗 집행 브릿지 잔해 제거`

- `wiring.py`의 `build_executor` 삭제(내부 전용 import 포함, docstring의 "10M" 오기도 함께 소멸).
- 섹션 주석 "챗 오케스트레이터 공유 팩토리(라우터와 병렬, 통합은 추후)" → 실제 역할("실행 모드·state version 정본 — 라우터가 사용")로 갱신.
- `resolve_execution_mode`·`state_version_v1`·`build_history_recorder`는 존치(커밋 1·2에서 실경로 소비자 확보).
- 호출자 0 확인됨 → 테스트 변경 없음, 전체 스위트 green 확인만.

## 범위 밖 / 후속 과제

1. **구 오케스트레이터 데드코드 삭제** — `api/assistant/orchestrator.py`·`intent.py`·`registry.py` + `api/assistant/wiring.py`의 `build_assistant`/`Orchestrator` 등록부. CLAUDE.md Open Issues 기존 항목대로 발표(7/14) 후 진행. `_build_*_handler`는 통합 딥에이전트가 재사용하므로 보존.
2. **org live 분기의 wiring 우회 정리** — `_resolve_reader/_resolve_writer`(management.py:3075·3087)가 `MetaAdsReader/Writer`를 직접 import하는 구조를 wiring 팩토리로 이관. 챗 도구·스케줄러가 전역 `.env` 토큰 기반 `build_reader(settings)`만 쓰는 이중 데이터 경로(라우터 live=org 연결, 챗·워커=전역 토큰) 문제와 묶어 별도 설계.

## 참고 — 이름 충돌 주의

`test/backend/management/helpers.py`의 테스트 헬퍼 `build_executor`는 wiring 것과 동명이인(집행 게이트 하드닝 계획 `2026-07-07-execution-gate-hardening.md`가 참조하는 것도 이쪽). 이번 삭제와 무관하며 건드리지 않는다.
