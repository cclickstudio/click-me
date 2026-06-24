# 채팅 카드 구조 + Composer 아키텍처 설계

> 작성일 2026-06-24 · 브랜치 `chat-boeun` · 기능 4-4(채팅 AI 어시스턴트)
> 한 줄 요약 — 채팅 한 턴의 응답을 "결론 + 타입이 붙은 카드 리스트"로 구조화하고, 백엔드 Composer가 정책·권한·상태를 검증해 안정적인 카드 봉투를 조립한다. 매니지먼트 전용(A)으로 시작해 시뮬·생성(B)으로 확장한다.

## 1. 배경과 목표

기능 4-4 채팅은 자유질문 + 시뮬·분석·생성 결과 전달이 목표다. 현재 상태:

- `api/routers/chat.py` — CLIO 페르소나 + Gemini, 매니지먼트 키워드를 서브에이전트로 라우팅하는 임시 오케스트레이션.
- `domain/management/assistant/` — LangGraph 서브에이전트(`agent.py`·`graph.py`), 행동 제안(`actions.py`), RAG(`retriever.py`), 정책 KB(`kb/meta_ad_policy.md` 등).

목표는 채팅 UX를 "긴 마크다운 한 덩어리"가 아니라 **결론 → 근거 → 결과 → 검수 → 액션**의 구조화된 카드로 제공하는 것. 단 이 구조가 매니지먼트에 고착되지 않고 시뮬·생성으로 확장 가능해야 한다.

### 비목표 (YAGNI)

- 공통 오케스트레이터 본체 구현 — 후순위(미정). 본 설계는 기존 키워드 라우팅 위에 카드 계약을 얹는다.
- 시뮬·생성 카드 페이로드의 실제 구현 — B 단계. 본 설계는 **확장점만** 정의한다.
- A/B·YouTube RAG 등 타 기능 연동.

## 2. 단계 전략 (A → B)

- **A 단계(본 작업 범위)** — 매니지먼트 어시스턴트 전용. `evidence`·`result`·`review`·`actionbar` 카드를 기존 `management/assistant` 산출물로 채운다.
- **B 단계(후속)** — 통합 CLIO. 턴 종류에 따라 `result` 카드의 `payload.type`만 달라진다(시뮬=`kpi_distribution`, 생성=`variants`). 프론트 렌더러·레이아웃·액션바·SSE 계약은 **변경 없이 재사용**.

통일성은 UI 코드가 아니라 **데이터 계약 수준**에서 보장된다.

## 3. 아키텍처

```
LLM / Agent (management/assistant)
  → 판단·근거·제안 "재료"만 생성 (UI JSON 직접 생성 금지)

Backend Composer  ← 신뢰 경계(trust boundary)
  → 재료를 카드 envelope로 조립
  → 정책 / 권한 / 상태 / 제안서 링크 검증
  → 안정적인 카드 JSON + SSE 이벤트 emit

Frontend
  → kind + payload.type 기준 렌더링 (고정 슬롯)
  → 상태 조회 / 저장 / 승인 / 실행 액션을 별도 API로 연결
```

**역할 분리의 핵심** — LLM은 비결정적 재료 생성자, Composer는 결정론적 검증·조립자. 정책 게이트(검수 → 실행)는 LLM 텍스트가 아니라 Composer/실행 엔드포인트에서 서버측으로 강제된다.

## 4. 데이터 계약

### 4.1 턴 응답 구조 (논리 모델)

```jsonc
{
  "turn_id": "turn_123",
  "conclusion": "최근 7일 기준 A 캠페인은 ...",   // 항상, 서술만
  "cards": [
    { "kind": "evidence",  "status": "ok", "payload": { "type": "rag_citations",   "version": 1, ... } },
    { "kind": "result",    "status": "ok", "payload": { "type": "action_proposal", "version": 1, ... } },
    { "kind": "review",    "status": "ok", "payload": { "type": "policy_check",     "version": 1, ... } },
    { "kind": "actionbar", "status": "ok", "payload": { "type": "actions",          "version": 1, "actions": [ ... ] } }
  ]
}
```

- `conclusion`은 항상 존재. 나머지 카드는 **그 턴이 실제로 생성했을 때만** 포함(progressive disclosure). 빈 카드 금지.
- 카드 `status` ∈ `ok | degraded | failed`.
- **능동 제안용 필드(§10)** — 턴은 `origin` ∈ `user | proactive`, 그리고 `proactive`일 때 `trigger`(`{anomaly, campaign_id, escalation_step}`)·`read_state` ∈ `unread | read`를 가진다. 사용자 발화 턴은 `origin="user"`, 나머지 필드 생략.

### 4.2 kind — 닫힌 집합 (슬롯)

