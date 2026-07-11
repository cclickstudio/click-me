# 리밸런스(transfer) 실집행 연결 설계 — REBALANCE_BUDGET 활성화

> 2026-07-11 확정. 브레인스토밍 결과 — 예산 리밸런싱(캠페인 간 이전) 제안을 승인 1건·원자 액션 1건으로 Meta 실집행까지 연결한다.

## 1. 배경 / 문제

- 리밸런스 제안(`insights.rebalance_proposal`)은 읽기 전용이며, transfer(저효율→고효율 이전) 적용은 프론트 `manage/budget` 페이지가 `budget-commit`을 **2번 순차 호출**하는 우회 구현.
- 감액 성공 후 증액 실패 시 **원복 없음** — 실돈 계정에서 총예산이 깎인 채 방치될 수 있다.
- 승인·감사가 DECREASE+INCREASE 2건으로 쪼개져 "리밸런스" 의도가 기록되지 않는다. `REBALANCE_BUDGET`(Tier 2) 정책 엔트리는 죽은 코드.
- 챗 어시스턴트는 제안 조회(`live_rebalance_proposal`)만 가능, 적용 불가. 데모는 챗에서 완결돼야 한다.

## 2. 범위

**In scope**

- `REBALANCE_BUDGET` 원자 액션 활성화(계약·정책·executor·라우터).
- 챗 적용 툴 `apply_rebalance` + 새 위젯 타입 `rebalance_action`(카드 클릭 = 승인, HITL).
- APScheduler 리밸런스 알림에 `suggested_action` 연결(알림 → 사람 승인 → 집행, 자동 집행 없음).
- 프론트 budget 페이지 transfer 브랜치를 1-call로 교체.

**Out of scope**

- 단일 캠페인 증감(kind=adjust)은 **기존 budget-commit 경로 유지** — rebalance-commit은 transfer 전용.
- 워커 자동 집행(HITL 원칙 유지, `AUTO_APPROVE_MAX_TIER=TIER_1` 불변).
- 광고세트 레벨 예산·CBO 판별(현행 캠페인 레벨 `daily_budget` 전제 유지).

## 3. 계약 / 정책 변경

- `execution/executor.py` — `SUPPORTED_ACTION_TYPES`에 `"REBALANCE_BUDGET"` 추가.
- `executor._validate`의 Tier 2 무조건 차단(현 317줄)을 Tier 3 게이트(319줄)와 동일 패턴으로 변경 — `action_tier is TIER_2 and approver_id == AUTO_APPROVER`일 때만 차단(사용자 승인은 통과). 자동승인 판정(`assistant/actions.py:43`)은 이미 TIER_2에 승인을 요구하므로 무변경.
- `contracts/policy.py:22` — `# 비활성 (7/8 스코프 제외)` 주석 제거.
- **제안 형태** — ActionProposal 1건.
  - `action_type="REBALANCE_BUDGET"`, `target_object_ids=(from_id, to_id)`.
  - `evidence_metrics={from_before_krw, from_after_krw, to_before_krw, to_after_krw, move_krw, from_name, to_name}`.
  - `max_total_spend_krw=0` — 총액 불변(Tier 2 정의와 정합, BudgetAuthority가 지출 증가로 오판하지 않게).

## 4. executor — REBALANCE_BUDGET 전용 실행 경로

`_dispatch`에만 추가하면 `_call_targets`의 타깃 순회(from/to 각 1회)로 **리밸런스가 2번 실행**되므로, `_call_targets` 초입에서 분기한다.

```
_call_targets(...):
    if proposal.action_type == "REBALANCE_BUDGET":
        return await self._call_rebalance(run, action, proposal, key)
    # 기존 순회 유지
```

**`_call_rebalance` 시퀀스** (감액 먼저 — 총예산이 순간적으로도 늘지 않게)

1. `adjust_budget(from_id, from_after_krw, f"{key}:{from_id}:dec")` — 실패 시: 아무것도 집행 안 됨 → FAILED(원인 그대로), 멱등키는 execute()가 해제 → 재시도 가능.
2. `adjust_budget(to_id, to_after_krw, f"{key}:{to_id}:inc")` — 실패 시 보상 1회:
   `adjust_budget(from_id, from_before_krw, f"{key}:{from_id}:comp")`.
3. **보상 성공** — 원복 완료지만 리밸런스는 실패. `FAILED + failure_reason=(증액 실패 원인, 비-PARTIAL)` + 스냅샷 `compensation_succeeded=true` → 기존 로직이 멱등키 해제 → 재승인 후 재시도 가능.
4. **보상 실패** — `FAILED + PARTIAL_FAILURE` + 스냅샷 `compensation_failed=true` + 수동 복구 안내(from 캠페인·원래 예산 명시) → 기존 P5/게이트 #7이 결과를 박제하고 같은 approval 재집행을 차단. `executor.partial_failure` 감사 이벤트 기록.
5. 두 다리 모두 성공 — SUCCESS, 스냅샷에 양쪽 응답.

재시도(`_call_with_retry`의 TIMEOUT/RATE_LIMITED 백오프)는 각 다리 호출에 그대로 적용한다. Writer는 무변경 — 기존 `adjust_budget` 2회 재사용.

## 5. 라우터 — `POST /api/management/budget/rebalance-commit`

budget-commit(management.py:3541)과 같은 골격. transfer 전용.

