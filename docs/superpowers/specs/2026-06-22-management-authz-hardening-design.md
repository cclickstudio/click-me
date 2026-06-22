# 매니지먼트 상태 변경 엔드포인트 인증·소유권 강화 (Vuln 3) — 설계

> 작성일 2026-06-22 · 작성자 🅱(boeun) · 브랜치 `feat/management-boeun`
> 출처: 2026-06-22 보안 리뷰 Vuln 3(미인증 권한 엔드포인트) / Vuln 2(OAuth state)는 🅰 핸드오프.

## 1. 배경 / 문제

`backend/api/routers/management.py`의 상태 변경 엔드포인트 대부분이 `get_current_user` 의존성 없이
공개돼 있다. `tenant_id`/`ad_account_id`는 데모 상수(`TENANT_ID`, `_DEMO_AD_ACCOUNT`) 또는 요청
body/query에서 오며, 호출자가 해당 테넌트/조직 소속인지 검증하지 않는다. 결과적으로 미인증 호출자가
캠페인 생성·삭제·활성화·일시중지, 크레딧 정산(`/sync`), 예산 한도, 에스컬레이션 사다리 상태를 조작할 수
있고, 실모드(`use_mock=False` + `management_execution_mode=live`)에서는 실제 Meta 변경/실집행까지 닿는다.

`/sync`는 `org_id`를 쿼리 파라미터(공격자 통제)로 받아 타 조직 크레딧을 차감할 수 있는 cross-tenant
정산 변조가 가능하다.

## 2. 범위 / 비목표

### 고칠 엔드포인트 (🅱 소유, 모두 `management.py`)

| # | 엔드포인트 | 현재 tenant/org 출처 | 조치 |
|---|---|---|---|
| 1 | `POST /execute` (305) | `body.proposal.tenant_id` | 인증 + `proposal.tenant_id == 내 org` 검증 |
| 2 | `POST /regenerate` (227) | `body`/`TENANT_ID` | 인증 + tenant를 내 org로 강제 |
| 3 | `POST /campaigns/create-proposal` (996) | `TENANT_ID` | 인증 + proposal.tenant = 내 org |
| 4 | `POST /campaign-proposals/from-candidate` (1084) | body/`TENANT_ID` | 인증 + proposal.tenant = 내 org |
| 5 | `POST /ad-image` (965) | — | 인증 |
| 6 | `POST /campaigns/{id}/activate` (1102) | `TENANT_ID`, `_resolve_ad_account()` | 인증 + 캠페인 소유권 검증 |
| 7 | `POST /campaigns/{id}/pause` (1269) | `TENANT_ID` | 인증 + 소유권 검증 |
| 8 | `DELETE /campaigns/{id}` (862) | — | 인증 + 소유권 검증 |
| 9 | `GET /campaigns/{id}/sync` (1231) | **`org_id` 쿼리(공격자 통제)** | 인증 + org를 쿼리 대신 JWT에서 도출 |
| 10 | `POST /budget/limit` (1466) | `TENANT_ID` | 인증 + 내 org tenant |
| 11 | `POST /re-evaluate` (1637) | `body.tenant_id` | 인증 + tenant를 내 org로 강제 |
| 12 | `POST /re-evaluate/executed` (1652) | `body.run_id` | 인증 + run의 `tenant_id == 내 org` 검증 (3.5) |
| 13 | `POST /re-evaluate/rejected` (1661) | `body.run_id` | 인증 + run의 `tenant_id == 내 org` 검증 (3.5) |

### 비목표

- `/approve`(🅰 승인 두뇌), OAuth `/meta/connect`·`/meta/callback`(🅰) — **수정하지 않음**.
- 읽기 전용 GET(`/campaigns/{id}/delivery-status` 등 단순 조회) — 이번 범위 밖.
- DB 모델·Alembic(`core/models.py`) 변경 — 공통부라 미수정. 소유권 검증은 기존 `CreatedCampaign.tenant_id`로 가능.

## 3. 설계

### 3.1 공용 헬퍼

기존 `_resolve_org_id`(None 반환 유지)에 더해 `management.py`에 두 헬퍼를 추가한다.

```python
async def _require_org_id(user, db) -> UUID:
    org_id = await _resolve_org_id(user, db)
    if org_id is None:
        raise HTTPException(409, "소속 조직이 없습니다 — 조직 연결 후 시도하세요.")
    return org_id

async def _require_owned_campaign(db, org_id, campaign_id) -> CreatedCampaign | None:
    """DB 적재 캠페인은 tenant 소유 검증. DB 행 없음은 mock/demo fixture로 확인된 경우에만 None 허용."""
```

