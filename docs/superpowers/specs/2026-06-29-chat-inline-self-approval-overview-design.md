# 챗 인라인 셀프승인 (TIER_3 카드) — 엄브렐러 설계

> **성격**: 큰 계획(umbrella). "왜·어디로·무엇을 페이즈로 쪼개나"를 고정한다. 각 페이즈의 "어떻게"는
> 페이즈별 독립 spec→plan 문서가 책임진다. 본 문서는 구현 단위가 아니다.
>
> **브랜치**: `feat/management` · **날짜**: 2026-06-29 · **선행 자산**: spec3(`2026-06-25-chat-management-execution-spec3`).
>
> **데이터 계약 권위**: `budget_basis`·`spend_horizon_days`·`estimated_daily_spend_cap_krw`는 레포(코드·docs)에
> 선례가 없다. **본 문서가 최초 계약(authoritative)** 이다.

---

## 1. 목표 상태

매니지먼트 챗에서, 라이브·실과금에 영향을 주는 조치(예산 증액·캠페인 게재 시작)를 **카드형 액션바에서 인라인으로 셀프승인·집행**한다. 
단, 정책상 위험한 조치는 **명시적 마찰(실과금 ack)** 과 **좁은 적격 조건**을 통과할 때만 허용하고,
그 외는 기존처럼 정식 승인 화면으로 보낸다. 목업(`TIER_3 인라인 셀프승인 — 카드 설계 목업`)이 목표 화면이다.

### 목업 4개 시나리오 (목표)

1. **modify_live · INCREASE_BUDGET · budget_basis=daily** — 일 예산 증액(TIER_3). **지출 증가 ack(`spend_risk`,
   reason=`increase_budget`) 1단계 후** "검토·승인 → 집행 대기 → 집행". 지출 풀어쓰기 표시("N일 기준 …").
   *(목업 ①은 ack 없음이었으나 본 설계는 증액도 ack 대상 — §6 "목업 이탈" 참조.)*
2. **start_live · ACTIVATE_CAMPAIGN** — 신규 게재·실과금 시작(TIER_3). **ack(`spend_risk`, reason=`activate_campaign`)
   체크박스 1단계 추가**, ack 완료 전 집행 차단.
3. **budget_basis=lifetime 또는 지출정보 부족** — 인라인 불가. 서버가 `unsupported_budget_basis`/`missing_spend_info`로
   막고 정식 승인 화면으로 안내(`chat.inline.blocked` 감사).
4. **집행 결과** — `success`(게재 시작) / `submitted_pending_review`(관리자 승인 대기열). 지출 풀어쓰기 동반.

---

## 2. 데이터 계약 (최초 정의)

세 필드는 진단·제안 파이프라인이 산출해 카드 섹션·`FinalizeResult`까지 흐른다. 값 출처는 Meta 진단 파이프라인
(`live_diagnosis`/proposal 빌드)이며, 본 문서가 의미·단위·결측 규칙을 고정한다.

| 필드 | 타입 | 의미 | 결측·기본 |
|---|---|---|---|
| `budget_basis` | enum `daily` \| `lifetime` \| `unknown` | 예산 해석 기준. 인라인 적격은 `daily`만(v1). | 산출 불가 시 `unknown`(= 인라인 차단 사유) |
| `spend_horizon_days` | positive int (days) | 인라인에서 지출 상한을 풀어 보여줄 기간. | **v1 서버 고정 상수 `7`** |
| `estimated_daily_spend_cap_krw` | int(KRW) \| null | **일 단위 지출 상한/환산 상한**(예측 아님). Meta 진단이 산출. | 없으면 `null`. **0으로 대체 금지** |

### 표기 주의 — "cap"의 의미