- **Request** `{from_campaign_id, to_campaign_id, from_after_krw, to_after_krw, move_krw, shown_from_before_krw, shown_to_before_krw}`.
- **검증** — 양쪽 캠페인 소유 확인, 양쪽 현재 예산 조회 후 drift 검증(표시값 ≠ 현재값이면 409, budget-commit의 `reject_shown_drift` 관례), 범위(`_MIN/_MAX_DAILY_BUDGET_KRW`)·방향(감액분=증액분=move) 검증(422/409).
- **흐름** — 제안 빌드(§3 형태) → `issue_approval`(호출 사용자 = 승인자, `_resolved_execution_mode()`) → `executor.execute` → 결과 반환(`compensation_*` 플래그 포함, 프론트 안내용 `error_message` 추출은 기존 관례).
- 성공 시 해당 캠페인들의 미해결 운영 알림 actioned 정리(기존 `_resolve_campaign_notifications` 재사용, 양쪽).

## 6. 챗 — `apply_rebalance` 툴 + `rebalance_action` 위젯

- **툴**(subagent_tools.py) — `live_rebalance_proposal`로 현재 제안 조회. kind=transfer면 `widgets.rebalance_action({from, to, move_krw, reason})` 카드 렌더. kind=adjust면 기존 `manage_campaign` 확인 카드로 안내(신규 경로 안 탐). 제안 없으면 note 문구 그대로 안내.
- **위젯**(domain/chat/widgets.py) — 새 타입 `rebalance_action`. 기존 `campaign_action`은 단일 캠페인 payload 전제라 혼용하지 않는다(분기 오염 방지).
- **승인** — 카드에서 사용자가 확인 클릭 → 프론트가 `rebalance-commit` 호출(카드 클릭 = 승인, manage_campaign 패턴 동일). 툴은 직접 집행하지 않는다.
- **등록 갱신 3곳** — ① `api/assistant/prompts.py`(70·104줄 툴 안내 문구) ② `subagent_tools.py:1356` 툴 목록 ③ `domain/management/remediation/contracts.py:13` `ALLOWED_TOOL_HINTS`에 `apply_rebalance` 추가.
- 요청 기록은 manage_campaign과 동일하게 `spawn_record_execution`(stage=request).

## 7. 스케줄러 알림 연결

`run_rebalance_report`(scheduler.py:388)의 transfer 알림에 `suggested_action`을 추가한다 — `record_automation_run`의 `suggested_action`은 문자열 파라미터이므로 `suggested_action="apply_rebalance"`를 넘기고, 제안 본문은 기존처럼 `payload.proposal`에 실린다. 홈 브리핑/챗 알림 카드에서 "적용" 진입 → §6 카드 → §5 집행. dedup_key·24h 주기·HITL 불변.

## 8. 프론트 변경

- `manage/budget/page.tsx` — `applyRebalance`의 **transfer 브랜치만** `api.management.rebalanceCommit(...)` 1-call로 교체(shown_* 양쪽 전달). adjust 브랜치는 기존 budgetCommit 유지.
- `lib/api.ts` — `rebalanceCommit` 함수 + 타입 추가.
- 챗 위젯 — `rebalance_action` 카드 컴포넌트 신규(from→to 캠페인·금액·CPC 근거 표시, 확인 시 rebalanceCommit 호출, 결과·보상 상태 표시).

## 9. 에러 처리 요약

| 상황 | 결과 | 재시도 |
| --- | --- | --- |
| drift(표시값≠현재값) | 409, 집행 진입 전 차단 | 제안 재조회 후 |
| 감액 실패 | FAILED, 멱등키 해제 | 가능 |
| 증액 실패 + 보상 성공 | FAILED + `compensation_succeeded` | 가능(재승인) |
| 증액 실패 + 보상 실패 | FAILED + PARTIAL_FAILURE + `compensation_failed` + 수동 복구 안내 | 같은 approval 차단 |
| TTL/해시/정책버전 위반 | 기존 게이트 그대로 | 새 제안 |

## 10. 테스트 계획

- **executor 단위** — ① 두 다리 성공 ② 감액 실패(멱등 해제 확인) ③ 증액 실패+보상 성공(`compensation_succeeded`, 비-PARTIAL) ④ 증액 실패+보상 실패(PARTIAL_FAILURE 박제, 같은 approval 재집행 차단) ⑤ 같은 idem_key 재호출 시 반쪽 재집행 없음(파생키 검증) ⑥ TIER_2 사용자 승인 통과 / AUTO_APPROVER 차단.
- **라우터** — drift 409, 방향·범위 422/409, 정상 흐름(mock writer).
- **프론트** — `pnpm build` 통과(수동 확인은 데모 리허설에서).
- **실계정** — `MANAGEMENT_EXECUTION_MODE=validate` (VALIDATE_ONLY, `execution_options=["validate_only"]`)로 1회 선검증 후 live 전환.

## 11. 데모 / 운영 주의

- transfer 제안은 **활성 일예산 캠페인 2개 이상**이어야 발동 — 데모 전 테스트 캠페인 1개 추가 필요.
- 현재 `.env`가 `USE_MOCK=false + MANAGEMENT_EXECUTION_MODE=live + 실 토큰`이라 승인 즉시 실예산이 변경된다. 개발·테스트 중에는 validate 모드 권장, 발표 후 dry_run 복귀(CLAUDE.md Open Issue).
- 캠페인 레벨 `daily_budget` POST는 CBO 캠페인 전제 — 현 캠페인 구성 기준 유지, 광고세트 예산 캠페인 지원은 후속.
