# 챗 캠페인 조치 — 정식 승인 플로우 임베드 재사용 (엄브렐러 설계)

> **성격**: 큰 계획(umbrella). "왜·어디로·무엇을 페이즈로 쪼개나"를 고정한다. 각 페이즈의 "어떻게"는
> 페이즈별 독립 spec→plan 문서가 책임진다. 본 문서는 구현 단위가 아니다.
>
> **브랜치**: `feat/management` · **날짜**: 2026-06-29.
>
> **개정 노트**:
> 1. 최초판(인라인 셀프승인·`spend_risk` ack)을 트랙 H(사람 승인 프리뷰 재사용)로 전환.
> 2. **브랜치 정정** — 이미지가 기댄 spec3 챗-실행 브릿지(`chat_management` finalize/decision · `proposal_builder` ·
>    `proposal_store` · `ProposalActions` · `ChatCardView`)는 **`feat/chat-boeun`에만** 있고 본 브랜치엔 없다.
>    따라서 spec3 백엔드·진단 파이프라인을 **포팅하지 않고**, **카드 UI만 가져와 management의 정식 흐름에
>    재배선**한다(§4 포팅 표면).

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
- **이 브랜치 핵심**: 정식 `/approve`·`/execute`엔 **tier-reject가 없다**. CREATE_CAMPAIGN(TIER_3)도 사람 승인만으로
  통과한다(= 현 생성 플로우). 그래서 "챗 전용 차단을 없앤다"가 아니라, **처음부터 차단 없는 정식 경로를 챗에서
  재사용**하는 것이다. (spec3의 챗 `decision` tier-block은 `feat/chat-boeun` 전용 — 본 브랜치엔 없어 정렬할 대상이
  없다.)
- 따라서 `approval.py`·`executor`·정식 라우트는 **미수정**. 인라인 셀프승인용 allowlist·정책 변경은 **불필요**.

> **현재 Tier 매핑(`TIER_POLICY`, grounding).** PAUSE·DECREASE = TIER_1, 그 외 6종 = TIER_3.
> 본 설계는 Tier 천장을 건드리지 않는다. TIER_3도 **사람이 프리뷰에서 승인**하므로 정식 경로와 동일하게 통과한다.

---

## 3. 핵심 불변식 (LLM 제안 ↔ 사람 승인)

LLM이 폼/파라미터를 제안하더라도 안전 경계는 사람 승인과 서버 권위에 둔다.

- **execute는 서버가 빌드한 정본 proposal만 사용**. LLM 자유텍스트가 집행 인자로 직접 들어가지 않는다.
- **프리뷰에 보이는 값 = 집행 대상.** `proposal_hash`로 결속하고, 표시 후 값이 바뀌면(drift) 재확인을 요구한다.
- **사람의 승인 클릭이 게이트 충족 지점.** 이 단계를 생략하고 자동 집행하면 — 그때만 — 정책 위반이다.
- **승인상태는 정식 경로가 이미 강제한다(신설/삭제 없음).** `/approve`가 `ApprovedAction`(approval_id)을 발행하고,
  `executor`가 **`proposal_hash` 일치를 검증**(`executor.py:265`)한 뒤 감사(`audit_events`)를 남긴다. 챗은 이 경로를
  **그대로 호출**한다 — 별도 게이트를 새로 만들거나 차단을 삭제하지 않는다.
- **권위 분리**: 서버가 권위(authoritative), UI(폼·프리뷰·버튼)는 안내(advisory). FE를 우회해도 서버에서 막힌다.

---

## 4. 재사용 자산 + 포팅 표면 (이 브랜치 기준)

> 핵심 결정: **카드 UI만 가져오고, spec3 백엔드·진단 파이프라인은 가져오지 않는다.** 이미지의 카드 모양·2단계
> 흐름은 그대로 살리되, 데이터는 management의 정식 흐름으로 흐르게 재배선한다.

### (A) 있음 — 정식 흐름 (재사용, 미수정)
| 자산 | 역할 |
|---|---|
| `executor`(8종, `executor.py:44`) · `/approve` · `/execute` | 집행 정본. `proposal_hash` 검증·감사 포함 |
| `/campaigns/create-proposal` + `CampaignForm` + `CreateProposalPreview` | CREATE 폼→제안→프리뷰 |
| `/run` · `/anomaly/scan` · `/regenerate` · `from-candidate` · `from-simulation` | 비-CREATE proposal 생성원 |
| `chat.py`(`/complete` SSE·orchestrator) · `chat/page.tsx` · `composer`/`chat_cards` | 챗 표면·카드 골격 |
| `ManagementChatMessage` · `audit_events` | 챗 이력·감사 영속 |

