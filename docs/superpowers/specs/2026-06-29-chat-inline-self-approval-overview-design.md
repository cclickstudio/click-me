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

매니지먼트 챗에서, 라이브·실과금에 영향을 주는 조치(예산 증액·캠페인 게재 시작)를 **카드형 액션바에서 인라인으로
셀프승인·집행**한다. 단, 정책상 위험한 조치는 **명시적 마찰(실과금 ack)** 과 **좁은 적격 조건**을 통과할 때만 허용하고,
그 외는 기존처럼 정식 승인 화면으로 보낸다. 목업(`TIER_3 인라인 셀프승인 — 카드 설계 목업`)이 목표 화면이다.

### 목업 4개 시나리오 (목표)

1. **modify_live · budget_basis=daily** — 일 예산 증액. ack 없이 "검토·승인 → 집행 대기 → 집행".
   지출 풀어쓰기 표시("N일 기준 …").
2. **start_live · ACTIVATE_CAMPAIGN** — 신규 게재(실과금 시작). **실과금 ack 체크박스 1단계 추가**, ack 완료 전 집행 차단.
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
| `spend_horizon_days` | int (days) | 인라인에서 지출 상한을 풀어 보여줄 기간. | 기본 `7`(목업 기준) |
| `estimated_daily_spend_cap_krw` | int(KRW) \| null | **일 단위 지출 상한/환산 상한**(예측 아님). Meta 진단이 산출. | 없으면 `null`. **0으로 대체 금지** |

### 표기 주의 — "cap"의 의미

`estimated_daily_spend_cap_krw`는 **예측 지출이 아니라 일 지출 상한**이다. 풀어쓰기 표시값
`estimated_daily_spend_cap_krw × spend_horizon_days`는 **"N일 기준 예상 최대 지출 / 지출 상한"** 이다.
목업 문구("N일 기준 예상지출")를 화면에서 유지하더라도, **데이터 정의와 코드 주석은 "상한" 의미를 명기**한다.
(권장 문구: "7일 기준 예상 최대 지출" 또는 "7일 기준 지출 상한".)

### 결측 처리 원칙

`estimated_daily_spend_cap_krw == null` 또는 `budget_basis ∈ {lifetime, unknown}`이면 **인라인 풀어쓰기·셀프승인을
산출하지 않는다**. null을 0으로 메우지 않는다(0은 "상한 0"이라는 잘못된 단정이 된다). 이 경우 시나리오 ③ 경로.

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
  AND ( action is paid_launch  ⇒  ack 충족(§6) )
```

- **정책 권위는 `approval.py`(Tier)에 그대로 남는다.** 위 술어는 그 위에 얹는 "챗 인라인에서만 통하는" 추가 관문이며,
  하나라도 거짓이면 정식 승인 화면으로 보낸다.
- **Feature flag / kill switch**: `settings.chat_inline_self_approval`(기본 off). 운영 중 즉시 인라인 셀프승인을 전면
  비활성화할 수 있어야 한다(P3 진입 전에 골격만 P1에 둬도 됨).
- 술어가 거짓인 경로는 전부 **서버가 거부 + 사유 코드 + 감사**로 닫는다(§3 권위 분리).

---

## 6. 실과금 ack — 스냅샷 결속 서버 계약 (P2의 핵심)

ack를 단순 `acknowledged=true` boolean으로 받지 않는다. 그러면 제안 내용이 바뀐 뒤에도 옛 ack가 재사용될 수 있다.
ack는 **사용자가 본 바로 그 제안 스냅샷에 결속**된다.

- 클라이언트가 ack 시, 표시된 제안의 식별·스냅샷을 함께 제출: `proposal_id`, `ack_type="paid_launch"`,
  표시된 지출 스냅샷(`shown_daily_cap_krw`·`shown_horizon_days`) 또는 그 **version/hash**.
- 서버는 ack 스냅샷이 **현재 정본 proposal과 일치할 때만** 유효 처리한다(불일치 = drift → ack 무효, 재확인 요구).
  기존 `proposal_hash`/drift 기제를 그대로 토대로 쓴다.
- **감사 로그**에 최소: `ack_type`, `proposal_id`(및 파생 `action`/approval id), `actor`(승인자), `timestamp`,
  표시된 지출 스냅샷 또는 hash. (`chat.inline.ack`·`chat.inline.blocked` 이벤트.)
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
- 시나리오 ① "N일 기준 예상 최대 지출(=cap×days)" 풀어쓰기 표시(modify_live·daily, ack 없음).
- 시나리오 ③ `budget_basis ∈ {lifetime, unknown}` 또는 cap=null → **서버 차단**(`unsupported_budget_basis`/
  `missing_spend_info`) + `chat.inline.blocked` 감사 + 정식화면 안내. UI는 안내만(§3).
- **실행 권한 불변** — 기존 적격 범위만 표시가 풍부해질 뿐, 새 집행 권한 없음.
- **종료 기준**: 적격 제안은 풀어쓰기가 보이고, 부적격은 서버가 막고 화면이 정식화면으로 안내.

### P2 — 실과금 ack 마찰 (리스크 중간, 의존: P1)
- 시나리오 ② start_live: ack 체크박스(UI 안내) + **§6 스냅샷 결속 서버 계약** + `ack_missing` 차단 + 감사.
- **단, 이 페이즈는 정책을 넓히지 않는다** — ack는 "현재 인라인 적격인 조치"에 마찰을 더하는 것까지.
- **종료 기준**: paid_launch 조치는 일치하는 ack 없이는 어떤 경로로도 집행 안 됨(서버 강제 + 감사).

### P3 — 좁은 인라인 셀프승인 정책 (리스크 높음, 의존: P2)
- §5 적격 술어 + feature flag/kill switch 도입. profile/budget_basis/spend/ack 조건을 다 만족할 때만
  해당 라이브·실과금 조치를 인라인 집행 허용. Tier 정책(`approval.py`)은 불변.
- **종료 기준**: flag on에서 적격 조치만 인라인 집행, 그 외 정식화면. flag off면 전부 정식화면(킬 스위치 검증).

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
