# 매니지먼트 챗 — 제안 집행 브릿지 설계 (스펙 3)

> 작성일 2026-06-25 · 브랜치 `feat/chat-boeun` · 기능 4-2/4-4(매니지먼트 챗) · 슬롯 🅱
> 한 줄 요약 — 스펙 2의 `proposal_preview`(비실행)를 **명시적 버튼 → finalize(정본 생성) → approve/execute(서버 orchestration) → execution_result 카드**로 한 흐름에 닫는다. 정본 본문은 서버에만 머물고(클라는 `proposal_id`만), 기존 승인/집행 플레인을 재사용하며, 결과 카드는 `execution_runs` 정본에서 결정적으로 만든다.

## 1. 배경과 목표

스펙 1로 매니지먼트 답변이 섹션 카드로 렌더되고, 스펙 2로 카드에 실제 진단(`DiagnosticResult`)과 **제안 미리보기**(`proposal_preview`, 실행 미연결)가 실렸다. 그러나 미리보기는 `executable=False`로 잠겨 있고, 사용자가 "응 해줘"라고 해도 집행으로 이어지는 경로가 없다. 스펙 2는 실행 API를 명시적으로 **스펙 3**으로 미뤘다.

스펙 3은 그 미리보기를 **실제 집행까지** 잇는다. 사용자가 챗 안에서 "진단 → 제안 → 승인 → 집행 → 결과 카드"를 끊김 없이 본다. 단, 안전 게이트("LLM은 보여주고, 버튼이 실행한다")와 기존 집행 플레인의 멱등·승인·감사를 그대로 유지한다.

### 1.1 검증 가능한 성공 기준

- preview 카드의 **명시적 "검토·승인" 버튼** → finalize 요청 → 서버가 **최신 진단으로** 정본 `ActionProposal` 생성·영속 → `proposal_id` 반환.
- 그 `proposal_id`로 기존 `approve()` → `executor.execute()`가 **서버 측 orchestration**으로 동작한다(클라는 정본 본문을 들지 않는다).
- 집행 결과는 서버가 **`executor.execute()` 반환 `ActionResult`(1차 정본)** + 영속된 `ActionProposal`(예산·proposal_id)로 **`execution_result` 카드**(구조화 필드 + 결정적 요약)를 만들어 챗에 되돌린다(있으면 `ExecutionRunRow.run_id` 연결, 현재는 None 가능).
- 같은 idempotency key 중복 → 정확히 1회 집행. 만료/이미 실행됨/실패/거절이 각각 구분돼 카드로 표현된다.
- **finalize 시점·approve/execute 시점 양쪽 authz**를 통과한다. 어시스턴트 그래프는 writer/executor를 직접 호출하지 않는다.

### 1.2 비목표 (스펙 4 이후)

- **proactive(능동 제안)** — 서버가 먼저 말 거는 인박스·dedup·트리거(스펙 4).
- **별도 승인자·아웃오브밴드 증빙이 필요한 Tier(예: Tier 3)의 챗 집행** — 스펙 3에서 챗 경로로는 집행하지 않는다(§5.4). 정식 승인 화면으로 안내.
- **재시도 버튼·다중 액션 묶음** — `ActionProposal`(단일 액션) → 묶음 계약 변경 동반(후속).
- **타임라인 UI·로그 펼침·toast 고도화·모바일 polish** — 새 UX 표면(후속).
- **실 Meta 비동기 집행의 폴링 완성** — 본 스펙은 `submitted_pending_review` 상태 카드까지만(폴링은 후속).
- **`execution_runs` 테이블 영속화** — 현재 `state_machine`이 인메모리. 결과 카드는 `ActionResult`로 만들고(§5.5), run 영속 전환은 후속 인프라 작업.

## 2. 안전·정직성 불변식 (이 스펙의 게이트)

