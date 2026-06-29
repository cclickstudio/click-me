# 챗 캠페인 조치 — 정식 승인 플로우 임베드 재사용 (엄브렐러 설계)

> **성격**: 큰 계획(umbrella). "왜·어디로·무엇을 페이즈로 쪼개나"를 고정한다. 각 페이즈의 "어떻게"는
> 페이즈별 독립 spec→plan 문서가 책임진다. 본 문서는 구현 단위가 아니다.
>
> **브랜치**: `feat/management` · **날짜**: 2026-06-29 · **선행 자산**: spec3(`2026-06-25-chat-management-execution-spec3`).
>
> **개정 노트**: 본 문서는 같은 날 최초판(인라인 셀프승인·`spend_risk` ack 중심)을 **대체**한다. 사용자 결정으로
> 축을 **"사람 승인 프리뷰를 챗에 임베드해 재사용(트랙 H)"** 으로 전환했다. 이전 셀프승인·ack 설계는 §5의
> 선택적 트랙 S로 보존한다.

---

## 1. 목표 상태

매니지먼트 챗에서 **모든 캠페인 조치(8종)** 를, 기존 정식 승인 플로우(폼 · 프리뷰 · `approve` · `execute`)를
**챗 카드에 임베드해 재사용**하는 방식으로 실행한다. **LLM이 제안·파라미터를 채우고, 사람이 프리뷰에서 최종
승인**한다. **승인 정책(Tier 게이트)은 바꾸지 않는다** — 챗은 기존 승인 경로의 새 진입점일 뿐이다.

**대상 8종** (`executor.py:44` `SUPPORTED_ACTION_TYPES` — 전부 집행 지원됨).
`PAUSE_CAMPAIGN` · `DECREASE_BUDGET` · `INCREASE_BUDGET` · `ACTIVATE_CAMPAIGN` · `CREATE_CAMPAIGN` ·
`REPLACE_CREATIVE` · `EXPAND_AUDIENCE` · `CHANGE_BID_STRATEGY`.

---

## 2. 왜 정책 위반이 아닌가 (정책 프레이밍)

- **Tier-3 "건별 사람 승인"의 뜻** = 사람이 각 건을 **명시적으로 승인**해야 한다. **다른 사람**이 승인해야 한다는
  뜻이 아니다(현행 생성 플로우도 폼 작성자가 곧 승인자다).
- 챗이 **제안 → 프리뷰 → 사람의 승인 클릭 → `approve`+`execute`** 를 그대로 태우면 그 게이트가 살아 있다.
  제너릭 `approve(proposal) → execute(approved, proposal)`가 8종을 전부 집행한다 — **검토자가 사라지지 않는다.**
- 따라서 `approval.py`·`executor`·Tier 정책 본체는 **미수정**. 인라인 셀프승인용 allowlist·정책 변경은 **불필요**.
- **단, spec3 챗 `decision`의 보수적 TIER_3 차단**(`requires_external_approval(tier) → reject`)은 손댄다. 이건
  **정책을 바꾸는 게 아니라**, 사람 승인 없이 챗에서 집행될까봐 걸어둔 **챗 전용 우회 차단을, 정식 승인 경로(프리뷰
  사람 승인)로 정렬**하는 작업이다. **차단을 단순 삭제하는 게 아니라 "유효한 사람 승인 레코드가 있는가" 확인으로
  대체**한다(§3 TIER_3 집행 게이트). 삭제만 하면 TIER_3가 승인 확인 없이 통과돼 위험하다.

> **현재 Tier 매핑(`TIER_POLICY`, grounding).** PAUSE·DECREASE = TIER_1, 그 외 6종 = TIER_3.
> 본 설계는 Tier 천장을 건드리지 않는다. TIER_3도 **사람이 프리뷰에서 승인**하므로 정식 경로와 동일하게 통과한다.
> (= 챗 전용 차단을 없애고 정식 경로로 합치는 것이지, Tier 등급을 낮추는 게 아니다.)

---

## 3. 핵심 불변식 (LLM 제안 ↔ 사람 승인)

LLM이 폼/파라미터를 제안하더라도 안전 경계는 사람 승인과 서버 권위에 둔다.

