# admin의 management org 스코프 설계 (impersonation + DB 전체뷰)

- 작성일: 2026-07-01
- 범위: `backend/api/routers/management.py`, `frontend/src/lib/api.ts` + admin org 선택 UI
- 관련: `backend/core/access.py`, `backend/core/auth.py`, `backend/api/routers/admin.py`, `backend/core/models.py`

## 1. 배경 / 문제

management 라우터는 org-스코프 엔드포인트마다 `_require_org_id = require_user_org`(소속 org 없으면 409)를 **무조건** 호출한다. ADMIN 특례가 없어, org 미소속인 admin은 management 데이터를 전혀 못 본다.

반면 `projects/chat/generator/simulation`은 `core/access.py`의 `project_access_ok`(`role == "ADMIN" → 전체`)와 `list_projects`의 role 분기(ADMIN이면 org 필터 없이 전체)를 쓴다. **즉 management만 이 role 인지 규칙을 안 따라서 불일치가 발생**한다.

추가 제약: ADMIN 계정은 설계상 org에 소속되지 않는다(`admin.py`의 `create_user`에 ADMIN용 `OrganizationMember` 생성 분기 없음). 따라서 admin은 `require_user_org`에서 곧바로 409를 받는다.

## 2. 목표 / 비목표

**목표**
- admin이 management를 다른 기능과 동일한 수준으로 볼 수 있게 한다.
- 멀티테넌시 격리(비-ADMIN은 자기 org만)를 훼손하지 않는다.

**비목표**
- live Meta 데이터의 "전 org 실시간 통합 뷰"는 만들지 않는다(각 org 토큰별 API·rate limit 때문에 비현실적).
- 인증 방식(JWT/Cognito) 자체 변경은 없다.

## 3. 핵심 결정

management엔 성격이 다른 두 종류의 엔드포인트가 섞여 있어 처리를 나눈다.

| 종류 | 예시 | admin 처리 |
|---|---|---|
| operational · 단일 org | reader/writer, activate, approve, link-simulation, budget mutate | **org 선택(impersonate)** — admin이 고른 org 회원처럼 동작 |
| 읽기 전용 리스트 · 집계 (순수 DB) | created_campaigns, KPI override 리스트, budget status 조회 | **무헤더 = 전 org 조회**, 헤더 있으면 그 org |

live Meta reader를 타는 조회는 단일 org 토큰이 필요하므로 "전 org"에서 제외하고, impersonate(org 선택)로만 처리한다.

**전송 방식** admin이 고른 org id를 `X-Org-Id` 헤더로 전달한다. 라우터 레벨 의존성이 요청당 1회 ContextVar에 캡처하므로, ~40개 엔드포인트 시그니처와 `api/main.py`를 건드리지 않는다.

**대안 비교**
- 쿼리파라미터 `?org_id=`: 명시적·테스트 용이·URL 공유 가능하나 40개 시그니처 수정 필요 → 변경량 과다로 기각.
- 서버 세션 상태: JWT-경량 구조와 안 맞고 과임 → 기각.

## 4. 안전장치 4종

성격이 두 종류다 — ①② 지켜야 할 코딩 규칙, ③④ 새로 추가하는 방어 코드.

1. **ADMIN 분기 안에서만 헤더를 읽는다 (규칙, 1순위).** 비-ADMIN이 `X-Org-Id`를 보내면 완전히 무시하고 `require_user_org`(자기 org)로 간다. 위반 시 수평 권한상승(IDOR)이 열린다.
2. **role은 DB 기준으로 판정 (전제).** `get_current_user`가 JWT 검증 후 DB에서 User를 로드하고, 해석기는 `user.role`(DB값)을 본다. 토큰 role claim 조작은 무력하다.
3. **헤더값 org 검증 (신규).** `X-Org-Id`를 UUID로 파싱(형식 오류 → 400)하고, `_validated_org`로 확인(§6.4). operational은 active 필수, read는 존재만.
4. **impersonation 감사/접근 로그 (신규).** 쓰기/실행은 `_AUDIT_LOG`(무거움), 전 org 조회는 경량 access log로 분리한다(§6.5).