`estimated_daily_spend_cap_krw`는 **예측 지출이 아니라 일 지출 상한**이다. 풀어쓰기 표시값
`estimated_daily_spend_cap_krw × spend_horizon_days`는 **"N일 기준 예상 최대 지출 / 지출 상한"** 이다.
목업 문구("N일 기준 예상지출")를 화면에서 유지하더라도, **데이터 정의와 코드 주석은 "상한" 의미를 명기**한다.
(권장 문구: "7일 기준 예상 최대 지출" 또는 "7일 기준 지출 상한".)

### 결측 처리 원칙

`estimated_daily_spend_cap_krw == null` 또는 `budget_basis ∈ {lifetime, unknown}`이면 **인라인 풀어쓰기·셀프승인을
산출하지 않는다**. null을 0으로 메우지 않는다(0은 "상한 0"이라는 잘못된 단정이 된다). 이 경우 시나리오 ③ 경로.

**검증 규칙.**
- `estimated_daily_spend_cap_krw` — 정수 KRW. `null`은 결측(③ 경로). `0`·음수는 **무효 → ③ 차단**(0 대체 금지).
- `spend_horizon_days` — **v1은 서버 고정 상수 7**(클라이언트 입력 안 받음 → 비정상값 원천 차단). 향후 동적화 시
  `positive int` + 허용 범위(예 1..30) 검증, 벗어나면(`null`·`0`·음수·과대값) **fallback 7 또는 차단**.
- `budget_basis` — 위 enum 외 값은 `unknown`으로 정규화(③ 경로). 임의 문자열을 그대로 신뢰하지 않는다.

---

## 3. 권위 분리 원칙 (전 페이즈 공통)

- **서버가 권위(authoritative)**. 인라인 적격 판정·ack 충족·집행 가능 여부는 `finalize`/`decision`(execute) 서버가
  최종 강제한다. 부적격이면 `missing_spend_info`/`unsupported_budget_basis`/`ack_missing`으로 거부.
- **UI는 안내(advisory)**. 버튼 숨김·비활성·체크박스는 사용자 안내일 뿐, 보안 경계가 아니다. FE를 우회해도 서버에서 막힌다.
- spec3가 이미 쓰는 패턴("Tier3 서버 가드 — FE에만 기대지 않는다")의 연장이다.

---

## 4. 기존 자산 재사용 맵 (spec3)

| 자산 | 재사용/확장 |
|---|---|
| `chat_management.py` `/proposals/finalize` → `/decision` | **재사용**. 적격 판정·ack 가드를 이 경로에 추가 |
| `proposal_builder.build_action_proposal_from_diagnosis` | **확장**. 3필드를 evidence/계약에 실어 보냄 |
| `result_card.build_execution_result_card` / `ExecutionResultSection` | **확장**. 풀어쓰기·`submitted_pending_review` 표기 |
| `ProposalActions.tsx` (검토·승인 → 집행/거절, `driftAck`) | **확장**. 실과금 ack 상태·풀어쓰기 추가 |
| `proposal_hash` / drift 비교(`shown_budget_after_krw`) | **재사용**. ack-스냅샷 결속의 토대 |
| `approve()` / `executor.execute()` / Tier 정책(`approval.py`) | **불변**. 정책 권위는 그대로, 인라인 적격은 별도 게이트 |

---

## 5. 정책 변경 — 좁은 인라인 적격 술어 (P3의 핵심)

"TIER_3 허용"을 `CHAT_EXECUTABLE_MAX_TIER` 완화로 구현하지 **않는다**(너무 넓음). 대신 기존 Tier 정책은 그대로 두고,
**별도의 좁은 인라인 적격(allowlist) 술어**를 추가한다.

```
inline_self_approval_eligible(proposal, profile, ack) :=
      feature_flag.chat_inline_self_approval == on        # kill switch
  AND profile ∈ { start_live, modify_live }
  AND budget_basis == daily
  AND estimated_daily_spend_cap_krw is not null
  AND ( action ∈ { ACTIVATE_CAMPAIGN, INCREASE_BUDGET }  ⇒  ack(spend_risk) 충족(§6) )
```