**엔드포인트별 의존성 주입(라우터 레벨 금지)** — 라우터 전체에 의존성을 걸면 같은 파일의 🅰 엔드포인트
(`/approve`, detection GET)까지 인증이 묶여 소유권 규칙을 위반한다. 따라서 🅱 핸들러 시그니처에만
`user: User = Depends(get_current_user)` 와 (필요 시) `db: AsyncSession = Depends(get_db)` 를 추가한다.

### 3.2 tenant / ad_account 도출

- `tenant_id`는 `str(org_id)`로 통일한다 (`models.py` 주석 `tenant_id = organization_id` 근거).
- `ad_account_id`는 org의 `MetaConnection`(org당 1개)에서 도출한다.
  - **mock 모드** — 연결이 없으면 기존 `_resolve_ad_account()`(데모 계정) 폴백 허용.
  - **live 모드(`use_mock=False`)** — `MetaConnection`이 없으면 **데모 계정으로 폴백 금지**.
    409/412로 fail-closed(연결 후 시도). 미연결 org의 작업이 데모 계정으로 새는 것을 막는다.
- 제안 생산 경로(create-proposal, from-candidate, activate, pause)는 `TENANT_ID` 상수 대신
  `str(org_id)`로 `ActionProposal.tenant_id`를 채운다.
- `approve(proposal, "user_demo", …)`의 승인자 ID를 `str(user.id)`로 교체(감사 정확도↑).

### 3.3 Executor 상호작용 (이중 차단)

`/execute`에서 `body.proposal.tenant_id != str(org_id)`이면 즉시 403으로 거부한다. 이는 executor의
기존 `TENANT_MISMATCH`(승인↔제안 재검증)와 맞물려 타 테넌트 제안 실행을 라우터·executor 두 지점에서
이중 차단한다. executor 코드는 변경하지 않는다.

### 3.4 mock/데모 엣지 케이스

`use_mock=True`일 때 일부 캠페인은 `_CAMPAIGNS_DEMO` 공유 픽스처에서 오므로 `CreatedCampaign` 행이
없을 수 있다. 단, **DB 행이 없다는 사실만으로 소유권 검증을 통과시키지 않는다.**

소유권 검증은 다음과 같이 분기한다.

- **DB 적재 캠페인** → `tenant_id == str(org_id)` 검증, 불일치 시 **403**.
- **DB 행 없음 + `use_mock=True` + `campaign_id`가 `_CAMPAIGNS_DEMO`에 존재** → mock/demo fixture로
  보고 인증된 사용자에게만 통과시킨다.
- **DB 행 없음 + 그 외** → 소유권을 확인할 수 없으므로 **404**(또는 **403**)으로 실패 처리한다.

즉, mock/demo 예외는 데모 fixture로 확인된 캠페인에만 제한하고, "행 없음" 자체를 통과 조건으로 삼지
않는다.

> 운영 메모(코드 아님): 실모드 시연 시 `created_campaigns` 행이 로그인 org의 tenant로 찍히도록 데모
> 시드를 정렬해야 소유권 검증이 의미를 가진다. 데이터 시드 이슈로 별도 관리.

### 3.5 escalation run 소유 검증 (12, 13)

`run_id`가 추측하기 어렵다는 점(UUID)을 **권한 검증의 근거로 삼지 않는다**(불투명성 ≠ 권한). 대신
가능한 경우 **run 생성 시점에 `tenant_id`를 함께 저장**하고, `/re-evaluate/executed|rejected`에서
해당 run의 `tenant_id == str(org_id)`를 **반드시 비교**한다(불일치 403).

`EscalationRun`은 이미 `tenant_id`를 보관하고(escalation.py:78, 생성 시 171행 적재) `get_by_run_id`로
읽을 수 있다. 따라서 **DB/모델 변경 없이** executed/rejected 핸들러에서 run을 조회해
`run.tenant_id == str(org_id)`를 비교하면 된다(불일치 403). `re_evaluate`(11)가 tenant를 내 org로
강제하므로 개시되는 run의 tenant도 자동으로 내 org가 된다. 인증 게이트만 두는 절충은 채택하지 않는다.

## 4. Vuln 2 핸드오프 (🅰)