| kind | 슬롯 의미 | 렌더 위치 |
|---|---|---|
| `evidence` | 데이터·가정·판단 이유(RAG 근거) | 결론 아래 1번 |
| `result` | 광고안·시뮬레이션·액션 제안 등 산출물 | 2번 |
| `review` | Meta 정책·한국 광고 표현·리스크 검수 | 3번 |
| `actionbar` | 저장/수정/승인/실행/다시 생성 | 최하단(고정) |

새 `kind` 추가는 드물고 신중해야 함(프론트 슬롯 레이아웃 변경 동반).

### 4.3 payload.type + version — 열린 확장점 (A→B 계약)

`kind`별 허용 `payload.type`과 `version`을 `contracts/chat_cards/` 패키지에 **레지스트리**로 둔다. 레지스트리 키는 `(kind, type, version)`. 버전은 처음부터 박는다(예시 단계 포함) — 마이그레이션·동시지원·검증이 문자열 임베딩보다 깔끔하다.

| kind | A 단계 (type, version) | B 단계 추가 예 |
|---|---|---|
| `evidence` | `rag_citations` v1 | `metric_window` v1 |
| `result` | `action_proposal` v1 | `kpi_distribution` v1(시뮬), `variants` v1(생성) |
| `review` | `policy_check` v1 | (공통 재사용) |
| `actionbar` | `actions` v1 | (공통 재사용) |

B에서 시뮬 팀이 `result.kpi_distribution` v1을 추가할 때 **레지스트리에 등록 + 프론트에 해당 type 렌더러 추가**만 하면 된다. 슬롯·SSE·액션바는 무변경.

**레지스트리는 순수해야 한다** — `chat_cards`는 management 내부를 import하지 않는다(import 0개). 그래야 B에서 시뮬/생성 도메인이 management 내부에 의존하지 않고(협업 규칙: 타 도메인 내부 직접 import 금지) 계약만 공유할 수 있다. A 단계에선 `domain/management/assistant/contracts/chat_cards/`에 두되, B 진입 시 중립 위치로 **이동(move)만** 하면 되도록 의존성을 비워 둔다.

## 5. SSE 이벤트 (2단계 스트리밍)

처음에 결론을 빠르게 보여주고, 카드는 Composer 검증이 끝난 순서대로 붙인다. **`final`은 어떤 경우에도 항상 보낸다** — 클라이언트는 늘 종료 이벤트를 받고, `status`로 결과를 판별한다.

```jsonc
{ "event": "conclusion_delta", "text": "최근 7일 기준 A 캠페인은..." }   // 토큰 스트리밍, 0..N회
{ "event": "card_ready", "card": { "kind": "evidence", "status": "ok", ... } }
{ "event": "card_ready", "card": { "kind": "result",   "status": "degraded", ... } }   // 카드 단위 실패
{ "event": "card_ready", "card": { "kind": "review",   "status": "ok", ... } }
{ "event": "card_ready", "card": { "kind": "actionbar", "status": "ok", ... } }
{ "event": "final", "turn_id": "turn_123", "status": "partial" }
```

`final.status` ∈ `ok | partial | failed`:

- `ok` — 모든 카드 정상.
- `partial` — 턴은 끝났지만 일부 카드가 `degraded`/`failed`. (이 값이 없으면 클라이언트가 "다 정상"과 "끝났지만 근거 카드 깨짐"을 구분 못 함.)
- `failed` — 턴 자체 실패(아래 §6-④).

이벤트 순서 규칙:

1. `conclusion_delta`가 먼저(빠른 체감). `card_ready`는 검증 완료 순.
2. **`actionbar` 카드는 `review` 계산 이후 항상 마지막에 emit**(액션 가용성이 검수 결과에 의존).
3. `final`은 턴 종료 신호 + `turn_id` 상관키. 후속 액션 호출이 이 키를 참조.

## 6. 설계에 못박는 4개 불변식

칭찬만 하고 넘어가면 나중에 터지는 지점들. 명시적으로 강제한다.

### ① Composer 검증은 UI 안전장치, 실행 권한의 정본은 실행 API

`actionbar`의 `실행` 버튼 노출은 **UI 안전장치**일 뿐 권한의 정본(source of truth)이 아니다. 실행 권한의 정본은 **실행 API**다. 실제 실행은 별도 API 요청이며 그 엔드포인트가 정책·상태를 **다시 검증**한다. 액션은 `proposal_id`를 들고 `turn_id` 기준으로 호출, 서버가 재검증·멱등 처리. 프론트 페이로드를 authz로 신뢰하지 않는다.

### ② 프론트는 "도착 순서"가 아니라 "고정 슬롯"에 렌더링

`card_ready`가 result→evidence 순으로 와도 레이아웃이 튀면 안 된다. 슬롯 순서(결론/근거/결과/검수/액션)는 프론트 고정, 도착은 **스켈레톤 → 채우기**로 처리.