### (B) 가져올 것 — 카드 UI (포팅, 닫힌 집합)
- **프론트(5파일)**: `components/chat/{ProposalActions, ChatCardView, sections}.tsx` + `lib/{chatCard.ts,
  managementActions.ts}`. `Markdown.tsx`는 management `chat/page.tsx`의 `renderMarkdown`으로 **대체**(→ `react-markdown`
  npm 불필요).
- **백엔드(소량 추가)**: `result_card.py`(결과 카드 빌더) + `chat_cards/models.py`에 `ExecutionResultSection` +
  결과 타입(`FinalizeResult` 상당) 추가.
- **재배선(핵심)**: `managementActions.ts`/`ProposalActions`의 `finalize`/`decision` 호출 → **management 정식
  엔드포인트**(proposal 생성 + `/approve` + `/execute`)로 교체. 이미지의 "검토·승인 → 집행"은 그대로, 백엔드만 정식 흐름.

### (C) 안 가져올 것 — 드래그 차단
- spec3 백엔드 브릿지: `chat_management`(finalize/decision) · `proposal_builder` · `proposal_store`.
- **진단 파이프라인(spec1/2)**: `live_diagnosis` · `DiagnosticResult` · `ProposalPreview`.
- `ActionProposalRow` + **Alembic 마이그레이션** — 정식 `/execute`는 proposal을 **request body로 받아** 집행하므로
  proposal 테이블 영속이 **불필요**.

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
> 그 위험을 `spend_risk` ack로 보완한다. 트랙 S 본격 구현은 후순위(별도 spec).

---

## 6. 액션별 제안·프리뷰 매트릭스

각 조치를 챗에 임베드하려면 "제안을 무엇으로 만들고 / 프리뷰에 무엇을 보여주나"가 필요하다. 막는 것은 정책이
아니라 **이 배선**이다. (제안 출처는 모두 **management 엔드포인트** — spec3 `finalize`/`live_diagnosis` 아님.)

| action_type | Tier | 제안 출처(management) | 프리뷰 | 집행 |
|---|---|---|---|---|
| `CREATE_CAMPAIGN` | 3 | `/campaigns/create-proposal`(폼) | `CreateProposalPreview` ✅있음 | `/approve`+`/execute` |
| `INCREASE_BUDGET` | 3 | `/run`·`/anomaly`·`/regenerate` 등 | 포팅 `ProposalActions`(재배선) | `/approve`+`/execute` |
| `DECREASE_BUDGET` | 1 | 〃 | 〃 | 〃 |
| `PAUSE_CAMPAIGN` | 1 | 〃 | 〃 | 〃 |
| `ACTIVATE_CAMPAIGN` | 3 | 〃 | 〃 +실과금 확인 항목 | 〃 |
| `REPLACE_CREATIVE` | 3 | `/regenerate` 후보 | **신규 프리뷰 필요** | `/approve`+`/execute` |
| `EXPAND_AUDIENCE` | 3 | 에스컬레이션 사다리 | **신규 프리뷰 필요** | `/approve`+`/execute` |
| `CHANGE_BID_STRATEGY` | 3 | 에스컬레이션 사다리 | **신규 프리뷰 필요** | `/approve`+`/execute` |

> **`ACTIVATE_CAMPAIGN` 실과금 확인 (프리뷰 내부).** 게재 시작은 과금이 0→시작되므로 프리뷰 안에 "지금부터 실제
> 과금이 시작됩니다 — 이해" 확인 항목을 둔다. 별도 ack 계약(트랙 S)이 아니라 **프리뷰 승인의 한 필드**다.
> - **필드명 후보**: `activation_notice_confirmed: true`(승인 제출 payload). 페이즈 spec에서 이 이름으로 고정.
> - **결속**: 승인 제출 시 `proposal_hash`와 **함께** 전송. 서버는 **미확인(`false`) 또는 drift이면 승인 거부**(§3).
> - **영속·감사**: 확인 사실을 **`audit_events`에 적재**("실과금 확인 문구가 포함된 프리뷰를 승인함" — actor·timestamp·
>   proposal_hash 포함). `ActionProposalRow`를 포팅하지 않으므로 proposal 테이블이 아니라 **감사 로그가 정본 흔적**이다.

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
> 풀어쓰기를 못 그리는 것**일 뿐이다. 집행은 **프리뷰 사람 승인으로 정상 진행**한다. 결측을 집행 게이트로 쓰지 않는다.

---

