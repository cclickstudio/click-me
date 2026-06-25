# 멀티테넌시 org 스코프 설계 (제너레이터·시뮬·매니지먼트·debate)

- 날짜: 2026-06-24
- 상태: 구현 완료 (검증: 백엔드 590 passed / 11 skipped, exit 0)
- 영역: `backend/api/routers/*`, `backend/domain/{management,generator,simulation}/*`, `backend/core/config.py`, 프론트 `manage/*`

## 1. 배경 / 문제

앱은 조직(org) 단위 멀티테넌트지만, 일부 읽기/쓰기 경로가 **로그인 org와 무관하게 동작**해 다른 org의 데이터가 보이거나 귀속이 어긋났다.

- **매니지먼트**: 캠페인 목록을 `.env`의 단일 전역 Meta 계정(`settings.meta_ad_account_id`)으로 모든 사용자에게 노출. 삭제는 org 소유 검증(`_require_owned_campaign`)을 했으나, 읽기는 전역이라 "남의 계정 캠페인을 보고 삭제 시도 → 403" 발생.
- **제너레이터**: `list_generations`(전역 목록)·`get_generation`·`select`·`publish`가 인증/org 필터 없음 → by-id로 타 org 생성물 접근 가능.
- **시뮬레이션**: `/{simulation_id}/db-result`(영속 조회)가 org 필터 없음.
- **debate**: `/by-simulation/{id}` 목록·리포트가 org 필터 없음.

데이터 **귀속**(`created_by`·`project_id`·`tenant_id`·`organization_id`)은 이미 올바르게 기록되고 있었다. 갭은 **조회 가시성과 쓰기 신뢰**였다.

대표 증상: `test1`(org `e33b37c6` → 연결 계정 `act_882`)로 로그인해도 전역 계정(`act_280`, org `bd9df2e2`)의 캠페인이 보이고, 삭제 시 "다른 조직의 캠페인입니다"(403).

## 2. 목표 / 위협 모델

- 로그인 사용자는 **자기 org의 데이터만** 보고/관리/집행한다.
- 다른 org 리소스 접근은 **존재 자체를 숨김**(404, fail-closed). 전역 계정 폴백 금지.
- 시뮬→집행→매니지먼트→비교 전주기가 **단일 org로 일관**.
- mock/데모·기존 테스트(무인증 호출)는 깨지지 않는다.

## 3. 설계 결정

| 결정 | 선택 | 이유 |
|---|---|---|
| org 출처 | **로그인 사용자에서 도출** | 클라이언트가 보낸 org_id를 신뢰하지 않음. 매니지먼트와 일관. |
| 실패 모드 | **404 (존재 은닉)** | 403보다 정보 노출 적음. |
| mock 모드 | **무인증·전역 동작 보존** | 데모/테스트 유지. live에서만 org 스코프. |
| 내부 서비스 호출 | **공유 시크릿 헤더(`X-Internal-Token`)** | 매니지먼트 `from-candidate`가 generator를 무인증 내부 HTTP로 읽음 → 토큰으로 우회 허용(완전 격리·기능 유지). dev 미설정 시 우회 검사 생략. |
| 브라우저 한계 | **SSE/이미지는 UUID 게이트 유지** | EventSource·`<img>`는 Authorization 헤더를 못 보냄. 완전 토큰화는 서명 URL 필요(범위 밖). |

## 4. 컴포넌트별 변경

### 4.1 매니지먼트 (`api/routers/management.py`)
- `_org_credentials` → `_resolve_reader`/`_resolve_writer`(org 연결 `MetaCredentials` 기반 `MetaAdsReader/Writer`) → `_require_reader`/`_require_writer`(미연결 409).
- `_optional_user`(토큰 있으면 검증, 없으면 None) + `_request_reader`/`_request_writer` 의존성: mock=전역, live=로그인 org.
- 전 캠페인 read/write(list·detail·breakdowns·funding·compare·anomaly·budget·delete·activate·pause·sync·from-candidate·from-simulation·create-proposal) + 집행 `Executor`를 org writer로 스코프.
- 비로그인/미연결: 목록은 빈 목록 + `auth_error`/`not_connected`, 그 외 401/409.