## 5. 구현 순서 (Phase 0 → 2)

1. **Phase 0 — 엔드포인트 매트릭스 (Phase 1 선행 필수).** management의 org 해석 호출부 ~40곳을 표로 분류한다(§6.1). "해석기 한 곳만 바꾸면 전부 동작"은 **성립하지 않으며**, 매트릭스로 각 엔드포인트의 처리를 확정해야 한다.
2. **Phase 1 — 핵심 축.** ContextVar+의존성, `_require_org_id` 교체, `_validated_org`, 감사 로그, 매트릭스에서 식별된 예외 엔드포인트 개별 처리, Phase 1 테스트. → admin이 org 선택 시 operational·org-필터 엔드포인트 동작(live Meta 포함).
3. **Phase 2 — DB 전체뷰.** `_scope_org_or_all`, 대상 리스트 엔드포인트 pagination·정렬·상한 포함 적용, 전 org 조회 access log, Phase 2 테스트. → 무헤더 admin이 DB 전 org 조회.
4. **프론트** org 선택기 + `request()` 헤더 부착(management 경로 한정) + 로그아웃 clear.

## 6. 컴포넌트

### 6.1 Phase 0 — 엔드포인트 매트릭스

각 org 해석 호출부를 세 부류로 분류하고 처리를 정한다.

| 부류 | 판별 | 처리 |
|---|---|---|
| (a) 순수 org-scope | `org_id`만으로 데이터 스코프 | 새 `_require_org_id`(operational) 또는 `_scope_org_or_all`(리스트) 적용 |
| (b) user 신원 병행 | `approve(..., str(user.id))`(2637/2760/2941), `updated_by = user.id`(1633) 등 현재 유저 id를 **기록**에 씀 | 그대로 둔다 — impersonation 시 기록 actor가 admin.id인 것이 오히려 정확(안전장치 ④와 정합). 쓰기 audit에 `on_behalf_of_org` 병기 |
| (c) 멤버십 직접 해석 | `select(OrganizationMember...).where(user_id == user.id)`로 org를 구함 (예: `meta_connect` 3254) | **개별 결정.** `meta_connect`(org 소유자가 자기 Meta 연결)는 impersonation 의미가 달라 admin 대리 연결을 **허용하지 않는다**(현행 멤버십 기반 유지, admin은 409). 그 외 멤버십-해석 조회는 새 해석기로 라우팅 |

산출물: 호출부별 {부류, 처리, 비고} 표. 이 표가 Phase 1/2의 편집 대상 목록이 된다.

### 6.2 Phase 1 — 헤더 캡처 (ContextVar + yield 의존성)

전부 `management.py` 안에서 처리(공통부 변경 0). ContextVar는 **요청 종료 시 반드시 reset**하여 background task·테스트·예외 흐름에서의 누수를 막는다.

```python
_selected_org_ctx: ContextVar[str | None] = ContextVar("selected_org", default=None)

async def _capture_selected_org(x_org_id: str | None = Header(None, alias="X-Org-Id")):
    token = _selected_org_ctx.set(x_org_id)
    try:
        yield
    finally:
        _selected_org_ctx.reset(token)

router = APIRouter(dependencies=[Depends(_capture_selected_org)])
```

**격리 규칙(명문화)** `_require_org_id`/`_scope_org_or_all`는 **이 라우터 의존성이 실행된 요청 스코프 안에서만** 호출한다. 라우터 밖(background task·CLI 스크립트·`scheduler.py` 등)에서는 org를 인자로 명시 전달하고 이 해석기를 쓰지 않는다.

### 6.3 Phase 1 — org 해석기 교체 (`_require_org_id`, 현재 2423번 줄 별칭)

```python
async def _require_org_id(user, db) -> UUID:
    if user.role.upper() == "ADMIN":
        sel = _selected_org_ctx.get()
        if not sel:
            raise HTTPException(400, "관리자는 조직을 선택하세요 (X-Org-Id 헤더).")
        return await _validated_org(db, sel, require_active=True)   # operational (§6.4)
    return await require_user_org(user, db)
```