1. **LLM은 보여주고, 버튼이 실행한다.** 자연어 "응 해줘"는 카드 강조/의도 확인까지만 — **명시적 UI action(버튼) 없이는 finalize조차 하지 않는다.** 자연어로 finalize까지 가지 않는다.
2. **정본 본문은 서버에만.** `ActionProposal`·`ApprovedAction` 평문을 클라로 왕복시키지 않는다(예산 기밀·변조 방지). 클라는 `proposal_id` + 표시 필드만 받는다.
3. **집행 단일 경로 유지.** 기존 `approve()` + `executor.execute()`를 재사용한다. `approval.py`·`detection/`·`executor.py`·**`ActionProposal` 실행 계약(18필드)** 은 **미수정**. (결과 카드용 새 섹션/계약 추가는 허용.)
4. **정직성.** 최신 진단(스냅샷·일예산)을 못 구하면 정본을 만들지 않고 `unavailable`. "이상 없음 ≠ 진단 불가 ≠ 집행 실패"를 분리한다.
5. **양시점 authz·멱등·TTL·해시 변조 감지**는 기존 플레인 그대로 통과한다(우회 금지). 사전 승인 검사(approval 3단계)와 사후 검사(executor 4단계)의 의도된 중복을 보존한다.

## 3. 아키텍처·데이터플로우

**핵심 결정: 서버 orchestration.** 클라는 `proposal_id` + 표시 필드만 들고, finalize → approve → execute는 서버 라우터가 내부에서 기존 함수(`approve()`·`executor.execute()`)를 호출한다. 정본 본문은 DB·서버에만 머문다.

```
[챗 카드: proposal_preview (preview_id, 비실행)]
        │  ① "검토·승인" 버튼 클릭 (명시적 UI action — 자연어 불가)
        ▼
POST /api/chat/management/proposals/finalize
  body {preview_id, campaign_id, thread_id, shown_budget_after_krw, shown_at, preview_fingerprint}
  · [authz] finalize 시점 — 이 사용자가 이 캠페인 변경 제안 가능?
  · live_diagnosis 재실행(최신 데이터) → DiagnosticResult
       - ok+anomaly 아님 → {status: "unavailable"|"no_anomaly"} (정본 미생성, 카드가 갱신)
  · 최신 진단 → 정본 ActionProposal 조립(🅱 producer) → finalize_proposal(해시)
    → DB 영속(action_proposals, PENDING + expires_at TTL)
  · drift 판정: 최신 budget_after vs shown_budget_after_krw 다르면 drift=true
  → FinalizeResult {status:"finalized", proposal_id, action_type, tier, requires_external_approval,
                    budget_before/after_krw, summary, expires_at, drift}
        │  ② 카드가 "정본 제안"으로 갱신(TTL 카운트다운).
        │     drift면 "값이 갱신됨" + "갱신값 확인" 버튼 1회 후 집행 활성.
        │     사용자가 "집행"(또는 "거절") 버튼 클릭 (명시적)
        ▼
POST /api/chat/management/proposals/{proposal_id}/decision
  body {decision: "approve"|"reject", idempotency_key, thread_id}
  · [authz] execute 시점 재확인(org/tenant 일치)
  · DB에서 proposal 로드 — 가드: 만료 아님·status==PENDING(아니면 expired/already_executed)
  · decision=="reject" → action_proposals REJECTED 표기 + audit → "거절됨" 카드(실행 전 → action_proposals+audit에서 조립)
  · decision=="approve" → approve()→ApprovedAction → executor.execute(action, proposal, idempotency_key)
       → execution_runs 적재 → proposal status 갱신(EXECUTED 등)
  · 결과 카드 조립(§5.5 source of truth 분리) → 챗 이력(management_chat_messages) 적재
  → execution_result 카드
```

**설계 포인트**

- **별도 `sync-execution` 엔드포인트 불필요.** 서버가 execute를 직접 호출하므로 `/decision` 응답이 결과 카드를 동기 반환한다. (실 Meta 비동기면 `submitted_pending_review` 카드로 표현, 폴링은 후속.)
- **proposal 영속**: `ExecutionService`의 `ProposalRepository` 포트는 **유지**하고, **DB-backed `ProposalRepository` 구현(action_proposals)을 추가**한다. 챗 finalize/decision 경로와 기존 실행 API가 **같은 repository를 주입**받도록 전환한다 — 전면 교체가 아니라 구현 추가 + 주입. 마이그레이션 없음(테이블 기존).
- **단일 결정 엔드포인트**(`/decision` with `approve|reject`)로 기존 `/approve`의 `approved: bool` 패턴과 일치, 거절도 audit에 남는다.
- **위치**: `management.py`(2800줄+)에 더 얹지 않고 **새 포커스 라우터** `api/routers/chat_management.py` 신설. `main.py`는 append-only include 1줄.

