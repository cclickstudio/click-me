# management org 해석 엔드포인트 매트릭스 (Phase 0)

> Task 1 산출물 — `backend/api/routers/management.py`의 org 해석 호출부를 부류(a/b/c)로 분류하고
> Phase 1/2의 편집 대상을 확정한다. **이 표가 Phase 1/2 편집 체크리스트이자 Task 6 치환 정적 대조의 기준.**
>
> 관련: spec `docs/superpowers/specs/2026-07-01-admin-management-org-scope-design.md`,
> plan `docs/superpowers/plans/2026-07-01-admin-management-org-scope.md`.

## 수집 명령 (Step 1)

```
cd backend && grep -nE '_require_org_id|_resolve_org_id|user_org_id|OrganizationMember.*user_id == user\.id|require_user_org' api/routers/management.py
```

grep 히트는 **org 해석 호출부만** 잡는다. 부류 (b)의 신원 기록 마커(`approve(..., str(user.id))` 2637/2760/2941,
`updated_by = user.id` 1633)는 이 grep에 **안 걸리며**, 각 엔드포인트의 org 해석 행 아래 주석으로 병기한다.

## 범례 / 판정 규칙

- **부류** — (a) 순수 org-scope · (b) user 신원 병행(현재 유저 id를 기록에 씀) · (c) 멤버십 직접 해석.
- **impersonate-only** — live Meta reader/writer(`_require_reader`/`_require_writer`/`_request_*` 의존성/`reader=`)를 타는 조회·실행.
  전 org(all-org) 대상에서 제외하고 admin은 org 선택(§34 spec)으로만 처리.
- **write여부 판정 규칙(본 매트릭스 채택)** — 해석된 org에 대해 **실행/영속/과금/외부(Meta) 쓰기·자산 업로드·상태 변이**를
  수행하면 `Y`. 순수 조회·표시전용(display-only) 제안 생산은 `N`. `write=Y & operational` 행이 Task 6에서
  `_require_org_id` → `_require_org_id_write(user, db, action=...)`로 치환되는 대상(체크박스).
- **치환완료 체크박스** — Task 6 Step 4에서 치환 후 채운다. `_scope_org_or_all` 대상은 치환 대상이 아님(해당 없음).
- **감사(audit) 범위(리뷰 확정)** — impersonation 감사는 **Meta/과금/외부 쓰기·자산 변이**만 대상. 내부 job/store 생성·display-only 제안·무과금 preview는 제외. 감사는 **시도 시점 기록**(`outcome="attempted"`)이라, mock/no-op·501 차단이어도 과기록 아님.

## 정의·import 행 (호출부 아님 — 참고용)

| 라인 | 내용 | 비고 |
|---|---|---|
| 30–31 | `require_user_org`, `user_org_id` import | core.auth 공용 |
| 1578 | `_resolve_org_id = user_org_id` (별칭 정의) | 없으면 None. list/put kpi-overrides가 사용 |
| 2423 | `_require_org_id = require_user_org` (별칭 정의) | 없으면 409. Task 4에서 role 인지 async 함수로 교체 |

## 분류표 (호출부 = grep 히트 순)