매트릭스 (a) 부류 operational 호출부가 이 함수를 그대로 재사용한다.

### 6.4 Phase 1 — org 검증 (`_validated_org`, 정책 플래그 1개)

operational impersonation과 read 필터는 정책이 다르다 — **operational은 active org만**(비활성 org에 게재·과금하면 안 됨), **read는 비활성 org도 조회 허용**(admin 감독 목적). 별도 함수 두 개 대신 `require_active` 플래그 하나로 구분한다.

`Organization` 모델엔 `status`(기본 `"ACTIVE"`)만 있고 soft-delete/archived 필드는 없다(models.py 99). enum이 없으므로 대소문자 방어 비교(`str(status).upper()`)를 쓴다.

```python
async def _validated_org(db, sel: str, *, require_active: bool) -> UUID:
    try:
        org_uuid = UUID(sel)
    except ValueError:
        raise HTTPException(400, "X-Org-Id 형식 오류")
    status = await db.scalar(select(Organization.status).where(Organization.id == org_uuid))
    if status is None:
        raise HTTPException(404, "선택한 조직을 찾을 수 없습니다.")
    if require_active and str(status).upper() != "ACTIVE":
        raise HTTPException(409, "비활성 조직은 선택할 수 없습니다.")
    return org_uuid
```

**정책 일관성** read는 특정 org·전 org 모두에서 inactive를 포함/허용한다(전 org 뷰에서 inactive를 숨기지 않는다 — admin 감독 기능 보존). Meta 토큰 없는 org를 operational로 impersonate하면 하류 `_require_reader`가 기존 409(`_NOT_CONNECTED_MSG`)로 막으므로 여기서 별도 처리하지 않는다.

### 6.5 Phase 1 — 감사/접근 로그

- **쓰기/실행** (activate/approve/게재 등): 기존 `_AUDIT_LOG`에 `{actor: admin.id, on_behalf_of_org: org_uuid, action}` 기록. 정확한 삽입 지점은 매트릭스 (b)에서 확정.
- **전 org 조회** (§6.6): 무거운 audit 대신 **경량 access log** 이벤트 1건. metadata = `{actor, endpoint, limit, offset, 주요 filter}`. (correlation/request-id 인프라가 없으므로 request_id는 넣지 않는다 — 없는 인프라를 위해 신설하지 않음.)

### 6.6 Phase 2 — DB 전체뷰 (`_scope_org_or_all` + 별도 쿼리 분기)

```python
async def _scope_org_or_all(user, db) -> UUID | None:
    """리스트/집계용 3-값 스코프.
    비-ADMIN → 자기 org / ADMIN+헤더 → 그 org(read, inactive 허용) / ADMIN+무헤더 → None(전체)."""
    if user.role.upper() == "ADMIN":
        sel = _selected_org_ctx.get()
        return await _validated_org(db, sel, require_active=False) if sel else None
    return await require_user_org(user, db)
```

**쿼리 적용 규칙** `None`(전체)과 특정 org를 **OR-NULL 한 쿼리로 합치지 않고 분기**한다(인덱스 보존).

- 특정 org: `WHERE organization_id = :org ... ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset`
- 전체(admin): `... ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset`
- 공통: **pagination**(limit/offset, 기본 limit=50, **최대 상한 200**), **안정 정렬**(`created_at DESC, id DESC` — 테이블 PK를 최종 tie-breaker. `organization_id`는 행 단위 유일하지 않아 tie-break로 부적합), 응답에 **`organization_id` + `organization_name`** 포함(전 org 뷰에서 어느 org 건지 식별).

**대상 선별** 순수 DB 읽기만. 후보: `created_campaigns`(498, 현재 무인증이라 별도 점검), KPI override 리스트(1583), budget status 조회 등. **live Meta reader를 타는 조회는 제외**(impersonate로 처리). 정확한 목록은 Phase 0 매트릭스에서 확정.

**operational 엔드포인트는 불변** activate/approve/link-simulation 등은 Phase 1의 `_require_org_id`(admin은 반드시 org 선택) 유지 — 전 org 대상 쓰기는 위험하므로 의도적으로 단일 org 강제.