- **execute는 서버가 빌드한 정본 proposal만 사용**. LLM 자유텍스트가 집행 인자로 직접 들어가지 않는다.
- **프리뷰에 보이는 값 = 집행 대상.** `proposal_hash`로 결속하고, 표시 후 값이 바뀌면(drift) 재확인을 요구한다.
- **사람의 승인 클릭이 Tier 게이트 충족 지점.** 이 단계를 생략하고 자동 집행하면 — 그때만 — 정책 위반이다.
- **TIER_3 집행 게이트 = 승인상태 확인(차단 제거 아님).** 챗 `decision`/`execute`는 `requires_external_approval →
  reject`를 **단순 삭제하지 않는다**. 대신 **(a) 사람 승인이 영속돼 `approval_id`가 존재**하고 **(b) 그 승인이 현재
  `proposal_hash`와 일치**할 때만 TIER_3를 집행한다. 게이트가 "tier > X면 거부"에서 **"유효한 사람 승인 레코드가
  있는가"** 로 이동한다 — 승인이 없거나 hash 불일치면 거부. (정식 `approval` route가 만드는 승인 레코드와 동등 —
  P0가 동등성을 검증.)
- **권위 분리**: 서버가 권위(authoritative), UI(폼·프리뷰·버튼)는 안내(advisory). FE를 우회해도 서버에서 막힌다.

---

## 4. 기존 자산 재사용 맵

| 자산 | 역할 / 재사용 |
|---|---|
| `executor` (`SUPPORTED_ACTION_TYPES`, `executor.py:44`) | 8종 집행 정본. **미수정** |
| `approve()` / `execute` 엔드포인트 | 제너릭 승인·집행 경로. 모든 액션 공통 |
| `POST /campaigns/create-proposal` + `CampaignForm` + `CreateProposalPreview` | **CREATE_CAMPAIGN** 폼→제안→프리뷰. 챗에 임베드 |
| spec3 `finalize` → `decision` + `ProposalActions.tsx` | **진단형 조치**(예산·상태) 제안→프리뷰→집행. 재사용·확장 |
| `ChatCardView` / `sections` / `ChatCard` | 챗 카드 렌더 골격. 액션 카드·프리뷰 슬롯 |
| `proposal_hash` / drift 비교 | 프리뷰=집행 결속(§3) |

---

## 5. 두 트랙 — H(척추) / S(선택)

| | **트랙 H — 사람승인 프리뷰 재사용 (이번 본체)** | **트랙 S — 원클릭 셀프승인 가속 (후순위)** |
|---|---|---|
| 흐름 | 제안 → **챗창에 프리뷰 표시** → 사람 승인 → execute | 제안 → **원클릭 ack**(프리뷰 축약) → execute |
| 대상 | **8종 전부** | 지출 조치(INCREASE·ACTIVATE)만 |
| 정책 변경 | **없음** | allowlist + `spend_risk` ack 필요 |
| 위험 | 낮음(프리뷰 사람 승인 유지) | 중(**프리뷰 단계 축약/생략** → `spend_risk` ack로 보완) |

> 둘의 차이는 "검토자가 합쳐지냐"가 아니다 — **maker-checker(다른 승인자)는 H·S 모두 도입 안 한다(§9).** 실제 차이는
> **프리뷰(사람이 챗창에서 내용을 확인하는 단계)를 H는 유지, S는 축약/생략**한다는 점이다. 그래서 S가 더 위험하고,
> 그 위험을 `spend_risk` ack로 보완한다.

> 트랙 S 설계(좁은 적격 술어·`spend_risk` 스냅샷 결속 ack)는 이전 판에 정리돼 있었다. 본 엄브렐러에서는
> **후순위 선택지**로 두고, 트랙 H 완료 후 "자주 쓰는 지출 조치의 클릭 가속"이 필요할 때 별도 spec으로 되살린다.

---

## 6. 액션별 제안·프리뷰 매트릭스

각 조치를 챗에 임베드하려면 "제안을 무엇으로 만들고 / 프리뷰에 무엇을 보여주나"가 필요하다. 막는 것은 정책이
아니라 **이 배선**이다.