### ③ conclusion은 검증 안 된 LLM 텍스트 — 단정·행동 지시 금지

`conclusion_delta`는 Composer 검증을 건너뛴 생짜 텍스트다. 결론이 "지금 실행하면 됩니다"라 했는데 뒤따른 `review`가 정책 위반 fail이면 자기모순. → **결론은 서술(describe)만, 행동 가능한 주장은 전부 카드에**. 시스템 프롬프트로 유도 + Composer가 위반 의심 시 강등/경고.

### ④ 부분 실패는 카드 단위 / 턴 단위로 세분화

조용히 빠뜨리지 않는다.

- **카드 단위 실패** — 해당 카드를 `card_ready`로 emit하되 `status`를 `failed` 또는 `degraded`로. 나머지 카드는 정상 진행. `final.status`는 `partial`.
- **턴 단위 실패** — `error` 이벤트(아래) 후 `final(status="failed")`. 카드는 가능한 만큼만.

```jsonc
{ "event": "error", "scope": "turn", "code": "policy_engine_unavailable", "message": "..." }
{ "event": "final", "turn_id": "turn_123", "status": "failed" }
```

`error.scope` ∈ `turn`(턴 중단) · `card`(카드 한정, 보통 `card_ready` status로 충분하나 부가 설명용). `error.code`는 머신 가독 코드(예: `policy_engine_unavailable`·`agent_timeout`)로 프론트가 분기 처리.

## 7. 컴포넌트 경계

| 컴포넌트 | 책임 | 의존 | 위치(제안) |
|---|---|---|---|
| Agent | 재료(판단·근거·제안) 생성 | LLM, RAG | `domain/management/assistant/` (기존) |
| Composer | 봉투 조립·검증·SSE emit | Agent 출력, `campaign_policy`·`target_check`·`approval` | `domain/management/assistant/composer.py` (신규) |
| 카드 계약(레지스트리) | kind·payload.type·version 스키마 | 없음(순수, import 0) | `domain/management/assistant/contracts/chat_cards/` (신규) |
| Chat 라우터 | SSE 전송·라우팅 | Composer | `api/routers/chat.py` (기존) |
| 트리거 invoker | demo/scheduled/SQS가 `re_evaluate` 호출(§10.3) | detection·escalation | `domain/management/assistant/proactive.py` (신규, 얇은 seam) |
| 전달(delivery) 포트 | 능동 턴을 인박스(지금)·푸시(미구현)로 전달 | 영속 turn | 인박스 어댑터만 구현, 푸시 포트는 자리만 |
| Frontend 렌더러 | kind+type별 카드 렌더·액션 연결·능동 턴 인박스 | 카드 계약(타입 공유) | `frontend/` (신규) |

각 단위 검증 질문 — 무엇을 하는가 / 어떻게 쓰는가 / 무엇에 의존하는가가 한 문장으로 답되어야 한다. Composer 내부를 안 읽어도 "재료를 검증된 카드 봉투로 바꾼다"로 이해 가능해야 한다.

## 8. 검증 기준 (성공 조건)

- 매니지먼트 질문 한 턴에 대해 `conclusion_delta` → `card_ready`(evidence/result/review/actionbar) → `final(status=ok)` 순으로 SSE가 흐른다.
- `review`가 정책 위반(fail)이면 `actionbar`의 `실행`이 비활성 + 사유 표시, 실행 엔드포인트도 거부한다.
- `actionbar` 페이로드를 조작해 실행을 호출해도 서버가 재검증으로 차단한다.
- `card_ready` 도착 순서를 뒤섞어도 프론트 슬롯 레이아웃이 고정 유지된다(스켈레톤 테스트).
- evidence 단계만 실패시켜도 result/actionbar는 정상 렌더, evidence는 `degraded/failed`로 표시되고 `final.status=partial`.
- 정책 엔진 다운 시 `error(scope=turn)` + `final(status=failed)`가 전달된다.
- `result.payload.type`/`version`이 미등록이면 계약 레벨에서 거부(또는 안전한 fallback 렌더).
- **능동 제안** — 진단 트리거 시 `origin="proactive"` 턴이 영속되고 인박스에 `unread`로 뜬다(사용자 미접속에도 보존). 같은 anomaly/step이 미회복으로 매 tick 반복돼도 새 턴이 중복 생성되지 않는다(dedup). step이 올라가면 새 능동 턴 1건 생성. 능동 제안의 `실행`도 사용자 제안과 동일하게 실행 API 재검증으로만 집행된다(자동 집행 없음).

## 9. 테스트 전략