| 엔드포인트 (메서드 경로) | 라인 | 부류 | 처리 | write | 치환완료 |
|---|---|---|---|---|---|
| `_request_reader` (공용 reader 의존성) | 174 | a | operational READ, **impersonate-only**(live reader). `Depends(_request_reader)` 엔드포인트 전부를 대리 — 아래 "reader 의존성 소비 엔드포인트" 목록 | N | — |
| `_request_writer` (공용 writer 의존성) | 186 | a | operational, **impersonate-only**. `ad_preview`(무과금 no-op preview)만 소비 — 실 write·과금·업로드 없어 **감사 제외**. 공용 dependency엔 action 미주입(원 상태 유지, 리뷰 #2 반영) | N | — |
| POST `/regenerate` → `regenerate` | 374 | a | operational READ(후보/제안 생산, Meta 쓰기·과금 없음). `_require_ad_account`만 참조 | N | — |
| POST `/execute` → `execute` | 466 | a | operational **WRITE** — 승인 액션 실행(단일 지출 경로), 조건부 `_require_writer`(479) | Y | - [ ] |
| POST `/regenerate/jobs` → `start_regen_job` | 570 | a | operational — 재생성 job 시작(내부 job store). Meta/과금 무관. **write=N로 분류(아래 애매행 참고)** | N | — |
| GET `/regenerate/jobs/{job_id}` → `get_regen_job` | 597 | a | operational READ(job 폴링) | N | — |
| POST `/regenerate/jobs/{job_id}/select` → `select_regen_job` | 619 | a | operational — job 선택 확정(내부 job store 변이). **write=N로 분류(아래 애매행 참고)** | N | — |
| GET `/execution/history` → `execution_history_endpoint` | 640 | a | operational READ(감사 이력) | N | — |
| GET `/compare/before-after` → `compare_before_after` | 739 | a | operational READ, **impersonate-only**(`reader.list_campaigns`). org는 링크 매핑용, live·mock 분기 | N | — |
| POST `/campaigns/{id}/link-simulation` → `link_simulation` | 799 | a | operational **WRITE** — `CreatedCampaign` DB 영속(생성/업서트) | Y | - [ ] |
| GET `/calibration/anchors` → `calibration_anchors` | 895 | a | operational READ, **impersonate-only**(`reader.list_campaigns`) | N | — |
| GET `/campaigns` → `list_campaigns` | 1435 | a | operational READ, **impersonate-only**(`_resolve_reader`→`_list_campaigns_real`) | N | — |
| GET `/kpi-overrides` → `list_kpi_overrides` | 1587 | a | **Phase 2 = impersonate-only**(Task 9). 순수 DB read. `_resolve_org_id`→`_scope_org_or_all`. all-org는 campaign_id 키 충돌로 제외 | N | — |
| PUT `/campaigns/{id}/kpi-override` → `put_kpi_override` | 1614 | a+b | DB WRITE + `updated_by = user.id`(1633, b). **결정(리뷰 #1): admin 편집 허용** — `_resolve_org_id` → `_require_org_id_write(action="kpi_override")` 치환(admin 선택 org 저장 + 감사). 비-admin은 미소속 409 동일. **Task 9에서 GET과 함께 처리** | Y | - [ ] |
| DELETE `/campaigns/{id}` → `delete_campaign` | 1648 | a | operational **WRITE** — 캠페인 삭제 + `_require_writer`(1650) + 소프트삭제 | Y | - [ ] |
| GET `/campaigns/{id}` → `get_campaign` | 1682 | a | operational READ, **impersonate-only**(`_require_reader`→`_get_campaign_real`) | N | — |
| POST `/ad-image` → `upload_ad_image` | 1790 | a | operational **WRITE** — Meta `/adimages` 자산 업로드. org 해석이 `_require_writer(db, await _require_org_id(...))`로 중첩 | Y | - [ ] |
| POST `/campaigns/create-proposal` → `create_campaign_proposal` | 1824 | a | operational READ — 제안 패키징. `_require_reader`(1826)로 정책만 조회, writer·업로드 없음. **impersonate-only**(live reader) | N | — |
| POST `/campaign-proposals/from-candidate` → `from_candidate` | 1931 | a | operational **WRITE** — `_require_writer`(1949) + 후보 크리에이티브 Meta 업로드. 제안 생산이나 자산 쓰기 발생 | Y | - [ ] |
| POST `/campaigns/{id}/replace-creative-proposal` → `replace_creative_proposal` | 2051 | a | operational **WRITE** — `_require_writer`(2088) 획득 + upload(비-sending은 no-op/합성해시). **LIVE(sending)는 501 차단(B-1 mock 범위)**. writer 자격 접근 기준 write=Y | Y | - [ ] |
| POST `/campaign-proposals/from-simulation` → `from_simulation` | 2234 | a | operational **WRITE** — `_require_writer`(2286) + 시뮬 크리에이티브 Meta 업로드 | Y | - [ ] |
| POST `/campaigns/{id}/activate` → `activate_campaign` | 2530 | a (+b) | operational **WRITE** — 게재 시작(spend_cap·ACTIVE), `_require_writer`(2593). (b) `approve(..., str(user.id))`(2637) 로직 불변 | Y | - [ ] |
| GET `/campaigns/{id}/sync` → `sync_campaign` | 2693 | a | 폴링 GET, **실 크레딧 차감 시에만** 과금 변이. **blanket seam 제외(리뷰 #3)** — org는 `_require_org_id`로 해석, 실 차감 분기에서만 `_emit_impersonation_audit(action="sync_credit_adjust")` 타깃 기록 | Y(타깃) | 별도 |
| POST `/campaigns/{id}/pause` → `pause_campaign` | 2736 | a (+b) | operational **WRITE** — 즉시 일시중지(게재·과금 중단) 실행. (b) `approve(..., str(user.id))`(2760) 로직 불변 | Y | - [ ] |
| POST `/campaigns/{id}/budget-proposal` → `budget_proposal` | 2895 | a | operational READ — display-only 제안. `_require_reader`(2898)로 현재 예산 조회. **impersonate-only** | N | — |
| POST `/campaigns/{id}/budget-commit` → `budget_commit` | 2925 | a (+b) | operational **WRITE** — 예산 변경 실행, 조건부 `_require_writer`(2946). (b) `approve(..., str(user.id))`(2941) 로직 불변 | Y | - [ ] |
| GET `/budget` → `get_budget` | 3126 | a | operational READ, **impersonate-only** — `reader=Depends(_request_reader)`(3119) + `_budget_status(reader, ...)`는 live reader 사용. (spec §6.6 all-org 후보였으나 **live reader 확인 → impersonate-only로 확정**) | N | — |
| POST `/budget/limit` → `set_budget_limit` | 3141 | a | operational **WRITE** — org 예산 한도 설정(`_BUDGET.set_limit`) + `_require_reader`(3146) | Y | - [ ] |
| POST `/re-evaluate` → `re_evaluate` | 3194 | a | operational — 에스컬레이션 사다리 재평가(store 변이·제안 생성), `_require_ad_account`. Meta 지출은 없음. **애매(아래 참고), write=Y로 분류** | Y? | - [ ] |
| POST `/re-evaluate/executed` → `mark_rung_executed` | 3215 | a | operational **WRITE** — 사다리 run 상태 변이(`on_executed`) | Y | - [ ] |
| POST `/re-evaluate/rejected` → `mark_rung_rejected` | 3229 | a | operational **WRITE** — 사다리 run 상태 변이(`on_rejected`) | Y | - [ ] |
| GET `/meta/connect` → `meta_connect` | 3255 | **c** | **멤버십 직접 해석** — `select(OrganizationMember.organization_id).where(user_id == user.id)`. org 소유자 Meta 연결이라 admin 대리 불가. 현행 유지, admin은 멤버십 없어 409 (Task 5 명문화) | N | — |

`Y*` = write지만 `_require_org_id` 치환 세트에 없음(별도 `_resolve_org_id` 사용). `Y?` = write로 분류하되 애매행(아래).

### reader 의존성만 쓰는 엔드포인트 (org 해석 = 174행 경유, 자체 grep 히트 없음)

전부 부류 (a) · operational READ · **impersonate-only**(live reader). 174행 치환 시 일괄 적용:

| 엔드포인트 | 라인(reader=) |
|---|---|
| GET `/anomaly/scan` → `anomaly_scan` | 295 |
| GET `/campaigns/{id}/targeting` → `get_campaign_targeting` | 774 |
| GET `/campaigns/{id}/creative-image` → `proxy_creative_image` | 847 |
| GET `/campaigns/{id}/outcome` → `get_campaign_outcome` | 1526 |
| GET `/campaigns/{id}/platforms` → `get_campaign_platforms` | 1541 |
| GET `/campaigns/{id}/demographics` → `get_campaign_demographics` | 1551 |
| GET `/campaigns/{id}/creatives` → `get_campaign_creatives` | 1561 |
| GET `/campaign-policy` → `campaign_policy` | 1774 |
| GET `/campaigns/{id}/delivery-status` → `delivery_status` | 2661 |

`Depends(_request_writer)` 소비: POST `/ad-preview` → `ad_preview`(1806) — 186행 경유(무과금 preview지만 writer 자격 획득).

## Phase 2 대상 (순수 DB read 리스트/집계 — `_scope_org_or_all`)

| 엔드포인트 | 라인 | 처리 | Task |
|---|---|---|---|
| GET `/created-campaigns` → `created_campaigns` | 497 | **all-org**. **현재 무인증**(`db`만, org 해석 없음 → grep 미히트)으로 전 org 노출 = 테넌트 누출. 인증+`_scope_org_or_all`+pagination로 수정 | Task 8 |
| GET `/kpi-overrides` → `list_kpi_overrides` | 1581 | **impersonate-only**(all-org는 campaign_id 키 충돌·shape 파손, YAGNI). 무헤더 admin → 빈 결과 | Task 9 |

`/compare*`·`/budget` 검토 결과: `/compare`(667)·`/compare/board`(680)는 org 해석 없이 항상 mock(대상 아님).
`/compare/before-after`(724)·`/budget`(3117)은 **live Meta reader 사용 → impersonate-only**(all-org 제외)로 확정.

## write=Y & operational 치환 대상 (Task 6 체크리스트 요약)

`_require_org_id`를 `_require_org_id_write(user, db, action=...)`로 치환:

- [ ] 466 `execute`
- [ ] 799 `link_simulation`
- [ ] 1614 `put_kpi_override` (리뷰 #1 — `_resolve_org_id` → write seam. Task 9에서 GET과 함께)
- [ ] 1648 `delete_campaign`
- [ ] 1790 `upload_ad_image`
- [ ] 1931 `from_candidate`
- [ ] 2051 `replace_creative_proposal` (LIVE 501 차단 상태 유의 — attempt 감사라 무방)
- [ ] 2234 `from_simulation`
- [ ] 2530 `activate_campaign`
- [ ] 2736 `pause_campaign`
- [ ] 2925 `budget_commit`
- [ ] 3141 `set_budget_limit`
- [ ] 3194 `re_evaluate`
- [ ] 3215 `mark_rung_executed`
- [ ] 3229 `mark_rung_rejected`

**blanket seam 제외(타깃 감사 별도):**
- [x] 2693 `sync_campaign` — `_require_org_id`로 해석, 실 크레딧 차감(`record_spend` 성공) 분기에서만 `_emit_impersonation_audit(action="sync_credit_adjust")` (리뷰 #3 / T6 후속 커밋 2921e5a에서 구현)

**제외(감사 대상 아님):** 186 `_request_writer`/`ad_preview`(무과금 preview, 리뷰 #2) · 570 `start_regen_job`·619 `select_regen_job`(내부 job store, 외부 토큰 미접근, 리뷰 #4).

> Task 6 named action 예시(approve/execute/activate/pause/budget_commit/link_simulation/kpi_override)는 위 목록의 핵심 부분집합.

## 애매행 — 리뷰 확정 결과

1. **`sync_campaign`(2693)** — GET 폴링, 실 크레딧 차감 시에만 과금 변이. **확정: blanket seam 제외 + 타깃 감사**(실 차감 분기에서만 `action="sync_credit_adjust"`). 매 폴링 감사 과기록 방지(리뷰 #3).
2. **`re_evaluate`(3194)** — 에스컬레이션 store 변이 + 다음 단계 제안. store 상태 변이는 외부/과금 쓰기이므로 **확정: `write=Y` 유지**(감사 대상).
3. **`start_regen_job`(570)·`select_regen_job`(619)** — 내부 job store만 변이, org Meta/과금 토큰 미접근. **확정: `write=N` 유지.** 감사 범위 = Meta/과금/외부 쓰기(범례 참고)라 내부 상태 생성은 제외(리뷰 #4).
4. **`put_kpi_override`(1614)** — **확정: admin 편집 허용**(리뷰 #1). `_resolve_org_id` → `_require_org_id_write(action="kpi_override")` 치환, Task 9에서 GET과 함께 처리. 비-admin 미소속 409 동일.
5. **`create_campaign_proposal`(1824)·`budget_proposal`(2895)** — display-only 제안(reader만, writer·업로드·영속 없음). **확정: `write=N`**(operational READ, impersonate-only).
6. **`_request_writer`(186)/`ad_preview`** — 무과금 no-op preview. **확정: 감사 제외**(리뷰 #2), 공용 dependency에 action 미주입.
