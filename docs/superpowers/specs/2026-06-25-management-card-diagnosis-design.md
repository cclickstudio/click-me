# 매니지먼트 카드 진단 풍부화 설계 (스펙 2)

> 작성일 2026-06-25 · 브랜치 `feat/chat-boeun` · 기능 4-2/4-4(매니지먼트 챗)
> 한 줄 요약 — 매니지먼트 챗 카드의 얇은 v0를 **실제 detection 진단(`DiagnosisResult`) + 진단용 제안 미리보기(proposal_preview)** 로 풍부화한다. severity·anomaly_type·confidence·hypothesis·예산델타를 표시하되, "이상 없음"과 "진단 불가"를 분리하고, 실행 정본·집행은 **스펙 3**으로 분리한다.

## 1. 배경과 목표

스펙 1로 매니지먼트 답변이 섹션 카드로 렌더되지만, 카드 데이터는 얇다 — `evidence` dict 숫자 + 얇은 `SuggestedAction`(action_type·tier·rationale)뿐이다. 매니지먼트 도메인엔 이미 정식 계약(`DiagnosisResult`·`ActionProposal`)과 detection 파이프라인(`run_detection`)이 있는데 챗 경로가 이를 우회한다.

스펙 2는 챗 어시스턴트에 **진단 능력을 툴 하나로** 꽂아, 실제 `DiagnosisResult`(anomaly_type·confidence·status·hypothesis)와 진단 기반 제안 미리보기를 카드로 흘린다. severity는 `DiagnosisResult`에 없으므로 composer에서 **파생**한다.

### 1.2 비목표 (스펙 3 이후)

- **실행 API**(카드 approve/execute → approval→executor→writer 집행) — **스펙 3**.
- 실제 인증 tenant 연동, 캠페인별 실제 일예산 reader 메서드 — 후속.
- anomaly별 proposal action 정교 매핑 — 후속(현재는 단순화).
- proactive(능동 제안) — 후속.

## 2. 안전·정직성 불변식 (이 스펙의 게이트)

1. **proposal은 "미리보기(preview)"다.** 실행 정본 ActionProposal은 **스펙 3에서만** 생성·확정(finalize)·영속(persist)한다. 스펙 2의 제안은 `executable=false, finalized=false, persisted=false`.
2. **"정식/실행 가능"으로 오인될 어휘 금지.** 카드/계약에서 `ActionProposal`이라 부르지 않고 **`proposal_preview`**, ID는 **`preview_id`**(정본 `proposal_id` 아님)로 노출한다.
3. **이상 없음 ≠ 진단 불가.** fetch 실패·데이터 부족·일예산 미소싱은 "이상 없음"으로 위장하지 않고 **`unavailable`** 로 분리한다.
4. **합성 금지(정직성).** `use_mock=False`(실측)에서 진단 입력(스냅샷·일예산)을 못 구하면 고정값으로 메우지 않고 **`unavailable`** 을 반환한다. 고정 일예산은 `use_mock=True`(데모)에서만 허용.
5. **detection 코어 미수정.** `detection/`의 `run_detection`·`diagnose` 등은 손대지 않고, 챗이 호출하는 **adapter 툴만 추가**한다.
6. **변경 액션 미배선.** approve/execute 액션은 전송하지 않거나 disabled. 실행 정본은 실행 API(스펙 3).

## 3. 진단 상태 모델 — 3 status + anomaly flag (4 cases)

`live_diagnosis` 툴은 `diagnostic_status`(3값) + `anomaly`(ok일 때만 유효) 조합으로 **4 case**를 낸다. 단일 4-값 enum이 아니다.

| diagnostic_status | anomaly | 의미 | 카드 |
|---|---|---|---|
| `ok` | `false` | 진단 완료, 이상 징후 없음 | summary("이상 없음") + metrics |
| `ok` | `true` | 진단 완료, 이상 감지 | summary + metrics + **diagnosis** + **proposal_preview** + review |
| `unavailable` | — | 데이터/설정 부족으로 진단 불가 | summary + `empty_state`("진단 데이터를 가져올 수 없어요"), severity=neutral |
| `failed` | — | 툴 실행 예외 | 안전 문구 반영, diagnosis 섹션 생략 |

툴 결과 형태:
```python
{
  "diagnostic_status": "ok" | "unavailable" | "failed",
  "anomaly": bool,                  # diagnostic_status == "ok"일 때만 유효
  "diagnosis": dict | None,         # DiagnosisResult.model_dump() (ok+anomaly)
  "proposal_preview": dict | None,  # 아래 §4.1 (ok+anomaly)
  "reason": str,                    # unavailable/failed 사유(사용자 표시용 안전 문구)
}
```