`docs/management/oauth-state-csrf-handoff.md`를 작성해 🅰에게 전달한다. 코드는 건드리지 않는다.

- **문제** — `/meta/connect`가 만든 `state="{org}:{nonce}"`의 nonce가 서버에 저장되지 않음.
  `/meta/callback`은 미인증이며 `state`에서 파싱한 org를 그대로 신뢰(`management.py:1602`).
- **권장 수정** — connect 시점에 인증 사용자/org에 바인딩된 single-use·TTL nonce를 서버에 저장,
  callback에서 조회·소진 검증 후 **저장된 레코드의 org**를 사용. raw `state`의 org 신뢰 금지.
- **영향** — OAuth CSRF/토큰 주입, 임의 org의 Meta 연결 토큰 덮어쓰기(자격 탈취).

## 5. 테스트

`tests/management/`에 기존 fake-JWT 패턴을 따라 엔드포인트별로 추가/보강한다.

- 토큰 없음 → **401**
- 소속 org 없음 → **409**
- 타 org 캠페인 대상 delete/activate/pause/sync → **403**
- DB 행 없음 + `_CAMPAIGNS_DEMO`에 없는 임의 `campaign_id` → **404/403**(행 없음만으로 통과 금지)
- `use_mock=True` + `_CAMPAIGNS_DEMO`에 존재하는 campaign_id → 인증 사용자에게 통과
- `/execute`에서 `proposal.tenant_id ≠ 내 org` → **403**
- `/sync`가 쿼리 `org_id`를 무시하고 JWT org로 정산 → 검증
- 정상(내 org) → 기존 동작/200 유지

## 6. 코디네이션 / 리스크

- **프론트 Authorization 헤더 누락 가능성** — 이 엔드포인트들이 인증 필수가 되면, 프론트가 호출 시
  Authorization 헤더를 싣지 않으면 일괄 401이 난다. `AuthProvider`/`lib/api.ts` 호출부가 Bearer
  토큰을 첨부하는지 점검이 후속으로 따라온다(이번 백엔드 범위 밖, 별도 메모).
- **mock/demo와 live의 소유권 검증 분기** — 같은 엔드포인트가 모드에 따라 다르게 동작한다(3.4).
  mock은 공유 픽스처라 행이 없어 인증+org까지만, live는 `CreatedCampaign.tenant_id`로 엄격 검증.
  두 경로가 갈리는 만큼 테스트도 모드별로 나눠 검증한다.
- **live 모드에서 `MetaConnection` 없을 때 fallback 금지** — 미연결 org가 데모 광고계정으로 새지
  않도록 live는 fail-closed(3.2). mock 폴백 로직을 live에 재사용하지 않도록 분기를 명확히 둔다.
- **`/sync`는 GET인데 정산(상태 변경)을 한다** — 크레딧 차감이라는 부수효과를 가진 GET은 의미상
  부적절하다(브라우저 prefetch·캐시·재시도로 의도치 않은 정산 위험). 단, 인증을 Bearer 토큰으로
  강제하면 ambient-credential 기반 CSRF는 차단된다. 이번 작업에서는 **인증 + org 도출**을 우선
  적용하고, GET→POST 메서드 변경은 프론트 호출부 영향이 있어 후속 항목으로 분리한다.
- **A/B 공유 파일 충돌 위험** — `management.py`는 A/B가 함께 쓰는 단일 파일이라 동시 수정 시 머지
  충돌 가능성이 있다. **🅱 핸들러 + 신규 헬퍼만** 수정하고 🅰 엔드포인트(`/approve`, OAuth, detection)는
  무변경. 작은 단독 커밋으로 분리하고 🅰와 작업 시점을 조율한다.
- `core/models.py`·Alembic 무변경 — 공통부 사전 공지 규칙 회피. 3.5의 run tenant 비교는
  `EscalationRun.tenant_id`(기존 필드) 재사용이라 스키마 변경이 필요 없다.

## 7. 완료 기준

1. 13개 엔드포인트 전부 미인증 호출 시 401.
2. DB 적재 캠페인에 대한 cross-tenant delete/activate/pause/sync 403.
3. `/execute` cross-tenant 제안 실행 403.
4. `/sync`가 쿼리 `org_id`를 신뢰하지 않음.
5. 기존 mock 데모 흐름·테스트 무회귀(`uv run pytest tests/management/ -v`).
6. Vuln 2 핸드오프 문서 커밋.