**누가 TIER_3를 통과시키나 (호출 위치 명시).** `approval.py`는 그대로 둔다 — 검증(`validate_proposal`)·자동승인
한도는 불변이고, **TIER_3 기본 deny도 유지**한다. 인라인 예외는 approval.py를 완화하는 게 아니라, **챗 decision
경로(`chat_management.decide_proposal`)에 있는 단일 게이트**에서 평가된다. 구체적으로 현재의 평면 차단
`requires_external_approval(tier) → reject`를 다음으로 바꾼다.

```
tier > CHAT_EXECUTABLE_MAX_TIER  AND NOT inline_self_approval_eligible(...)  → 정식화면(reject)
```

즉 TIER_3는 **이 예외 게이트가 참일 때만** execute 경로로 통과하고, 그 판정·강제는 챗 라우터 한 곳에 모인다.
approval.py·executor·Tier 정책 본체는 미수정.

- 위 술어는 Tier 천장 위에 얹는 "챗 인라인에서만 통하는" 추가 관문이며, 하나라도 거짓이면 정식 승인 화면으로 보낸다.
- **Feature flag / kill switch**: `settings.chat_inline_self_approval`(기본 off). 운영 중 즉시 인라인 셀프승인을 전면
  비활성화할 수 있어야 한다(P3 진입 전에 골격만 P1에 둬도 됨).
- 술어가 거짓인 경로는 전부 **서버가 거부 + 사유 코드 + 감사**로 닫는다(§3 권위 분리).

---

## 6. 지출위험 ack (`spend_risk`) — 스냅샷 결속 서버 계약 (P2의 핵심)

### 적용 범위 — 지출이 늘어나는 조치(`spend_risk`)에

실과금 ack은 **상태가 아니라 집행 전 동의 게이트**다. 사용자가 "이 조치로 추가 지출이 발생함"을 인지했다는 한 단계다.
**지출을 새로 시작하거나 늘리는 조치(`spend_risk`)에 적용**한다 — 신규 게재(과금 0→시작)와 일 예산 증액 **둘 다**.
지출을 줄이거나 멈추는 안전 방향(정지·감액)은 ack 없이 간다.

| action_type | profile | Tier | 집행 효과 | ack(`spend_risk`) |
|---|---|---|---|---|
| `ACTIVATE_CAMPAIGN` (신규 게재) | `start_live` | TIER_3 | 과금 0→시작 | ✅ (reason=`activate_campaign`) |
| `INCREASE_BUDGET` | `modify_live` | TIER_3 | 일 예산 ↑ | ✅ (reason=`increase_budget`) |
| `DECREASE_BUDGET` | `modify_live` | TIER_1 | 일 예산 ↓ | ❌ |
| `PAUSE_CAMPAIGN` | — | TIER_1 | 정지 | ❌ |

> **현재 Tier 매핑(`TIER_POLICY`, grounding).** ACTIVATE_CAMPAIGN·INCREASE_BUDGET = **TIER_3**(오늘은 챗 인라인
> 차단), PAUSE·DECREASE = TIER_1(오늘도 인라인 집행 가능). 즉 ack가 붙는 두 조치는 **둘 다 P3 적격 술어(§5)를 켜야
> 인라인으로 열린다**. ack는 그 문을 열 때 거는 마찰이다.

**ack_type / ack_reason (이름 정정).** `launch`가 증액에는 안 맞으므로 포괄 이름을 쓴다.
- `ack_type = "spend_risk"` — 지출 위험 조치 공통 ack.
- `ack_reason ∈ { "activate_campaign", "increase_budget" }` — payload로 케이스 구분.

**ack 문구(액션별 — 같은 카피로 묶지 않는다).**
- `activate_campaign`: "지금부터 실제 과금이 시작됩니다."
- `increase_budget`: "일 예산이 증가해 추가 지출이 발생할 수 있습니다."

- **승인·집행 = "제안된 action_type을 그대로 실행"**. 승인이 항상 정지(pause)를 의미하지 않는다 — PAUSE 제안은 정지로,
  ACTIVATE는 게재 시작, INCREASE는 증액으로 간다. ack는 그중 **지출이 새로 시작/증가하는 두 조치**에만 붙는다.