| action_type | Tier | 제안 출처 | 프리뷰 | 집행 | 추가 입력 |
|---|---|---|---|---|---|
| `CREATE_CAMPAIGN` | 3 | `create-proposal`(폼) | `CreateProposalPreview` ✅있음 | `approve`+`execute` | 폼: 예산·목표·타깃·소재 |
| `INCREASE_BUDGET` | 3 | `live_diagnosis`→`finalize` | `ProposalActions` ✅있음 | `decision`(approve→execute) | — |
| `DECREASE_BUDGET` | 1 | 〃 | 〃 | 〃 | — |
| `PAUSE_CAMPAIGN` | 1 | 〃 | 〃 | 〃 | — |
| `ACTIVATE_CAMPAIGN` | 3 | 〃 | 〃 +실과금 확인 항목 | 〃 | 프리뷰 내부 실과금 시작 확인(hash 결속) |
| `REPLACE_CREATIVE` | 3 | 재생성 후보 | **신규 프리뷰 필요** | `approve`+`execute` | `selected_candidate_id`(교체 소재) |
| `EXPAND_AUDIENCE` | 3 | 에스컬레이션 사다리 | **신규 프리뷰 필요** | `approve`+`execute` | 타깃 확장 파라미터 |
| `CHANGE_BID_STRATEGY` | 3 | 에스컬레이션 사다리 | **신규 프리뷰 필요** | `approve`+`execute` | 입찰 전략 파라미터 |

> **`ACTIVATE_CAMPAIGN` 실과금 확인 (프리뷰 내부).** 게재 시작은 과금이 0→시작되므로 프리뷰 안에 "지금부터 실제
> 과금이 시작됩니다 — 이해" 확인 항목을 둔다. 별도 ack 계약(트랙 S)이 아니라 **프리뷰 승인의 한 필드**다.
> - **필드명 후보**: `activation_notice_confirmed: true`(승인 제출 payload). 페이즈 spec에서 이 이름으로 고정.
> - **결속**: 승인 제출 시 `proposal_hash`와 **함께** 전송. 서버는 **미확인(`false`) 또는 drift(표시값 변경)이면
>   승인 거부**(§3).
> - **영속·감사**: 확인 사실을 **DB에 저장**한다 — 승인/proposal 레코드에 `activation_notice_confirmed`를 남기고,
>   `audit_events`에 "실과금 확인 문구가 포함된 프리뷰를 승인함"(actor·timestamp·proposal_id 포함) 흔적을 적재.
>   사후에 "이 게재는 실과금 고지를 보고 승인됐다"가 추적 가능해야 한다.

---

## 7. 데이터 계약 (강등 — 선택적 표시 개선)

이전 판의 핵심이던 세 필드는 **승인 게이트가 아니라 "지출 풀어쓰기" 표시 보조**로 강등한다(트랙 H는 프리뷰가
게이트라 이 필드 없이도 동작). 표시 품질을 위해 P2에서 **선택적으로** 싣는다. 정의는 유지한다.

| 필드 | 타입 | 의미 | 결측·기본 |
|---|---|---|---|
| `budget_basis` | enum `daily`\|`lifetime`\|`unknown` | 예산 해석 기준 | 산출 불가 시 `unknown` |
| `spend_horizon_days` | positive int | 풀어쓰기 기간 | **v1 서버 고정 `7`** |
| `estimated_daily_spend_cap_krw` | int(KRW)\|null | **일 지출 상한**(예측 아님) | 없으면 `null`(0 대체 금지) |

표시값 `cap × days` = "N일 기준 예상 최대 지출 / 지출 상한"(cap=상한 의미를 코드 주석에 명기). `null`·`0`·음수·
`lifetime`/`unknown`이면 풀어쓰기를 **표시하지 않는다**.

> **중요 — 집행 차단 사유 아님.** lifetime/지출정보 부족은 트랙 H에서 "셀프승인 부적격"이 아니라 **단지 지출
> 풀어쓰기를 못 그리는 것**일 뿐이다. 집행은 **프리뷰 사람 승인으로 정상 진행**한다. 이 세 필드의 결측을 집행
> 게이트로 쓰지 않는다(게이트는 오직 프리뷰 승인). (이전 트랙 S의 `unsupported_budget_basis` 차단 개념은 폐기.)

---

## 8. 페이즈 분해

> 재사용도 높은 것부터. 각 페이즈는 자체 spec→plan을 갖는다.

