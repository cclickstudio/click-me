# 집행 게이트 하드닝 설계 — 승인 플레인 보안 + 집행 권장 게이트 정본화 + launch_suggest 루프

> 2026-07-07 · management 도메인 · 브랜치 `feat/management-boeun`
> 상태: 설계 확정(사용자 승인) — 시뮬팀 확인 항목 2건 포함(§6)

## 1. 배경 — 안 닫힌 집행 게이트

감지→진단→제안→승인→집행→감사 파이프라인과 executor의 Tier·소프트캡·멱등 게이트는 갖춰져
있으나, **"사람이 진짜 승인했는가"를 보증하는 부분이 비어 있다.**

| # | 구멍 | 위치 | 내용 |
|---|------|------|------|
| ① | `/approve` 무인증 | `api/routers/management.py:692` | management write 계열 중 유일하게 `get_current_user` 없음. org 검증도 없음 — 비로그인 사용자가 아무 조직의 제안을 승인 가능 |
| ② | `approver_id` 클라이언트 수신 | `management.py:686-689` | body 필드(기본 `"user_demo"`)를 그대로 신뢰. executor의 Tier 3 게이트는 `approver_id == "AUTO"`만 거부(`executor.py:285`)라 임의 문자열로 사람 승인 위장 가능 |
| ③ | 승인 서버측 기록 부재 | `/approve` → `/execute` 왕복 | `ApprovedAction`이 서버 기록 없는 bearer 객체. executor 4단계 재검증은 클라이언트 제출 객체 내부 필드끼리의 대조라 자기완결적 위조 가능 — `/approve` 없이 `/execute`만으로 집행 가능 |
| A | 집행 권장 게이트 임시 해제 | `management.py:2530`, `ExecuteFromSimulation.tsx:11-12` | 프론트·백엔드 모두 TEST용 0%/100%로 해제 상태. 게다가 주석의 "운영 복원값" 20%는 실제 시뮬 분포와 안 맞음(실측 감각: 클릭 의향률 1%면 양호) |
| B | launch_suggest 미연결 | `simulation_service.py:127`(TODO), `AlarmCenter.tsx:334-348` | "집행 제안" 알림 생성 훅이 없고("좋음" 판정 기준 미확정 = open-decisions §1), 카드에도 집행 액션이 없음 |

참고: `budget-commit`(3093)·`activate`(3232)·`pause`(3415)는 서버가 `str(user.id)`를 승인자로
주입하는 올바른 패턴을 이미 사용 — 이 패턴을 승인 플레인 전체로 확장한다.

## 2. 범위

①②③ + A + B 전부. 워커잡·채팅 tool은 write를 직접 호출하지 않음을 확인했으므로 범위 외.

## 3. 설계 — 승인 플레인 보안 (①②③)

### 3.1 `/approve` 인증·org 검증 (①)

- `POST /api/management/approve`에 `user: User = Depends(get_current_user)` + `db` 추가.
- org 확인은 **`_require_org_id_write(user, db, action="approve")`** 사용 — `/execute`와 동일
  헬퍼로 admin impersonation 감사 흐름을 맞춘다.
- 시연 제안(`proposal.tenant_id == TENANT_ID` 센티넬)은 `/execute`와 동일하게 org 일치 면제
  (로그인은 필수). 실 제안은 `proposal.tenant_id == str(org_id)` 강제, 불일치 시 403.

### 3.2 승인자 서버 주입 (②)

- `ApprovalRequest`에서 `approver_id` 필드 제거. 서버가 `str(user.id)` 주입.
- 프론트 `api.ts`의 `approve()` 시그니처에서 approver_id 제거(현재 호출부는
  `ExecuteFromSimulation.tsx` 등 — 기본값 의존이라 실질 변경 없음).

### 3.3 DB 승인 원장 (③)

기존 `IdempotencyKeyRow`/`AuditEventRow` + `execution/db_stores.py` + wiring 교체 패턴을 따른다.

**모델** — `core/models.py`에 `ApprovalRecordRow` 추가(**팀 사전 공지 + Alembic, 단독 PR**):