- 정지·감액 등 **지출을 줄이는 안전 방향**은 ack 없이 기존 인라인 흐름(§7 P1)으로 집행한다.

> **목업 이탈(의도).** 목업 시나리오 ①은 "modify_live 증액 → ack 없이"였으나, 본 설계는 **증액도 `spend_risk` ack
> 대상**으로 정한다(사용자 결정). 따라서 ① 카드는 목업과 달리 ack 체크박스를 1단계 가진다 — 의도된 차이.

### 스냅샷 결속 (ack 위·변조 방지)

ack를 단순 `acknowledged=true` boolean으로 받지 않는다. 그러면 제안 내용이 바뀐 뒤에도 옛 ack가 재사용될 수 있다.
ack는 **사용자가 본 바로 그 제안 스냅샷에 결속**된다.

- 클라이언트가 ack 시, 표시된 제안의 식별·스냅샷을 함께 제출: `proposal_id`, `ack_type="spend_risk"`, `ack_reason`,
  표시된 지출 스냅샷 — `shown_daily_cap_krw`·`shown_horizon_days` + **증액 표기용 `shown_budget_before_krw`·
  `shown_budget_after_krw`·`shown_delta_krw`**(사용자가 "무엇이 얼마나 늘었는지" 본 사실을 감사에 남긴다) 또는 그 **version/hash**.
- 서버는 ack 스냅샷이 **현재 정본 proposal과 일치할 때만** 유효 처리한다(불일치 = drift → ack 무효, 재확인 요구).
  기존 `proposal_hash`/drift 기제를 그대로 토대로 쓴다.
- **감사 로그**에 최소: `ack_type`·`ack_reason`, `proposal_id`(및 파생 `action`/approval id), `actor`(승인자),
  `timestamp`, 표시된 지출 스냅샷(before/after/delta 포함) 또는 hash. (`chat.inline.ack`·`chat.inline.blocked` 이벤트.)
- ack 미충족·불일치면 서버가 `ack_missing`으로 집행 차단(§3).

---

## 7. 페이즈 분해

> 출하 단위로 쪼갠다. **P1은 단독 출하 가능**(목업의 보이는 부분 먼저). 정책을 바꾸는 **P3는 맨 뒤로 격리**하고,
> ack 마찰(P2)이 먼저 존재해야 P3가 안전하다. 각 페이즈는 자체 spec→plan 문서를 갖는다.

### P0 — 선행: 재사용 경계 확인 (리스크 낮음)
- spec3 `ChatCardView`/`ProposalActions`/`sections`가 **일반 챗(`chat/page.tsx`)에 실제 마운트**되는지 확인.
- finalize→decision→결과카드 흐름에서 **어떤 컴포넌트·상태·액션 payload를 그대로 쓰고 어디서 분기**하는지 매핑.
- 산출: 재사용/분기 지점 표 + (필요 시) 일반 챗에 spec3 카드 경로 연결 과제 식별.
- **종료 기준**: P1이 손댈 정확한 파일·함수·payload 경계가 문서로 고정됨.

### P1 — 데이터 계약 + 지출 풀어쓰기 + ③ 차단 (리스크 낮음, 의존: P0)
- 3필드를 end-to-end 신설: proposal_builder → 카드 섹션/`FinalizeResult` → 프론트 표시.
- 지출 풀어쓰기 **표시만** 추가: "N일 기준 예상 최대 지출 = cap×days". **집행 권한은 안 연다** — INCREASE·ACTIVATE는
  TIER_3라 P1에서도 여전히 인라인 차단(정식화면)이고, 인라인 집행은 P3에서 열린다.
- 시나리오 ③ `budget_basis ∈ {lifetime, unknown}` 또는 cap=null → **서버 차단**(`unsupported_budget_basis`/
  `missing_spend_info`) + `chat.inline.blocked` 감사 + 정식화면 안내. UI는 안내만(§3).
