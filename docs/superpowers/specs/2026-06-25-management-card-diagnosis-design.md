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

1. **proposal은 "미리보기(preview)"다.** 실행 정본 ActionProposal은 **스펙 3에서만** 생성·확정(finalize)·영속(persist)한다. 스펙 2의 제안은 `executable=false, finalized=false, persisted=false`. **스펙 2는 정본 `ActionProposal` 모델을 메모리에도 생성하지 않는다** — preview는 `DiagnosisResult`에서 직접 조립한다(`build_sample_proposal`/`finalize_proposal` 미사용).
2. **"정식/실행 가능"으로 오인될 어휘 금지.** 카드/계약에서 `ActionProposal`이라 부르지 않고 **`proposal_preview`**, ID는 **`preview_id`**(정본 `proposal_id` 아님)로 노출한다.
3. **이상 없음 ≠ 진단 불가.** fetch 실패·데이터 부족·일예산 미소싱은 "이상 없음"으로 위장하지 않고 **`unavailable`** 로 분리한다.
4. **합성 금지(정직성).** `use_mock=False`(실측)에서 진단 입력(스냅샷·일예산)을 못 구하면 고정값으로 메우지 않고 **`unavailable`** 을 반환한다. 고정 일예산은 `use_mock=True`(데모)에서만 허용.
5. **detection 코어 미수정.** `detection/`의 `run_detection`·`diagnose` 등은 손대지 않고, 챗이 호출하는 **adapter 툴만 추가**한다.
6. **변경 액션 미배선.** approve/execute 액션은 전송하지 않거나 disabled. 실행 정본은 실행 API(스펙 3).

## 3. 진단 상태 모델 — 3 status + anomaly flag (4 cases)

`live_diagnosis` 툴은 `diagnostic_status`(3값) + `anomaly`(ok일 때만 유효) 조합으로 **4 case**를 낸다. 단일 4-값 enum이 아니다. **이 조합은 typed 모델 `DiagnosticResult`의 validator로 강제**한다(§4.2) — 불법 조합(`ok+no-anomaly`인데 proposal_preview 존재, `unavailable`인데 diagnosis 존재 등)은 생성 시점에 거부된다.

| diagnostic_status | anomaly | 의미 | 카드 |
|---|---|---|---|
| `ok` | `false` | 진단 완료, 이상 징후 없음 | summary("이상 없음") + metrics |
| `ok` | `true` | 진단 완료, 이상 감지 | summary + metrics + **diagnosis** + **proposal_preview** + review |
| `unavailable` | — | 데이터/설정 부족으로 진단 불가 | **composer가 결정적으로** summary + `empty_state`("진단 데이터를 가져올 수 없어요"), severity=neutral |
| `failed` | — | 툴 실행 예외 | **composer가 결정적으로** summary + `empty_state`(안전 문구), severity=neutral. diagnosis 섹션 생략 |

> `unavailable`·`failed`의 **카드 표현은 composer가 결정적으로** 만든다(empty_state + neutral). LLM은 사용자-facing summary 텍스트만 보조하고, **실패/불가 상태를 카드 계약으로 소유하지 않는다**(LLM 경유 비결정성 배제).

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
| `backend/domain/management/assistant/tools.py` | `live_diagnosis(settings, campaign_id, tenant_id=None) -> DiagnosticResult` + `build_proposal_preview_from_diagnosis(dx, daily_budget_krw)` + `INTENT_TOOLS["diagnosis"]` 등록 |
| `backend/domain/management/assistant/graph.py` | LLM 바인딩 툴 목록에 `live_diagnosis(campaign_id)` 추가(풀모드) |