| 컬럼 | 비고 |
|---|---|
| `approval_id` (PK) | `appr_…` |
| `proposal_id` | executor가 이미 검증하는 필드 — 원장에도 남겨 추적·불일치 진단 |
| `proposal_hash` | |
| `tenant_id` | |
| `approver_id` | 서버 주입값 |
| `action_tier` | |
| `execution_mode` | **위조 시 LIVE 전환 위험 — 반드시 검증 대상** |
| `approval_policy_version` | |
| `expected_state_version` | |
| `approved_at` / `expires_at` | |
| `consumed_at` (nullable) | 집행 성공 시 마킹 |

**발행** — `issue_approval()` 헬퍼(async): `validate_proposal()` → `approve()` → 원장 INSERT.
`approve()` 호출처 **라우터 4곳 전부 교체**(`/approve`·budget-commit·activate·pause) — 한 곳이라도
빠지면 그 경로의 승인이 executor 원장 게이트에서 전부 거부되므로 필수. 향후 Tier 0~1 내부
자동승인(AUTO) 경로가 생기면 그것도 `issue_approval()`을 거친다.

**검증(게이트 #5)** — executor의 `_validate()`는 **sync 순수 함수로 유지**하고, `execute()` 초반
sync `_validate()` 직후에 **별도 async 승인원장 게이트**를 호출한다. 제출된 `approved_action`의
`approval_id`로 원장을 조회해 다음 필드가 **전부 일치**해야 통과: `proposal_id` ·
`proposal_hash` · `tenant_id` · `approver_id` · `action_tier` · `execution_mode` ·
`approval_policy_version` · `expected_state_version` · `expires_at`. 레코드 부재/불일치 →
`UNAPPROVED_ACTION`(기존 FailureReason 재사용, 신규 에러 타입 없음). 집행 성공 시
`consumed_at` 마킹(재사용 방지는 기존 멱등 게이트와 이중 방어).

**배선** — `contracts/`에 `ApprovalStore` 포트, `execution/db_stores.py`에 `DbApprovalStore`,
테스트·demo용 `InMemoryApprovalStore`. **발행부와 executor가 같은 스토어 인스턴스를 공유**하도록
wiring 싱글턴으로 주입(mock↔실DB 교체는 `wiring.py` 유일 지점 규칙 유지).

## 4. 설계 — 집행 권장 게이트 정본화 (A)

- 임계값을 settings로 이동: `management_exec_gate_min_cir = 0.01` ·
  `management_exec_gate_max_rej = 0.2`. **잠정치이며 시뮬팀 확인 대상**(§6). 실측 누적 후
  calibration 해금 방침과 정합 — 코드 수정 없이 재조정 가능.
- 판정 함수 `is_executable_verdict(click_intent_rate, rejection_rate)`를
  `domain/management/contracts/`로 이동(단일 정본). 라우터 `_is_executable_verdict`는 위임.
- **경계값 명시**: `click_intent_rate >= 0.01 AND rejection_rate < 0.2`.
  클릭 의향률 1% 정확히는 **통과**, 거부율 20% 정확히는 **실패**. boundary 테스트 필수.
- 프론트 하드코딩(`EXEC_CIR`/`EXEC_REJ`) 제거 → 경량 `GET /api/management/exec-gate`로 임계값
  1회 조회(실패 시 기본값 폴백). 양쪽 "임시 TEST 해제" 주석 삭제.

### 임계값 근거(기록)

주석의 "운영 복원 20%"는 비현실적 — 현 시뮬 분포에서 클릭 의향률 1%면 양호. 과거 동물 사진
광고에서 5%가 나왔으나 어그로성 클릭으로 판단(제품 광고 타깃팅과 다른 조건). 거부율은 아직
분포 감이 없어 기존 20%를 잠정 유지.

## 5. 설계 — launch_suggest 집행 제안 루프 (B)

기준 정본은 §4의 `is_executable_verdict()` 하나 — launch_suggest 기준이 집행 게이트보다 느슨하면
알림→[집행하기]가 409로 튕겨 UX가 깨지므로, **동일 함수 재사용이 논리적 필연**이다. 이로써
open-decisions §1("좋음" 판정 기준)을 "매니지먼트 집행 게이트 재사용"으로 잠정 확정한다.

- **훅(시뮬 도메인 — 시뮬팀 확인 대상, §6)**: `simulation_service.py`의 TODO 자리에서 시뮬 집계
  완료 시 `is_executable_verdict(cir, rej)` 통과면 launch_suggest 알림 생성. gen_suggest 생성
  코드와 같은 자리·같은 패턴, `dedup_key=f"launch_suggest:{sim_id}"`. payload에 클릭 의향률·
  거부율·광고 제목 캐시(카드가 재조회 없이 렌더).
- **경계 규칙 준수**: 시뮬 → `domain/management/contracts/`만 import(내부 직접 import 아님).
- **카드(프론트)**: `AlarmCenter.tsx` launch_suggest 분기에 [확인] 옆 **[집행하기]** 추가 —
  payload의 `source_sim_id`·지표로 `ExecuteFromSimulation` 모달을 그 자리에서 재사용.
- **머지 순서**: 훅 커밋은 별도 분리, 시뮬팀 확인 전 머지 보류.

## 6. 팀 조율 항목

| 항목 | 대상 | 내용 | 차단 여부 |
|---|---|---|---|
| `core/models.py` `ApprovalRecordRow` | 전체 공지 | 단독 PR + Alembic 마이그레이션 | ③ 머지 전 공지 |
| launch_suggest 훅 | 시뮬팀 | `simulation_service.py`에 훅 추가(기준은 매니지먼트 집행 게이트 재사용) 승인 | 훅 커밋 머지 보류 |
| 게이트 잠정값 1%/20% | 시뮬팀 | settings 기본값 확인 — calibration 후 재조정 가능 | 비차단(잠정 적용) |

## 7. 에러 처리

- `/approve`: 미인증 401 / 타 org 403 / 3단계 검증 실패 409(기존 유지).
- `/execute`: 위조·부재 `approved_action` → `UNAPPROVED_ACTION` 결과(기존 스키마).
- `GET /api/management/exec-gate`: 프론트는 조회 실패 시 기본값(1%/20%) 폴백.
- launch_suggest 훅: 알림 생성 실패는 시뮬 결과 저장에 영향 없음(best-effort, gen_suggest 동일).

## 8. 테스트

1. 무인증 `/approve` → 401.
2. 타 org 제안 `/approve` → 403 (시연 센티넬은 통과).
3. body에 approver_id를 넣어도 무시되고(모델에서 필드 제거 — pydantic이 extra 무시)
   발행된 승인의 approver_id가 로그인 사용자 id인지 확인.
4. 위조 `ApprovedAction`(원장 부재) `/execute` → `UNAPPROVED_ACTION`.
5. 원장 필드 1개 불일치(특히 `execution_mode` LIVE 바꿔치기) → `UNAPPROVED_ACTION`.
6. 정상 `issue_approval()` → `/execute` 통과, `consumed_at` 마킹.
7. budget-commit·activate·pause 경로도 원장 게이트 통과(4곳 교체 검증).
8. `is_executable_verdict` boundary: `(0.01, 0.19)` 통과 · `(0.009…, x)` 실패 ·
   `(x, 0.2)` 실패 · `(0.01, 0.2)` 실패.
9. launch_suggest 훅: 게이트 통과 시 생성 / 미달 시 미생성 / 동일 sim 재실행 dedup.

## 9. 커밋 분할

1. `core/models.py` `ApprovalRecordRow` + Alembic (단독 PR, 팀 공지).
2. ①②③ — `/approve` 인증·서버 주입·`issue_approval()`·executor 원장 게이트 + 테스트.
3. A — 게이트 정본화(settings·contracts 이동·exec-gate 엔드포인트·프론트 연동) + 테스트.
4. B(프론트) — AlarmCenter [집행하기] 연결.
5. B(훅) — simulation_service 훅 (시뮬팀 확인 후 머지).