## 4. preview_id 와 정본 proposal_id 경계 (명시)

| | preview_id | proposal_id |
|---|---|---|
| 생성 | 스펙 2 `build_proposal_preview_from_diagnosis` | 스펙 3 finalize |
| 영속 | **안 함**(휘발성) | `action_proposals` DB |
| 용도 | **trace/anti-stale·drift 비교 기준 식별** | 정본 집행 lookup 키 |
| 관계 | `proposal_id != preview_id` (절대 재사용 금지) | finalize가 **새로** 발급 |

- finalize는 `preview_id`로 무엇도 **lookup하지 않는다.** 정본은 `campaign_id` 기반 **최신 진단 재실행**으로 만든다.
- body의 `shown_budget_after_krw`·`shown_at`·`preview_fingerprint`는 **클라가 본 값**으로, **신뢰 대상이 아니라 drift 비교에만** 쓴다("사용자가 본 것과 최신 정본이 얼마나 달라졌나").

## 5. 백엔드 컴포넌트·계약

| # | 컴포넌트 | 파일(소유) | 책임 |
|---|---|---|---|
| 1 | chat_management 라우터(신규) | `api/routers/chat_management.py` (🅱) | `/proposals/finalize`, `/proposals/{id}/decision`. deps: `get_current_user`·`get_db`·`settings`, org/tenant authz. main.py append-only include |
| 2 | 정본 proposal 빌더(신규) | `domain/management/execution/proposal_builder.py` (🅱) | `build_action_proposal_from_diagnosis(dx, ctx) -> ActionProposal` — anomaly→action_type·예산델타·tier·TTL·state_version 매핑. `finalize_proposal`로 해시. 입력 못 구하면 정본 미생성 |
| 3 | DB ProposalRepository(신규 구현) | `domain/management/execution/service/` (🅱) | `DbProposalRepository(ProposalRepository)` — `action_proposals`(ActionProposalRow) get/save. 포트 유지, 챗·실행 경로에 주입 |
| 4 | 결과 카드 빌더 | `domain/management/assistant/composer.py` (🅱) | `ExecutionResultSection` + 결정적 요약 조립. source는 §5.5대로(1차 정본=`ActionResult`, 예산·proposal_id=영속 `ActionProposal`, 실행 전 terminal=`ActionProposalRow`+`AuditEventRow`). LLM 미경유 |
| 5 | 새 카드 섹션 계약 | `domain/management/assistant/chat_cards/models.py` (공유 카드 계약) | `ExecutionResultSection` 추가 → `CardSection` union. FE 렌더러도 대응 |
| 6 | 상태·에러 매핑 | composer/router (🅱) | ResultStatus·FailureReason·ProposalStatus → 카드 status + 안전 문구. 결정적 |
| 7 | 결과 이력 적재 | router (🅱) | execution_result 카드를 `management_chat_messages`에 적재(JSON 직렬화) |

### 5.1 새 계약 — `ExecutionResultSection`

```python
class ExecutionResultSection(BaseModel):
    kind: Literal["execution_result"] = "execution_result"
    title: str | None = None
    action_type: str
    result_status: Literal[
        "success", "submitted_pending_review", "failed", "rejected", "expired", "already_executed"
    ]
    proposal_id: str                   # 정본 lookup 키(노출 가능) — preview_id→proposal_id→run_id 추적
    preview_id: str | None = None      # optional trace(어느 미리보기에서 왔는지)
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    run_id: str | None = None          # execution_runs 정본 키(집행된 경우)
    summary: str                       # 서버 결정적 요약(한두 줄)
    failure_reason: str | None = None  # 안전 문구(실패/만료/거절 시)
```

### 5.2 finalize 응답 — `FinalizeResult` (로컬 계약, assistant/contracts.py)