### 6.7 CORS

`api/main.py`의 CORS는 `allow_headers=["*"]`(165번 줄)라 `X-Org-Id`가 자동 허용된다(무수정 확인 완료).

## 7. 데이터 흐름 (요청 1건)

1. 프론트 `request()`가 `Authorization: Bearer <jwt>` + (management 경로 & admin org 선택 시) `X-Org-Id: <uuid>` 부착.
2. 라우터 의존성 `_capture_selected_org`가 헤더를 ContextVar에 저장(요청 종료 시 reset).
3. `get_current_user`가 JWT 검증 → DB User 로드(role은 DB값).
4. 핸들러가 `_require_org_id`(operational) 또는 `_scope_org_or_all`(리스트) 호출 → org 스코프 확정.
5. 그 org로 쿼리/Meta reader·writer 동작. 쓰기/실행이면 audit, 전 org 조회면 access log.

## 8. 에러처리 (일관된 코드)

| 상황 | 응답 |
|---|---|
| 비-ADMIN 미소속 | 409 (기존 유지) |
| ADMIN operational + org 미선택 | 400 "관리자는 조직을 선택하세요" |
| `X-Org-Id` 형식 오류 | 400 |
| `X-Org-Id` org 실존 안 함 | 404 |
| ADMIN operational + 비활성 org(status≠ACTIVE) | 409 |
| ADMIN read + 비활성 org | 정상(조회 허용) |
| 비-ADMIN이 `X-Org-Id` 보냄 | 무시(조용히 자기 org) |
| ADMIN 리스트 + 무헤더 | 에러 아님, 전 org(pagination) 반환 |
| `meta_connect` 등 (c)-owner 액션을 admin이 시도 | 409 (대리 연결 불가) |

## 9. 프론트엔드 (최소·범위 한정)

- **request() path 계약**: `request(path)`는 `` `${API_BASE}/api${path}` `` 로 조립되며 `path`는 항상 `/api` 이후의 상대경로다(절대 URL·`/api` 중복 없음). management 호출은 `/management` prefix를 쓴다(예: `/management/compare/board`).
- `frontend/src/lib/api.ts`의 중앙 `request()` 헬퍼(현재 163~167): **`path.startsWith('/management')`** 이고 **현재 유저가 admin**이며 저장된 `adminOrgId`가 있을 때만 `X-Org-Id` 헤더 추가. 전역 부착 금지(다른 라우터로 impersonation 힌트 누출 방지). URL 정규화 배선은 불필요(입력이 항상 상대경로라는 계약으로 충분).
- admin org 선택기: `GET /api/admin/organizations`(이미 존재)로 목록 → 선택값 저장, "전체" = 미설정. 관리 화면 상단 드롭다운.
- **stale state 방지**: 로그아웃 시 `adminOrgId` clear. 저장은 sessionStorage 또는 user-id별 key 중 택1(구현 시 확정). role이 admin이 아닐 땐 set/read 안 함.

## 10. 테스트 (`test/backend/management`)

- **IDOR 회귀 (핵심)**: 비-ADMIN이 `X-Org-Id`로 남의 org를 못 봄(무시, 자기 org만).
- role은 DB 기준(토큰 role 조작 무력) — 가능하면.
- admin+무헤더 operational → 400 / 형식오류 → 400 / 실존X → 404 / 비활성 org(operational) → 409.
- admin read + 비활성 org(헤더) → 정상 조회.
- admin+`X-Org-Id` → 그 org로 동작, 쓰기 시 audit(`on_behalf_of_org`) 기록.
- admin+무헤더 리스트 → 전 org(pagination·`created_at DESC, id DESC`·상한 200, 응답에 org 식별자) / admin+헤더 리스트 → 그 org / 비-admin 리스트 → 자기 org.
- `meta_connect` 등 (c)-owner 액션: admin 대리 시도 → 409.
- 비-admin 기존 동작 불변(미소속 409) 회귀.
- ContextVar 격리: 연속 요청/예외 흐름에서 org 힌트 누수 없음.