- **Composer 단위** — 정책 통과/위반 케이스별로 조립된 봉투의 `actionbar.actions`와 `review.status`를 검증(TDD).
- **SSE 통합** — 이벤트 순서·`actionbar` 마지막 보장·`final` 항상 송신·`status` 3값 분기 검증.
- **불변식 회귀** — ①~④ 각각에 실패 테스트 1개 이상(①: 실행 엔드포인트 재검증, ②: 슬롯 고정, ④: 카드/턴 실패 분리).
- **계약** — `(kind, type, version)` 레지스트리 등록/미등록 케이스, `chat_cards`가 management를 import하지 않는지 의존성 테스트.
- **프론트** — kind+type 렌더러 스냅샷, 도착 순서 셔플 시 레이아웃 안정성.

## 10. 능동 제안 (Proactive)

사용자가 묻지 않아도 진단이 걸리면 채팅이 먼저 조치를 제안한다. 채팅을 **수동 응답형 → 능동 제안형**으로 확장.

### 10.1 핵심 — "사용자 메시지 없는 턴"

§3~§9의 카드 봉투/Composer/불변식을 **그대로 재사용**한다. 바뀌는 건 트리거 출처와 전달 경로뿐.

```
진단 트리거 (demo tick / scheduled tick / SQS consumer)
  → detection (deterministic_dx·performance_dx·guardrails)
  → escalation.re_evaluate() → ActionProposal      // 전송 독립 순수 함수, HITL 강제
  → Composer (동일)
  → turn = {
       origin: "proactive",
       trigger: { anomaly, campaign_id, escalation_step },
       read_state: "unread",
       conclusion: "A 캠페인 예산 페이싱 이상 감지 — 조치 제안",   // 서술만(불변식 ③)
       cards: [ evidence, result(action_proposal), review(policy_check), actionbar ]
     }
  → 영속(history) + (선택)전달
```

이미 `escalation.re_evaluate`가 ActionProposal을 만들고 HITL을 강제하므로(승인 없는 자동 집행 없음), **능동 제안 = 제안만 자동, 실행은 여전히 승인 + 실행 API 재검증(불변식 ①)**.

### 10.2 단계 — 지금 (가), 설계 방향 (다)

- **지금 구현 (가) 인박스/알림 영속** — 능동 턴을 DB 영속(`history.py` 턴 기록 확장), 알림 배지·제안 피드로 표시. 사용자가 접속 안 해도 안 사라짐.
- **설계 방향 (다) 영속 + 라이브 푸시** — 푸시는 **전달(delivery) 포트의 자리만** 정의하고 미구현. (다)로 설계하면 (가) 대비 달라지는 3가지(모두 저렴):

  1. **영속이 정본, 푸시는 선택적 전달 포트.** 능동 턴 생성은 열린 SSE 연결에 의존하지 않는다(생성 = detection→Composer→영속으로 종료). `re_evaluate`가 전송 독립이라 자연 충족. UI는 인박스 엔드포인트에서 능동 턴을 읽고, 푸시는 "새 턴 있음 → refetch" 신호 또는 턴 동봉 — 카드 페이로드는 동일.
  2. **턴 스키마에 `origin`/`trigger`/`read_state`(§4.1).** read_state는 인박스용이면서 푸시에도 호환.
  3. **중복 억제(dedup) — (가)만 보면 빠뜨리는 함정.** scheduled/SQS는 같은 anomaly로 매 tick 반복 발화 → 인박스 도배. dedup 키 = **escalation state 재사용**(`campaign, anomaly, escalation_step`). escalation이 이미 회복 판정(목록 멤버십)을 가지므로 "같은 step 미회복이면 새 턴 생성 안 함, step이 올라갈 때만 새 능동 턴" 규칙으로 연결.

### 10.3 트리거 진화

`demo tick → scheduled tick → SQS consumer` 순. 셋 다 **동일한 `re_evaluate`를 호출**하고 다른 건 호출자(invoker)뿐. invoker만 교체 가능한 얇은 seam으로 두면 생성 로직 무변경으로 진화(escalation 설계 의도와 일치).

### 10.4 불변식 재확인

능동 제안도 §6 ①~④ 그대로 적용. 특히 ① 실행 권한 정본=실행 API(자동 집행 없음, escalation HITL과 일치), ③ 결론은 "감지됨"까지만 서술하고 "실행하라" 단정 금지.

## 11. 미해결/후속

- 액션 실행 엔드포인트의 멱등키 설계(`proposal_id` + `turn_id` 조합) — 구현 계획에서 구체화.
- conclusion 강등 정책의 정확한 트리거(휴리스틱 vs Composer 후처리) — 1차는 시스템 프롬프트 + 사후 경고로 시작.
- B 단계 시뮬/생성 payload.type 스키마 + `chat_cards` 중립 위치 이동(공통부 변경 → 협업 규칙상 사전 공지) — 본 설계 범위 밖.