`{status, proposal_id?, action_type?, tier?, requires_external_approval?, budget_before_krw?, budget_after_krw?, summary?, expires_at?, drift?, reason?}`
정본 본문(`ActionProposal`)은 **미포함**(서버 DB에만).

> **`requires_external_approval` 의미 고정** — 이 제안이 **챗 밖의 별도 승인(별도 승인자·아웃오브밴드 증빙)이 필요해 챗에서 집행 불가**함을 뜻한다. **버튼 클릭 = HITL 승인 행위**(§5.4)와는 별개 축이다. `false`면 사용자의 "집행" 버튼 한 번으로 충분(챗 집행 가능), `true`면 챗 집행 대상이 아님(FE는 정식 승인 화면 안내). "사용자 승인으로 충분한 제안"과 "챗에서 처리 못 하는 제안"을 이 필드 하나로만 가른다.

### 5.3 상태 어휘 분리 규칙 (절대 안 섞음)

두 단계의 상태는 **별도 enum, 교집합 없음**. finalize는 결코 execution_result 상태를 내지 않고, 그 반대도 없다.

- **finalize 상태(제안 생성 단계)**: `finalized` | `unavailable` | `no_anomaly`
- **execution_result 상태(집행 단계)**: 아래는 `ExecutionResultSection.result_status`(섹션 자체 필드)다. **카드 status 열은 기존 `CardStatus = ok|warning|critical|neutral`** 에 매핑한 값으로, `CardStatus`/`Tone` 계약은 확장하지 않는다(`success`는 result_status 값일 뿐 CardStatus가 아니다 → 카드 레벨은 `ok`로 매핑).

| 경로 | result_status | 카드 status(CardStatus) | 비고 |
|---|---|---|---|
| 집행 성공 | `success` | `ok` | run_id·전후값 표시 |
| 실 Meta 비동기 | `submitted_pending_review` | `warning` | "제출됨/검토중", 폴링은 후속 |
| executor 실패 | `failed` | `critical` | failure_reason 안전 문구 |
| 정책 거부(Tier 증빙 부족 등) 또는 사용자 거절 | `rejected` | `neutral` | approve()가 거부 시 §5.4. audit 기록 |
| TTL 만료 후 시도 | `expired` | `neutral` | 재진단 유도 |
| 이미 실행됨(EXECUTED/STALE) | `already_executed` | `neutral` | 멱등 — 중복 클릭/재시도 방어 |

### 5.4 승인·Tier 계약 (버튼 의미·Tier3 처리)