### 4.2 제너레이터 (`api/routers/generator.py`, `domain/generator/service/generator_service.py`)
- 라우터: `_require_user_org`·`_optional_user` 헬퍼.
  - `list_generations`·`select`·`publish` → 로그인 org(불일치 404). `create` → 프로젝트 org 소유 검증.
  - `get_generation` → ① 유저 토큰=org 스코프, ② `X-Internal-Token` 일치 또는 토큰 미설정(dev)=우회(from-candidate), ③ 그 외 401.
  - `stream`(SSE)·`proxy_image`(`<img>`) → UUID 게이트 유지(헤더 불가).
- 서비스: `get_detail(id, org_id=None)`·`list_generations(limit, org_id)` — `AdGeneration → Project.organization_id`로 검증/필터. org_id=None은 내부 우회.

### 4.3 내부 토큰 배선
- `core/config.py`: `internal_service_token: str | None = None` 추가.
- `domain/management/adapters/generator/client.py`: 설정 시 `X-Internal-Token` 헤더 전송.
- `domain/management/wiring.py`: `build_generator_client`가 토큰 주입.

### 4.4 시뮬레이션 (`api/routers/simulation/router.py`)
- `get_simulation_db_result` → 인증 + `simulations.organization_id == 로그인 org`(raw SQL, 도메인 ORM import 없이 경계 유지) 검증, 404.

### 4.5 debate (`api/routers/debate.py`)
- `_verify_sim_org` 헬퍼(raw SQL로 sim org 대조).
- `/by-simulation/{id}` 목록·`/report` → 로그인 org 시뮬만(404).

### 4.6 projects
- 변경 없음 — 이미 org 스코프(`WHERE organization_id = :org`).

## 5. 데이터 흐름 (집행 예시)

```
로그인(test1) → 제너레이터 생성(created_by=test1, project=test1 org)
  → 시뮬(organization_id=test1 org)
  → 집행: org_id=_require_org_id(test1) → _require_writer(org) = test1 연결(act_882)
         from-candidate가 generator를 X-Internal-Token으로 조회(우회)
         Executor(org writer)로 Meta 생성, created_campaigns.tenant_id=test1 org
  → 매니지먼트 목록/상세/삭제: _request_reader/_require_writer = test1 org만
  → before-after: created_campaigns.simulation_id로 test1 시뮬 예측 매칭
```

## 6. 범위 밖 (잔여 — 저위험)

- 인메모리 sim `result`/`analysis`(자기 run_id 즉시 조회).
- sim `start`의 폼 `organization_id` 신뢰(귀속은 프론트가 올바른 org 전송 → 실사용 정확).
- generator `stream`/`proxy_image` 완전 토큰화(서명 URL 필요).
- alembic 마이그레이션 그래프 정리(024 유령·중복 019/020 — 타 팀 조율).

데이터 귀속이 이미 정확해 기능 누수는 아님.

## 7. 테스트 / 검증

- ruff 클린, 앱 임포트 OK(144 라우트).
- 타깃: 제너레이터 29(**from-candidate 미파손** 확인)·시뮬+debate 129·매니지먼트 417.
- 전체 백엔드 **590 passed / 11 skipped**(회귀 0).
- 프론트: 보호 엔드포인트는 이미 토큰 전송(`request()`/Authorization) → UI 무파손, 프론트 코드 변경 0.

## 8. 배포 / 설정

- 백엔드 리로드로 반영.
- 운영: `INTERNAL_SERVICE_TOKEN` 설정 시 `get_generation`까지 완전 격리(dev 미설정도 동작).
- 협업 주의: 제너레이터·시뮬·debate는 타 팀(yunseop·yeotaeho) 도메인 — 본 변경은 사용자 승인 하에 수행, 통합 시 공지 필요.

## 9. 임시 항목 (운영 전 복원 필수)

테스트용 집행 게이트 해제가 코드에 남아 있음 — 운영 전 복원:
- `management.py` `_is_executable_verdict`: `>= 0.0 and <= 1.0` → `>= 0.2 and < 0.2`.
- `ExecuteFromSimulation.tsx` `EXEC_CIR/EXEC_REJ`: `0.0/1.0` → `0.2/0.2`, 비교 `<=` → `<`.
- `test_from_simulation.py`: 단언 원복 + `bad_verdict_409` skip 해제.