## 8. 페이즈 분해

> 재사용도 높은 것부터. 각 페이즈는 자체 spec→plan을 갖는다.

### P0 — 재사용 경계 + 포팅 표면 확정 (리스크 낮음)
- §4 포팅 표면(가져올 5+α 파일 / 안 가져올 spec3·진단·마이그레이션)을 **파일 단위로 확정**.
- 정식 `/approve`+`/execute`가 **챗에서 그대로 호출 가능한지** 확인 — 승인상태(approval_id)·`proposal_hash` 검증·
  감사가 정식 경로와 동등하게 생기는지(이미 `executor.py:265`로 강제됨을 코드로 확인).
- `ProposalActions`/`managementActions`의 `finalize`/`decision` → 정식 엔드포인트 **재배선 지점**을 명시.
- **종료 기준**: P1이 손댈 파일·재배선 지점이 문서로 고정됨.

### P1 — 카드 UI 포팅 + 정식 흐름 재배선 + `CREATE_CAMPAIGN` 임베드 (리스크 중간, 의존: P0)
- 카드 UI 5파일 포팅(Markdown은 `renderMarkdown` 대체) + `result_card`·`ExecutionResultSection` 추가.
- `managementActions`/`ProposalActions`를 **정식 흐름**(proposal 생성 + `/approve` + `/execute`)으로 재배선.
- 첫 액션으로 `CampaignForm` + `CreateProposalPreview`를 챗 카드에 임베드 → `/create-proposal` → `/approve`+`/execute`.
  LLM은 폼 prefill만, 최종 승인은 사람.
- **종료 기준**: 챗에서 폼 작성→프리뷰 승인으로 캠페인이 정식 경로와 동일하게 생성됨(PAUSED). **LLM prefill은 카드
  안에서 수정 가능**, **서버 validation 실패가 카드 안에서 회복 가능**(이탈 없이).

### P2 — 예산·상태 4종 (리스크 중간, 의존: P1)
- `INCREASE`/`DECREASE`/`PAUSE`/`ACTIVATE` — management 제안 엔드포인트(`/run`·`/anomaly`·`/regenerate`)로 proposal을
  만들고, 포팅한 `ProposalActions`(재배선)로 프리뷰→`/approve`+`/execute`. `ACTIVATE`는 프리뷰 내부 실과금 확인(§6).
  (선택) §7 지출 풀어쓰기 표시.
- **종료 기준**: 4종이 챗 프리뷰 승인으로 집행됨. lifetime/지출부족은 풀어쓰기만 생략(집행 차단 아님 — §7).

### P3 — 나머지 3종 (리스크 중간~높음, 의존: P2)
- `REPLACE_CREATIVE`(소재 후보 선택 연계) · `EXPAND_AUDIENCE` · `CHANGE_BID_STRATEGY`. 각 제안 빌더 + **신규 프리뷰**.
- **종료 기준**: 3종이 챗 프리뷰 승인으로 집행됨. 프리뷰에 변경 내용(소재/타깃/전략)이 명확히 표시됨.

### (선택) S — 원클릭 지출 가속 (후순위, 의존: P2)
- 자주 쓰는 지출 조치(INCREASE·ACTIVATE)에 `spend_risk` ack 기반 **원클릭** 경로 추가(이전 판 설계 되살림).

### 의존 그래프
```
P0 → P1 → P2 → P3
              └→ (선택) S
```

---

## 9. Non-goals

- **별도 검토자(maker-checker)** 도입 — 현행은 "명시적 사람 승인"이면 충분.
- **spec3 백엔드 브릿지·진단 파이프라인(`live_diagnosis`)·`ActionProposalRow` 마이그레이션 포팅** — 가져오지 않는다(§4-C).
- writer 실연동 정확도(데모/mock으로 계약만 고정) · 트랙 S 본격 구현(후순위).

---

## 10. Open Questions (페이즈 spec에서 해소)

- **비-CREATE 제안 출처 확정** — INCREASE/PAUSE 등은 `/run`·`/anomaly`·`/regenerate` 중 무엇으로 proposal을 만드나,
  아니면 챗 제안→경량 proposal 빌더가 필요한가. (P0/P2)
- **챗 액션 의도 감지** — 사용자 발화 → 어떤 액션·빌더로 라우팅(키워드/LLM 분류). (P0/P1)
- **LLM 파라미터 제안의 검증** — prefill 값의 서버측 검증 범위(특히 CREATE 폼). (P1)
- **REPLACE_CREATIVE 소재 출처** · **EXPAND/BID 신규 프리뷰** 설계. (P3)