- **"집행" 버튼 한 번 = "승인 + 집행" 단일 의도.** 그 클릭이 HITL 승인 *행위*이고, 서버는 `approve(proposal, approver_id=current_user)` → `executor.execute(...)` 순서로 실행한다. 승인의 *정책 권위*는 여전히 `approval.py`(🅰)이며 스펙 3은 정책을 바꾸지 않는다.
- **decision body에 approval_proof를 받지 않는다(스펙 3 비목표).** 별도 승인자·아웃오브밴드 증빙이 필요한 Tier(예: Tier 3)는 **챗 집행 대상이 아니다.**
- **처리 방식**: finalize 응답 `requires_external_approval=true`(챗 집행 불가)면 **FE는 "집행" 버튼 대신 "정식 승인 화면으로" 안내**를 띄운다. 방어적으로 그래도 `decision=approve`가 들어오면 `approve()`가 거부하고 → 결과 카드 `rejected`(failure_reason="정식 승인 경로 필요") 로 닫힌다. 즉 **"Tier 3는 스펙 3에서 챗 집행 불가"** 를 정책(approve())이 강제하며 우회는 없다(게이트 #4).
- Tier 1(자동승인 한도 내)·단일 승인자로 통과하는 제안만 챗에서 집행된다.
- **`requires_external_approval=true`여도 정본은 영속한다.** 정식 승인 화면이 `proposal_id`로 인계받아야 하므로 finalize는 `ActionProposalRow`에 **`PENDING`으로 저장**한다(`ProposalStatus`엔 external 전용 상태가 없으므로 새로 만들지 않는다 — 잠금 계약 존중). 챗은 집행만 막고, 영속·핸드오프는 그대로.

### 5.5 결과 카드 source of truth (실행 여부로 분리)

**1차 정본은 `executor.execute()`가 같은 요청에서 반환한 `ActionResult`다.** `execution_runs` 테이블은 아직 쓰는 코드가 없으므로(`state_machine`이 인메모리), run 조회를 카드의 전제로 삼지 않는다. (정본 테이블/ORM: 제안 `ActionProposalRow`/`action_proposals`, 감사 `AuditEventRow`/`audit_events`, 승인 `ApprovalRow`/`approvals`. 실행 `ExecutionRunRow`/`execution_runs`는 **있으면 연결**용.)

| result_status | source of truth |
|---|---|
| `success` · `submitted_pending_review` · `failed` | **`ActionResult`(executor 반환, 1차 정본)** — status·failure_reason·snapshot. 예산·`proposal_id`는 영속 `ActionProposal`에서. `ExecutionRunRow`가 있으면 `run_id` 연결, 없으면 `run_id=None` |
| `rejected` · `expired` · (실행 전) `already_executed` | **`ActionProposalRow` + `AuditEventRow`** 에서 결정적으로 조립(executor 미호출 → `ActionResult` 없음, `run_id=None`) |

규칙
- 어느 경로든 **LLM 미경유·결정적**. 예산 전후·`action_type`·`proposal_id`는 항상 영속 `ActionProposal`에서 읽는다.
- **`failed`는 근거 없이 카드를 만들지 않는다.** executor가 `ActionResult`를 반환하면 그걸로 조립한다. 만약 executor가 `ActionResult` 반환 전 예외로 죽으면, 라우터가 **실패를 `AuditEventRow`로 반드시 남긴 뒤** 그 audit에서 `failed` 카드를 조립한다(`run_id=None` 허용). "근거 없는 실패 카드" 금지.
- **`execution_runs` 영속화는 본 스펙 비목표(후속 인프라 작업).** 들어오면 `run_id` 연결만 자연히 채워진다.

## 6. idempotency

- key scope = **`(proposal_id, idempotency_key)`** (authz는 user_id). 같은 proposal에서 같은 key는 1회로 수렴, 다른 proposal과 충돌하지 않는다.
- **approve 경로**: 기존 executor 멱등(`idempotency_keys` 테이블)으로 **정확히 1회 집행**.
- **reject 경로도 멱등**: `PENDING → REJECTED` 1회 전이, 반복 호출은 에러 없이 현재 `REJECTED` 상태를 반환.
- **클라 idempotency_key 규칙**: **한 클릭당 1개 생성**. 네트워크 실패 후 **재시도는 동일 key**(같은 의도), 사용자가 **새로 다시 누르는 새 의도는 새 key**.

## 7. 프론트엔드 (필수 안전 상태만, 기존 카드 스타일로 마감)

- **proposal(preview) 섹션** — `preview_id`·권한 있을 때만 **"검토·승인" 버튼**(명시적 UI action) → finalize 호출. 자연어로는 이 버튼 없이 finalize 안 됨.
- **finalize 후 "정본 제안" 상태** — 예산 전후·tier·**TTL 카운트다운**·"집행"/"거절" 버튼. `drift=true`면 "값이 갱신됨" 강조 + **"갱신값 확인" 버튼을 1회 누른 뒤에만 "집행" 활성**(2-step confirm).
- **execution_result 섹션(신규 렌더러)** — status 배지(6종)·전후값·run_id·요약·실패 문구.
- **안전 상태** — finalize·decision 진행 중 **로딩/disabled(중복 클릭 방지)**; idempotency_key는 §6 규칙대로 전송; TTL 만료 → 집행 disable + "만료, 재요청"(재-finalize); already_executed/rejected → 종결 상태(버튼 제거); failed → 안전 문구.
- **파일** — 카드 섹션 렌더러(스펙 `2026-06-25-chat-card-section-renderer`) + `types.ts`에 `execution_result` 컴포넌트·proposal 버튼·finalize/decision API. 기존 카드 스타일 재사용.
- **후속(FE)** — 타임라인·재시도 버튼·로그 펼침·toast 고도화·모바일 polish.

## 8. 결과 카드 영속·재조회 (FE/BE 계약)

- **모든 terminal `/decision` 결과를 적재한다.** `success`·`submitted_pending_review`·`failed`·`rejected`·`expired`·`already_executed` 6종 모두, 서버가 `execution_result` 카드를 `management_chat_messages`에 1건 적재한다(role="assistant", `content`=카드 JSON 직렬화). 스키마 변경 없음.
- **회귀 기준**: 세션 재조회 시 저장된 카드 JSON을 역직렬화해 **라이브 스트림과 동일 렌더**가 나와야 한다.
- **의존성/리스크**: 카드 이력 재조회(GET messages → 카드 역직렬화) 경로가 아직 스텁(`/sessions/{id}/messages`)이라, 저장된 카드 JSON을 `ChatCard`로 복원하는 **최소 역직렬화**가 스펙 3 BE 범위에 포함된다. 전체 이력 UI·페이지네이션은 후속.

## 9. 테스트 게이트

**백엔드**
1. 같은 idempotency_key 10회 → 정확히 1회 집행.
2. 만료 proposal 집행 차단(`expired`).
3. 타 org/tenant는 **finalize·decision 양쪽** 거부.
4. **Tier3/chat-ineligible proposal returns `requires_external_approval=true` at finalize, and a defensive `decision=approve` maps to `rejected` by `approve()`** (body에 approval_proof 없음 — §5.4, enforcement 유지).
5. reject 멱등 — `PENDING→REJECTED` 1회 전이, 반복은 `REJECTED` 반환.
6. finalize 최신 진단 재실행 — ok+anomaly만 정본 생성, unavailable/no_anomaly는 정본 미생성.
7. **`proposal_id != preview_id`** — finalize 응답의 `proposal_id`는 정본이며 `preview_id`를 재사용하지 않는다(preview_id는 trace/fingerprint 비교에만).
8. drift — `shown_budget_after_krw` ≠ 최신 → `drift=true`.
9. 결과 카드는 **`ActionResult` + 영속 `ActionProposal`에서 결정적 생성(LLM 미경유)**, 6상태 매핑 — 실행 전 terminal(expired/rejected)은 `ActionProposalRow`+`AuditEventRow`에서 `run_id=None`으로 조립, run row가 있으면 `run_id` 연결(§5.5).
10. 어시스턴트 그래프가 writer/executor 직접 호출 안 함(import-purity).
11. 결과 카드 적재·재조회 동일 렌더(§8 회귀 기준).
12. executor가 run 적재 전 예외 → 라우터가 `AuditEventRow`를 남기고 그 audit에서 `failed` 카드 조립(run 없는 failed 카드는 audit 필수, §5.5).
13. `requires_external_approval=true` 제안도 `ActionProposalRow`에 `PENDING`으로 영속(정식 승인 UI 인계용) — 챗 집행만 차단.

**프론트**
- finalize·decision 진행 중 버튼 disable, 이중 클릭 시 decision 1회.
- drift 시 "갱신값 확인" 전 집행 비활성.
- TTL 만료 시 집행 disable.
- `requires_external_approval=true`(챗 집행 불가)면 집행 버튼 대신 "정식 승인 화면으로" 안내 노출.
- execution_result 6상태 렌더(proposal_id 표시 포함).

## 10. 경계·소유권

- **🅱(수정)**: 신규 라우터, `execution/proposal_builder.py`, `execution/service` DB repo, `assistant/composer` 결과 빌더, `chat_cards` 섹션, FE 카드 렌더러.
- **미수정(잠금/🅰)**: `approval.py`·`detection/`·`executor.py`·`ActionProposal`(18필드).
- **공유**: `chat_cards/models.py`(FE+BE 카드 계약) 섹션 추가, `core/models.py` **변경 없음**(테이블 기존), `main.py` include append-only 1줄.

## 11. 스펙 4 전망

proactive(능동 제안): 서버 발신 인박스·dedup·트리거 진화. 스펙 3의 **finalize/decision/결과-카드 루프를 그대로 재사용**해 "서버가 먼저 제안 카드를 띄움"으로 확장한다. 재시도·다중 액션 묶음(`ActionProposal` 단일 → 묶음 계약 변경)은 그다음.