**`live_diagnosis(settings, campaign_id)` 흐름**
1. `reader = build_reader(settings)` (mock↔실측 = `use_mock`).
2. `snapshots = await reader.fetch_hourly_metrics(campaign_id, today)`.
3. **일예산 소싱** — `use_mock=True`면 `DAILY_BUDGET_KRW`(데모 고정) 허용. `use_mock=False`면 캠페인 실제 일예산을 구하고, **없으면 `unavailable` 반환**(합성 금지, 불변식 4).
4. 스냅샷이 비었거나 일예산이 없으면 `unavailable`.
5. **외부 호출만 `try/except`** — `build_reader().fetch_hourly_metrics(campaign_id, datetime.now(UTC))` + `run_detection(...)`만 try로 감싸 reader/detection **I/O 실패만 `failed`**(raw 미노출)로 변환한다. **결과 조립·`DiagnosticResult`/`ProposalPreview` 생성은 try 밖** — validator·빌더 버그는 raise되게 둔다(계약 결함을 failed로 삼키지 않음). 기준 시각은 **UTC**. `tenant_id`는 detection이 출력 라벨로만 쓴다(검증: `deterministic_dx.py:89`·`performance_dx.py:106` — config 조회 미사용). 요청 tenant 있으면 전달, 없으면 `org_eval`(비인증 placeholder, 영속·노출 안 함, 실 tenant는 스펙 3+).
6. **guard.verdict 매핑(불변식 3 — 이상없음≠진단불가)** — `INSUFFICIENT_DATA`(또는 스냅샷 빔) → **`unavailable`**(판단 보류, "이상 없음"으로 위장 금지). `NORMAL`(diagnosis None) → `ok+anomaly=false`. `DELIVERY_ANOMALY`(diagnosis 존재) → `ok+anomaly=true` + `build_proposal_preview_from_diagnosis(dx, daily_budget)`. 부분일/희소 데이터는 guard의 `INSUFFICIENT_DATA`가 걸러 `unavailable`로. 계정 타임존 정렬은 스펙 3+.

> `campaign_id`는 풀모드에선 LLM이 `live_campaigns`로 얻어 전달, 무키 폴백에선 `req.campaign_id`. 없으면 `unavailable`.

**`build_proposal_preview_from_diagnosis(dx, daily_budget_krw) -> ProposalPreview`** — **정본 `ActionProposal`을 만들지 않고**(불변식 1) `DiagnosisResult`에서 직접 `ProposalPreview`(typed)를 조립한다. `build_sample_proposal`/`finalize_proposal`은 호출하지 않는다. 필드:
```python
{
  "preview_id": "preview_<8hex>",         # 정본 ID 아님(휘발성). uuid4 즉석 생성.
  "action_type": <anomaly_type→action 매핑>,  # v1 단순 매핑(예 budget_exhausted→INCREASE_BUDGET)
  "tier": <action별 기본 tier>,           # 표시용 라벨(정책 판정 아님)
  "budget_before_krw": daily_budget_krw,
  "budget_after_krw": <heuristic, 예 *1.5>,
  "hypothesis": dx.hypothesis,
  "executable": False, "finalized": False, "persisted": False,
  "source": "diagnostic_preview",         # trace: 미리보기 출처 명시
}
```

### 4.2 운반 계약 — `AskResult`

`backend/domain/management/assistant/contracts.py` — **중첩까지 typed**: `DiagnosisView`(표시 필드만) · `ProposalPreview`(정본 아님/실행 불가를 타입으로 잠금) · `DiagnosticResult`(4-case validator). `AskResult`에 **`diagnostic: DiagnosticResult | None = None`** 추가(optional·하위호환). raw dict가 아니라 모델로 불법 값/조합을 생성 시점에 거부한다.

```python
class DiagnosisView(BaseModel):           # 카드용 표시 필드만(정보 최소화)
    anomaly_type: str; status: str; confidence: float; hypothesis: str = ""

class ProposalPreview(BaseModel):         # 불변식 1·2를 타입으로 잠금
    model_config = ConfigDict(extra="forbid")   # proposal_id 등 정본 키 주입 거부
    preview_id: str; action_type: str; tier: str | None = None
    budget_before_krw: int | None = None; budget_after_krw: int | None = None; hypothesis: str = ""
    executable: Literal[False] = False; finalized: Literal[False] = False
    persisted: Literal[False] = False; source: Literal["diagnostic_preview"] = "diagnostic_preview"

class DiagnosticResult(BaseModel):
    diagnostic_status: Literal["ok", "unavailable", "failed"]
    anomaly: bool = False
    diagnosis: DiagnosisView | None = None
    proposal_preview: ProposalPreview | None = None
    reason: str = ""

    @model_validator(mode="after")
    def _legal_combo(self):
        if self.diagnostic_status != "ok":           # 진단 불가/실패
            if self.diagnosis or self.proposal_preview: raise ValueError("payload forbidden")
            if not self.reason: raise ValueError("reason required")
            if self.anomaly: raise ValueError("anomaly must be False")
        elif self.anomaly:                           # ok+anomaly ⇒ 둘 다 필수(카드 계약 일치)
            if self.diagnosis is None or self.proposal_preview is None:
                raise ValueError("ok+anomaly requires diagnosis AND proposal_preview")
        else:                                        # ok+no-anomaly
            if self.diagnosis or self.proposal_preview: raise ValueError("payload forbidden")
        return self
```
> `ProposalPreview`는 `executable/finalized/persisted = Literal[False]` + `extra="forbid"`로 **executable=True·proposal_id 주입을 타입 에러**로 막는다(불변식 1·2를 코드로 잠금). graph `to_result`/무키 폴백이 `DiagnosticResult`를 `AskResult.diagnostic`에 싣는다. 기존 `suggested_action` 유지.