## 4. 컴포넌트 — 백엔드

### 4.1 `live_diagnosis` 툴 (신규 adapter)

| 파일 | 책임 |
|---|---|
| `backend/domain/management/assistant/tools.py` | `live_diagnosis(settings, campaign_id) -> dict` + `build_diagnostic_proposal_preview(dx)` 래퍼 + `INTENT_TOOLS["diagnosis"]` 등록 |
| `backend/domain/management/assistant/graph.py` | LLM 바인딩 툴 목록에 `live_diagnosis(campaign_id)` 추가(풀모드) |

**`live_diagnosis(settings, campaign_id)` 흐름**
1. `reader = build_reader(settings)` (mock↔실측 = `use_mock`).
2. `snapshots = await reader.fetch_hourly_metrics(campaign_id, today)`.
3. **일예산 소싱** — `use_mock=True`면 `DAILY_BUDGET_KRW`(데모 고정) 허용. `use_mock=False`면 캠페인 실제 일예산을 구하고, **없으면 `unavailable` 반환**(합성 금지, 불변식 4).
4. 스냅샷이 비었거나 일예산이 없으면 `unavailable`.
5. `outcome = run_detection(tenant_id, campaign_id, snapshots, daily_budget_krw)`. `tenant_id`는 **비인증 placeholder** `org_eval`(detection이 요구하는 데이터-스코핑 파라미터일 뿐, 스펙 2에선 영속·노출 안 함). 실 인증 tenant는 스펙 3+.
6. `outcome.diagnosis is None` → `ok + anomaly=false`. 있으면 `ok + anomaly=true` + `proposal_preview = build_diagnostic_proposal_preview(outcome.diagnosis)`.
7. 전 과정 `try/except` — 예외는 `failed`(raw 미노출, `reason`은 안전 문구). detection 코어는 호출만.

> `campaign_id`는 풀모드에선 LLM이 `live_campaigns`로 얻어 전달, 무키 폴백에선 `req.campaign_id`. 없으면 `unavailable`.

**`build_diagnostic_proposal_preview(dx)`** — 기존 `demo.build_sample_proposal(dx)`를 감싸 **미리보기 전용 dict**로 변환한다. 정본 `ActionProposal`/`proposal_id`를 그대로 노출하지 않고 아래만 추린다.
```python
{
  "preview_id": "preview_<8hex>",         # 정본 ID 아님(휘발성)
  "action_type": "INCREASE_BUDGET",       # 현재 sample 기반(단순화)
  "tier": "TIER_1",                       # sample 라벨
  "budget_before_krw": int,
  "budget_after_krw": int,
  "hypothesis": str,
  "executable": False, "finalized": False, "persisted": False,
  "source": "diagnostic_sample_preview",  # trace: sample 기반임을 명시
}
```

### 4.2 운반 계약 — `AskResult`

`backend/domain/management/assistant/contracts.py` — `AskResult`에 **`diagnostic: dict | None = None`** 한 필드 추가(§3의 4-case 결과 전체). optional·하위호환. graph `to_result`/무키 폴백이 `live_diagnosis` 결과를 여기에 싣는다. 기존 `suggested_action`은 유지(폴백·하위호환).

### 4.3 composer 확장

`backend/domain/management/assistant/composer.py` · `chat_cards/`

- **새 `DiagnosisSection`**(`kind="diagnosis"`: `anomaly_type`·`status`·`confidence`·`hypothesis`) — chat_cards 모델 + 섹션 union에 추가.
- **`proposal_preview`** — `ProposalSection`에 `preview_id`·`budget_before_krw`·`budget_after_krw`·`executable(=false)` 필드 추가(기존 `action_type`·`rationale` 유지). `proposal_id`는 쓰지 않는다.
- **`derive_severity(diagnostic) -> CardStatus`**(단일 헬퍼, 진단만으로 파생) — §6.
- **`compose_card` 분기**(diagnostic 상태별, §3 표):
  - `ok+anomaly` → summary + metrics + diagnosis + proposal_preview(+review).
  - `ok+no-anomaly` → summary + metrics.
  - `unavailable` → summary + `empty_state`(reason).
  - `failed`/`diagnostic=None` → 기존 v0 경로(스펙 1) 그대로(diagnosis 섹션 없음).