### P0 — 재사용 경계 확인 (리스크 낮음)
- `ChatCardView`/`ProposalActions`/`sections`가 **일반 챗(`chat/page.tsx`)에 마운트**되는지 확인.
- 임베드 가능한 폼/프리뷰/엔드포인트(CREATE·진단형)와 호출 payload를 매핑.
- **챗 `decision` 경로가 정식 `approval` route와 동일한 승인 상태를 만드는지 검증** — 같은 `ActionProposal`
  영속·`approval_id`·감사(`audit_events`) 아티팩트가 생기는지 대조(§2 정책 논거의 전제). 어긋나면 P1 전에 메운다.
- **종료 기준**: P1이 손댈 파일·컴포넌트·엔드포인트 경계가 문서로 고정되고, **챗=정식 승인 상태 동등성**이 확인됨.

### P1 — `CREATE_CAMPAIGN` 임베드 (리스크 중간, 의존: P0)
- `CampaignForm` + `CreateProposalPreview`를 **챗 카드로 임베드** → `create-proposal` → `approve`+`execute`.
  (가장 완성된 정식 플로우라 첫 타자. 단 폼 필드가 많고 prefill 검증이 있어 UX 리스크는 낮지 않다.) LLM은 폼
  prefill만, 최종 승인은 사람.
- §3 불변식 적용: 프리뷰=집행 결속, 서버 빌드 proposal, 사람 승인 필수.
- **종료 기준**: 챗에서 폼 작성→프리뷰 승인으로 캠페인이 정식 경로와 동일하게 생성됨(PAUSED). **LLM prefill은
  사용자가 카드 안에서 수정 가능**하고, **서버 validation 실패가 카드 안에서 회복 가능**(에러 표시→수정→재제출,
  챗 흐름 이탈 없이).

### P2 — 예산·상태 4종 (리스크 중간, 의존: P1)
- `INCREASE`/`DECREASE`/`PAUSE`/`ACTIVATE` — spec3 `finalize`/`decision` + `ProposalActions` 재사용해 챗 카드로.
  `ACTIVATE`는 **프리뷰 내부에 실과금 시작 확인 항목**을 포함(§6) — 확인 상태를 `proposal_hash`와 함께 제출,
  서버가 미확인·drift 시 승인 거부. (선택) §7 지출 풀어쓰기 표시.
- **종료 기준**: 4종이 챗 프리뷰 승인으로 집행됨. lifetime/지출정보 부족은 **풀어쓰기 표시만 생략**하고 집행은
  프리뷰 승인으로 정상(집행 차단 사유 아님 — §7).

### P3 — 나머지 3종 (리스크 중간~높음, 의존: P2)
- `REPLACE_CREATIVE`(소재 후보 선택 연계) · `EXPAND_AUDIENCE` · `CHANGE_BID_STRATEGY`. 각 제안 빌더 + **신규 프리뷰**.
- **종료 기준**: 3종이 챗 프리뷰 승인으로 집행됨. 프리뷰에 변경 내용(소재/타깃/전략)이 명확히 표시됨.

### (선택) S — 원클릭 지출 가속 (후순위, 의존: P2)
- 자주 쓰는 지출 조치(INCREASE·ACTIVATE)에 `spend_risk` ack 기반 **원클릭** 경로 추가(이전 판 설계 되살림).
- **종료 기준**: ack 충족 시에만 프리뷰 없이 집행, 서버 강제 + 감사.

### 의존 그래프
```
P0 → P1 → P2 → P3
              └→ (선택) S
```

---

## 9. Non-goals

- **별도 검토자(maker-checker)** 도입 — 현행은 "명시적 사람 승인"이면 충분(다른 승인자 강제 안 함).
- 멀티테넌트 진단 스코프(spec3 제약 승계) · writer 실연동 정확도(데모/mock으로 계약만 고정).
- 트랙 S(원클릭 셀프승인)의 본격 구현 — 선택·후순위.

---

## 10. Open Questions (페이즈 spec에서 해소)

- **챗 액션 의도 감지** — 사용자 발화 → 어떤 액션 빌더로 라우팅하나(키워드/LLM 분류). (P0/P1)
- **LLM 파라미터 제안의 검증** — prefill 값의 서버측 검증 범위·한계(특히 CREATE 폼). (P1)
- **REPLACE_CREATIVE 소재 출처** — 교체 후보(`selected_candidate_id`)를 챗에서 어떻게 고르나(generator 연계). (P3)
- **신규 프리뷰 컴포넌트** — EXPAND_AUDIENCE/CHANGE_BID_STRATEGY 변경 내용 표시 설계. (P3)