### 4.3 composer 확장

`backend/domain/management/assistant/composer.py` · `chat_cards/`

- **새 `DiagnosisSection`**(`kind="diagnosis"`: `anomaly_type`·`status`·`confidence`·`hypothesis`) — chat_cards 모델 + 섹션 union에 추가.
- **`proposal_preview`** — `ProposalSection`에 `preview_id`·`budget_before_krw`·`budget_after_krw`·`executable(=false)` 필드 추가(기존 `action_type`·`rationale` 유지). `proposal_id`는 쓰지 않는다.
- **`derive_severity(diagnostic) -> CardStatus`**(단일 헬퍼, 진단만으로 파생) — §6.
- **`compose_card` 분기**(diagnostic 상태별, §3 표):
  - `ok+anomaly` → summary + metrics + diagnosis + proposal_preview(+review).
  - `ok+no-anomaly` → summary + metrics.
  - `unavailable` → summary + `empty_state`(reason), severity=neutral. **(composer 결정적)**
  - `failed` → summary + `empty_state`(안전 문구), severity=neutral. **(composer 결정적, LLM 미경유)**
  - `diagnostic is None`(진단 툴 미호출 — 일반 질문) → 기존 v0 경로(스펙 1) 그대로(diagnosis 섹션 없음).

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

- **`INSUFFICIENT_DATA`(guard) / 스냅샷 빔 / 부분일** — `ok+no-anomaly`("이상 없음")로 보내지 않고 **`unavailable`**(판단 보류). 불변식 3의 핵심 경계.
- **`unavailable`** — 정상 흐름(오류 아님). `empty_state` 섹션 + neutral. "이상 없음"과 구분.
- **`failed`** — 툴이 `failed` 상태 반환(예외 raw 미노출). **composer가 결정적으로** empty_state + neutral로 표현(LLM 미경유). LLM은 summary 텍스트만 보조. 턴 자체는 정상 종료.
- **실측 모드 일예산 미소싱** — `unavailable`(합성 금지). 현재 reader엔 계정 단위 `get_min_daily_budget`만 있어 실측 모드는 자주 `unavailable` — 한계로 명시(§10).
- **detection 예외** — 코어 미수정. 툴 래퍼에서 잡아 `failed`.

## 9. 테스트

- **`live_diagnosis`**(`tests/management/`) — mock fault 시드 → `ok+anomaly` + proposal_preview(executable=false). mock normal → `ok+anomaly=false`. campaign_id 없음/스냅샷 빔 → `unavailable`. 예외 주입 → `failed`(reason에 raw 미노출).
- **`DiagnosticResult` validator** — 불법 조합 거부: `unavailable`인데 diagnosis 있음 / `ok+no-anomaly`인데 proposal_preview 있음 / `failed`인데 reason 빔 → ValueError.
- **`build_proposal_preview_from_diagnosis`** — `preview_id` 존재·`proposal_id`/`ActionProposal` 미생성·`executable/finalized/persisted=false`·`source` 표기. (정본 모델을 안 만드는지: `build_sample_proposal`/`finalize_proposal` 미호출 확인.)
- **composer** — `ok+anomaly` → `[summary, metrics?, diagnosis, proposal, review]` + severity. `ok+no-anomaly` → summary+metrics, severity=neutral. `unavailable`·`failed` → summary+empty_state, severity=neutral(둘 다 composer 결정적, LLM 미경유). `diagnostic=None` → v0 경로. `derive_severity` 3분기(진단만, tier 미사용). `diagnosis` 섹션이 chat_cards 레지스트리에 등록됨.
- **프론트** — `diagnosis` 렌더러·proposal preview 렌더, severity 톤, 미등록 kind 스킵 유지. lint·build.
- **회귀** — 스펙 1 카드/CLIO 경로 무변경.

## 10. 후속 (스펙 3+)

1. **실행 API(스펙 3)** — 카드 approve/execute → preview(draft)를 입력으로 **정본 ActionProposal을 finalize·persist** → approval→executor→writer 집행. dry_run 우선, HITL, 멱등성. **preview_id는 휘발성이고 스펙 3가 자기 정본 proposal_id를 새로 생성**한다(핸드오프 경계).
2. **캠페인별 실제 일예산 reader 메서드** — 실측 모드 진단의 `unavailable` 해소.
3. **실 인증 tenant 연동** — `org_eval` placeholder 대체(영속·감사 시 필요).
4. anomaly별 proposal action 매핑.