## 5. 컴포넌트 — 프론트

| 파일 | 변경 |
|---|---|
| `frontend/src/lib/chatCard.ts` | `CardSection`에 `diagnosis` 변종 추가, `ProposalSection`에 `preview_id`·예산 필드 추가 |
| `frontend/src/components/chat/sections.tsx` | `diagnosis` 렌더러 등록 + `proposal` 렌더러에 preview_id·예산델타·"draft(실행 미연결)" 뱃지 |
| `frontend/src/components/chat/ChatCardView.tsx` | `card.status`(severity) → 헤더 톤 강조(이미 badges/status 자리 있음) |

> 스펙 1의 "새 섹션 = 렌더러 한 개 등록" 구조를 그대로 활용. 미등록 kind 스킵은 전방호환 유지.

## 6. severity 매핑 (파생, 진단만)

스펙 1의 `CardStatus`(`ok|warning|critical|neutral`)·`Tone`만 사용한다. **`info`는 계약에 없으므로 `neutral`로 매핑**(타입 미확장). severity는 "이상의 심각도"라 **진단 속성(status·confidence)만으로 파생**한다 — tier(=액션 위험등급)는 섞지 않는다.

| 조건 | status / tone |
|---|---|
| `status == confirmed` & `confidence ≥ 0.8` | `critical` |
| `status == confirmed` & `confidence < 0.8` | `warning` |
| `inconclusive` · 이상 없음 · `unavailable` · 읽기 전용 | `neutral` |

> anomaly_type별 가중(예 budget_exhausted를 더 심각하게)은 후속 정교화 — v1은 status·confidence만.

## 7. 데이터 흐름

```
질문 → 라우터(management) → assistant
   → (LLM/폴백) live_diagnosis(campaign_id) → 4-case 결과
   → AskResult.diagnostic
   → compose_card: 상태별 섹션 + derive_severity → ChatCard
   → stream_card(summary_delta→card→final) → 프론트 렌더(diagnosis 섹션·severity·proposal preview)
```

## 8. 오류·엣지

- **`unavailable`** — 정상 흐름(오류 아님). `empty_state` 섹션 + neutral. "이상 없음"과 구분.
- **`failed`** — 툴이 `failed` dict 반환(예외를 raw 노출 안 함). **풀모드는 LLM이, 무키 폴백은 composer가** 안전 문구로 반영하고 diagnosis 섹션은 생략. 턴 자체는 정상 종료.
- **실측 모드 일예산 미소싱** — `unavailable`(합성 금지). 현재 reader엔 계정 단위 `get_min_daily_budget`만 있어 실측 모드는 자주 `unavailable` — 한계로 명시(§10).
- **detection 예외** — 코어 미수정. 툴 래퍼에서 잡아 `failed`.

## 9. 테스트

- **`live_diagnosis`**(`tests/management/`) — mock fault 시드 → `ok+anomaly` + proposal_preview(executable=false). mock normal → `ok+anomaly=false`. campaign_id 없음/스냅샷 빔 → `unavailable`. 예외 주입 → `failed`(reason에 raw 미노출).
- **`build_diagnostic_proposal_preview`** — `preview_id` 존재·`proposal_id` 부재·`executable/finalized/persisted=false`·`source` 표기.
- **composer** — `ok+anomaly` → `[summary, metrics?, diagnosis, proposal, review]` + severity. `ok+no-anomaly` → summary+metrics, severity=neutral. `unavailable` → empty_state. `derive_severity` 3분기(진단만). `diagnosis` 섹션이 chat_cards 레지스트리에 등록됨.
- **프론트** — `diagnosis` 렌더러·proposal preview 렌더, severity 톤, 미등록 kind 스킵 유지. lint·build.
- **회귀** — 스펙 1 카드/CLIO 경로 무변경.

## 10. 후속 (스펙 3+)

1. **실행 API(스펙 3)** — 카드 approve/execute → preview(draft)를 입력으로 **정본 ActionProposal을 finalize·persist** → approval→executor→writer 집행. dry_run 우선, HITL, 멱등성. **preview_id는 휘발성이고 스펙 3가 자기 정본 proposal_id를 새로 생성**한다(핸드오프 경계).
2. **캠페인별 실제 일예산 reader 메서드** — 실측 모드 진단의 `unavailable` 해소.
3. **실 인증 tenant 연동** — `org_eval` placeholder 대체(영속·감사 시 필요).
4. anomaly별 proposal action 매핑.