- **실행 권한 불변** — 오늘 챗 인라인 집행 가능한 건 PAUSE·DECREASE(TIER_1)뿐이며 P1은 이를 바꾸지 않는다. 새 집행 권한 없음.
- **종료 기준**: 제안 카드에 풀어쓰기가 보이고, lifetime/지출부족은 서버가 막고 정식화면 안내. TIER_3 두 조치는 아직 정식화면.

### P2 — `spend_risk` ack 서버 계약 (리스크 중간, 의존: P1)
- **§6 스냅샷 결속 ack 서버 계약**을 구축·검증한다: `ack_type="spend_risk"` + `ack_reason`(`activate_campaign`/
  `increase_budget`) + 스냅샷(before/after/delta·cap·horizon) 일치 검사 + `ack_missing` 차단 + 감사(`chat.inline.ack`).
  ack 체크박스(UI 안내, 액션별 문구)·payload 형태도 이 페이즈에서 정의.
- **정책은 넓히지 않는다.** ack가 붙는 두 조치(ACTIVATE·INCREASE)는 TIER_3라 P3 전까지 인라인 집행 대상이 아니므로,
  실제 사용자 흐름에는 아직 ack가 노출되지 않는다 — 이 페이즈는 **계약·게이트를 먼저 만든다**.
- **독립 검증 방법**: 서버 ack 계약을 **테스트 + flag-gated/테스트 전용 경로**로 검증한다(end-user 노출은 P3).
  스냅샷 일치 시 통과, drift·미충족·재사용 시 `ack_missing` 차단을 단위/통합 테스트로 게이트.
- **종료 기준**: ACTIVATE·INCREASE는 일치하는 ack 없이는 어떤 경로로도 집행 안 됨이 **테스트로 증명**됨
  (서버 강제 + 감사). 사용자 노출은 P3에서 적격 술어를 켤 때 활성.

### P3 — 좁은 인라인 셀프승인 정책 (리스크 높음, 의존: P2)
- §5 적격 술어 + feature flag/kill switch 도입. profile/budget_basis/spend/ack 조건을 다 만족할 때만
  **TIER_3 두 조치(ACTIVATE·INCREASE)** 를 인라인 집행 허용. 챗 decision 게이트의 평면 차단을 술어로 교체(§5).
  `approval.py`·executor·Tier 정책 본체는 불변.
- **종료 기준**: flag on에서 적격 TIER_3 조치만 ack 충족 시 인라인 집행, 그 외 정식화면. flag off면 전부 정식화면(킬 스위치 검증).

### 의존 그래프
```
P0 → P1 → P2 → P3
```

---

## 8. Non-goals (이번 엄브렐러 범위 밖)

- Meta 진단 파이프라인이 `budget_basis`/`cap`을 산출하는 **실연동 정확도** 개선(데모/mock 값으로 계약만 고정, 실측 보정은 후속).
- `lifetime` 예산의 인라인 지원(v1은 `daily`만). 멀티테넌트 진단 스코프(spec3 기존 제약 승계).
- 재시도/조정(reconciliation) 강화(spec3 non-goals 승계).
- 정식 승인 화면 자체의 개편(인라인에서 그쪽으로 "보내는" 것까지만).

---

## 9. Open Questions (페이즈 spec에서 해소)

- **profile(`start_live`/`modify_live`) 출처** — proposal/진단에서 어떻게 도출하나? action_type 매핑인가 별도 신호인가? (P0/P1에서 확정)
- **감사 이벤트 스키마** — `chat.inline.ack`/`chat.inline.blocked`를 기존 `audit_events`에 어떻게 싣나(payload 필드). (P2)
- **feature flag 위치** — `settings` env vs DB 토글. 운영 킬 스위치 요구 수준에 따라. (P3)
- **일반 챗 ↔ 매니지먼트 챗 표면 통합** — P0 결과에 따라 카드 경로 연결 과제가 P1로 들어올 수 있음.
