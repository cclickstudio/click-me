# 채팅 카드 — 범용 섹션 렌더러 + ChatCard 계약 설계 (스펙 1)

> 작성일 2026-06-25 · 브랜치 `feat/chat-boeun` · 기능 4-4(채팅 AI 어시스턴트)
> 한 줄 요약 — 채팅 카드를 도메인 비종속 `ChatCard{sections[]}` 한 벌로 재정의하고, 프론트는 섹션 `kind`만 보고 그리는 범용 렌더러로, 백엔드 composer는 도메인 결과를 섹션으로 normalize하는 adapter로 둔다. 이 스펙은 **계약 + 범용 렌더러 + 현재 데이터 기준 management adapter v0** 까지다. 실제 진단·제안 데이터 풍부화와 관측(트레이싱)은 스펙 2.

## 1. 배경과 목표

### 1.1 지금 깨진 곳

백엔드 management 챗은 카드 SSE를 보내는데, 프론트 `(app)/chat/page.tsx`의 SSE 소비부는 CLIO용 `token`/`done`/`meta`만 처리한다. 그래서 매니지먼트 키워드 질문은 **서버는 답을 보내는데 프론트가 형식을 못 읽어 화면이 빈 채로 멈춘다**(게다가 종료 이벤트를 못 받아 스피너도 안 멈춤). 이게 사용자가 겪은 "답이 안 옴"의 정체다.

### 1.2 목표

- 챗 카드를 **도메인 필드(`severity`·`anomaly_type`·`budget_delta`)에 직접 의존하지 않는** 범용 구조로 정의한다.
- 프론트는 **섹션 `kind`만 보고 렌더**한다. 모르는 `kind`는 스킵(전방호환).
- 백엔드 composer가 **도메인 결과를 섹션으로 변환**한다. 없는 값은 섹션을 생략한다.
- "이상 없음"도 정직하게 표현한다(제안·검수 섹션 없이 결론+지표만).
- 같은 렌더러를 리포트·QA·운영 승인 등 다른 기능이 섹션 조합만 바꿔 재사용한다.

### 1.3 비목표 (스펙 2 이후)

- 실제 `DiagnosisResult`/`ActionProposal` 계약 연동, `live_diagnosis` 진단 툴, severity 산출 — **스펙 2**.
- LangSmith 트레이싱(진단 툴·LLM·비용 기록) — **스펙 2**(이 스펙의 composer는 LLM 없는 순수 변환이라 추적 비대상). CLIO 경로 토큰 기록 갭은 별도 소규모 후속.
- 변경(mutating) 액션 실행 배선 — 실행 API 후속.
- sim/gen 도메인 카드, 멀티도메인 분해 — 오케스트레이션 후속.

이 스펙은 **현재 management 어시스턴트가 이미 내놓는 데이터**(결론 prose + `evidence` dict 숫자 + 얇은 `SuggestedAction` + citations)만으로 끝까지 동작한다. 끝나면 챗이 즉시 살아나고, 스펙 2는 이 렌더러에 더 풍부한 데이터만 채운다.

## 2. 설계 원칙

1. **프론트는 도메인을 모른다.** `ChatCard.sections`의 `kind`만 안다. `severity`·`confidence` 같은 도메인 필드는 백엔드가 표시용 `status`/`tone`으로 번역해 넣는다.
2. **백엔드 composer = 도메인 adapter.** 도메인 결과 → 섹션. 단일 변환 지점.
3. **없으면 생략.** 제안이 없으면 proposal 섹션을 안 만든다. 진단이 없으면 summary + metrics만.
4. **표시용과 원본의 분리.** `status`/`tone`/`badges`는 표시용. 원본 도메인 데이터가 필요하면 `trace.raw`에만 둔다(아래 보안 규칙 준수).
5. **전방호환.** 프론트는 아는 섹션 `kind`만 그리고 모르는 건 스킵한다. 새 섹션(`chart`·`table`)을 나중에 추가해도 구버전 프론트가 안 깨진다.

## 3. 공유 계약 — ChatCard / CardSection

프론트(TS)와 백엔드(Python)가 **이 한 벌에만 코딩**한다. seam이다.

```ts
type Tone = "neutral" | "muted" | "success" | "warning" | "critical";
type CardStatus = "ok" | "warning" | "critical" | "neutral";

type Badge = { label: string; tone: Tone };
type MetricItem = { label: string; value: string; hint?: string }; // value는 포맷 완료된 표시 문자열
type KeyValueItem = { key: string; value: string };
type Citation = { kind: string; source: string; title?: string };
type TraceInfo = { turn_id?: string; raw?: Record<string, unknown> };

type CardSection =
  | { kind: "summary"; title?: string; text: string }
  | { kind: "metrics"; title?: string; items: MetricItem[] }
  | { kind: "entity"; title?: string; items: KeyValueItem[] }
  | { kind: "proposal"; title?: string; action_type: string; rationale?: string; proposal_id?: string }
  | { kind: "review"; title?: string; decision: string; rationale?: string }
  | { kind: "evidence"; title?: string; citations?: Citation[]; used_tools?: string[] }
  | { kind: "empty_state"; title?: string; text: string };

type ChatCard = {
  version: 1;                 // 현재 v1만. v2 나오면 리터럴 union(1 | 2)으로 확장
  type: "management" | "report" | "qa" | "generic"; // 생산 기능. 렌더는 sections가 끈다(type은 헤더 라벨/아이콘만)
  title?: string;
  status?: CardStatus;        // 표시용 — 도메인 severity의 번역 결과(스펙 2). v0에선 보통 생략/neutral
  badges?: Badge[];
  sections: CardSection[];
  actions?: never;            // 스펙 1 미전송. 변경 액션 실행 정본은 실행 API — CardAction은 실행 스펙에서 정의
  trace?: TraceInfo;
};
```

- **숫자는 표시 문자열로 보낸다.** `MetricItem.value = "29,082원"`처럼 포맷을 백엔드가 끝낸다. 프론트는 통화·로케일 포맷을 모른다.
- **`metrics`는 표시 문자열만.** `raw_value`(원시 숫자) 필드를 추가하지 않는다. 스펙 2에서 차트·비교가 필요해지면 `metrics`를 부풀리지 말고 **새 `chart`/`table` 섹션으로 확장**한다(섹션 레지스트리 전방호환 그대로).
- **`actions` 비전송** — TS는 `actions?: never`. **Python/Pydantic 계약은 "`actions` 필드를 v1에서 serialize하지 않는다"**(모델에 두더라도 `exclude` 또는 미직렬화). 변경 액션 실행 정본은 실행 API다(불변식 ①).
- **`trace.raw` — v0은 아예 안 보낸다(보수).** v0엔 소비자가 없고 필요한 건 `turn_id`뿐이라 `trace = {turn_id}`만 보낸다. **못 보내는 건 못 새므로** 비밀 누출 표면이 0. `raw`가 실제로 필요해지는 **스펙 2를 대비해** `chat_cards`에 `TRACE_RAW_ALLOWLIST = {"turn_id", "period", ...}` 상수와 **allowlist 통과 함수**만 미리 두고(composer가 raw를 담을 땐 이 함수만 거치게), 토큰·계정 비밀·식별자·원본 대량 row는 영구 제외(루트 규칙). **테스트로 강제**(§8).
- 파이썬 측은 Pydantic v2 모델로 같은 형태(섹션은 `kind` discriminated union, `Field(discriminator="kind")`).

## 4. 와이어 포맷 (SSE)

management 턴의 SSE를 **`kind` 단일 디스크리미네이터**로 새로 간다.

```
data: {"kind":"summary_delta","text":"이번 달 캠페인 예산 소진은 29,082원"}
data: {"kind":"summary_delta","text":"이며, 월말 예상 34,898원입니다."}
data: {"kind":"card","payload":{ ...ChatCard }}
data: {"kind":"final","turn_id":"mgmt-...","status":"ok"}
```

- **`summary_delta`** — 결론 텍스트를 청크로 흘린다(챗 UX). 프론트는 현재 어시스턴트 메시지의 스트리밍 버퍼에 누적.
- **`card`** — 완성된 `ChatCard`(summary 섹션에 결론 전체 포함). 프론트는 스트리밍 버퍼를 이 카드로 **교체**.
- **`final`** — `status ∈ {ok, partial, failed}`. **카드 protocol의 종료 신호 = CLIO `done`과 동일.** 항상 송신. 프론트는 이걸로 스트리밍 종료(스피너 해제).
- **상태 불변식(프론트 상태 처리 단순화)** — `partial`은 **`card`가 이미 전송된 상태에서만** 나온다(일부 섹션 degraded/누락). **`error`는 항상 `failed`** 로 끝난다(`error` + `partial` 조합은 없음). 정리 — `ok`/`partial` ⇒ `card` 도착함, `failed` ⇒ `card` 없을 수 있음(error 본문 표시).
- **오류** — `data: {"kind":"error","scope":"turn","message":"..."}` 후 `final`(status=failed). 정상 종료로 위장하지 않는다. **`error.message`는 raw exception이 아니라 사용자 표시용 안전 문구**(예 "매니지먼트 조회 중 문제가 발생했어요.")로 제한한다. 원인 상세는 서버 로그/trace로만(비밀·스택 노출 금지).

**기존 포맷 교체 전제 — 안정 소비자 없음.** 기존 `event`/`conclusion_delta`/`card_ready` 포맷을 끌고 가지 않고 교체한다. 전제는 "이 포맷의 안정 소비자가 프론트에 없다"이며, **구현 전 검증 항목**으로 둔다. (작성 시점 확인 — `frontend/src` 전체에 `card_ready`/`conclusion_delta`/`result`/`evidence`/`actionbar` 소비처 0건, `token`/`done`/`meta`만 소비.)

CLIO(Gemini/OpenAI) 분기는 **기존 `meta`/`token`/`done` 그대로.** 프론트는 `data.kind`가 있으면 카드 프로토콜, 없으면 CLIO 프로토콜로 분기.

## 5. 컴포넌트

### 5.1 프론트 — 범용 섹션 렌더러

| 파일 | 책임 |
|---|---|
| `frontend/src/lib/chatCard.ts` | `ChatCard`·`CardSection` 등 공유 타입(계약) + 타입 가드 |
| `frontend/src/components/chat/ChatCardView.tsx` | `ChatCard` 한 장 렌더 — 헤더(title·badges·status) + `sections.map`으로 섹션 위임 |
| `frontend/src/components/chat/sections/*.tsx` | 섹션 `kind`별 렌더러. `SECTION_RENDERERS` 레지스트리로 매핑, 미등록 `kind`는 `null` 반환(렌더 스킵). dev 환경에서는 `console.debug`로 미등록 `kind`를 남김(telemetry) |
| `frontend/src/app/(app)/chat/page.tsx` | SSE 루프에 `kind` 분기 추가 — `summary_delta`/`card`/`final`/`error`. `Message`에 `card?: ChatCard` 필드 |

- 렌더 규칙은 **섹션 레지스트리**(`Record<kind, Renderer>`). 새 섹션 추가 = 렌더러 한 개 등록. 미등록은 스킵(전방호환).
- `tone`/`status`는 색 클래스로만 매핑(기존 토스 팔레트 재사용). 의미 추론 없음.
- **`card` 없이 `final(failed)`만 온 경우** — 프론트는 `error` 메시지를 **assistant 메시지 본문**으로 표시(빈 버블 방지).

### 5.2 백엔드 — management adapter (v0, 현재 데이터)

| 파일 | 책임 |
|---|---|
| `backend/domain/management/assistant/chat_cards/` | 섹션 기반으로 **재작성** — `ChatCard`·`CardSection`(discriminated)·`Tone`·`CardStatus` Pydantic 모델. 기존 kind/slot 모델·`(kind,type,version)` 레지스트리 폐기 |
| `backend/domain/management/assistant/composer.py` | **재작성** — `compose_card(AskResult) -> ChatCard`(도메인→섹션 normalize) + `stream_card(card)`(summary_delta→card→final SSE) |
| `backend/api/routers/chat.py` | `_management_card_stream`을 새 `compose_card`/`stream_card`에 맞게 수정 |

**현재 데이터 → 섹션 매핑(v0)**

- `AskResult.answer`(서술 가드 통과) → `summary` 섹션.
- `AskResult.evidence`(dict: `this_month_spent_krw`·`runrate_projection_krw`·`account_balance_krw`·`period`) → `metrics` 섹션(값은 `"29,082원"` 포맷). 비면 생략.
- `AskResult.suggested_action`(있으면) → `proposal` 섹션(`action_type`·`rationale`) + `review` 섹션(`decision = needs_approval|auto_ok`). 없으면 둘 다 생략 → **이상 없음/읽기 전용**.
- `AskResult.citations`/`used_tools` → `evidence` 섹션. 비면 생략.
- 배지(v0) — `tier`·`stage(draft)`·`decision`을 가진 만큼만. severity/색 `status`는 **스펙 2**.
- `trace = {turn_id: thread_id}`만. **`raw` 미전송**(v0 보수 — §3).

> v0는 데이터에 없는 걸 만들지 않는다. severity·anomaly_type·confidence·예산델타·"이상 없음 정직 판정"은 스펙 2에서 `live_diagnosis` 툴이 실제 `DiagnosisResult`/`ActionProposal`을 실어오면 같은 섹션 구조에 채워진다.

## 6. 데이터 흐름

```
질문 → 라우터(management) → assistant.ask → AskResult
   → composer.compose_card(AskResult) → ChatCard(sections)
   → stream_card: summary_delta×N → card → final   (SSE)
   → 프론트: summary 버퍼 누적 → card 도착 시 ChatCardView로 교체 → final 종료
```

## 7. 오류·엣지

- **어시스턴트/조립 실패** — `error`(scope=turn) + `final`(failed). 프론트는 error 본문 표시(§5.1).
- **이상 없음/제안 없음** — `summary` + `metrics`만. 정상 흐름. 필요시 `empty_state` 섹션으로 명시.
- **모르는 섹션 `kind`** — 프론트 렌더 스킵 + dev `console.debug`. 나머지 섹션 정상.
- **부분 실패(`final.status=partial`)** — 일부 섹션 누락이어도 카드는 보낸다. 받은 섹션만 그린다.
- **적재(record_turn) 실패** — best-effort, 답변 스트림 안 끊음(기존 동작 보존).

## 8. 테스트

- **백엔드 composer**(`tests/management/`) — 재작성. ① 제안 있는 AskResult → `[summary, metrics?, proposal, review, evidence?]` 섹션·순서. ② 제안 없는 AskResult → `[summary, metrics?]`만(이상 없음). ③ evidence 비면 metrics 생략. ④ 서술 가드 유지. ⑤ `stream_card` 시퀀스 = `summary_delta`+ → `card` → `final`, 오류 = `error` → `final(failed)`. ⑥ **v0 출력에 `trace.raw`가 없음**(turn_id만). 그리고 `TRACE_RAW_ALLOWLIST` 통과 함수가 allowlist 밖 키를 떨어뜨리는지(스펙 2 대비 단위 테스트). ⑦ **`error.message`에 raw exception 문자열이 안 새는지**(안전 문구 고정). ⑧ `actions` 필드가 직렬화 출력에 없는지.
- **프론트** — `ChatCardView`/섹션 렌더러 단위 테스트(있으면). 미등록 `kind` 스킵 검증. `card` 없이 `final(failed)` → error 본문 표시. 최소 빌드(`pnpm build`)·수동 확인(매니지먼트 질문 → 카드, 일반 질문 → CLIO 토큰).
- **회귀** — CLIO `token`/`done` 경로 무변경 확인.

## 9. 구현 전 검증 항목

- [ ] `frontend/src` 전체에 `card_ready`/`conclusion_delta`/`result`/`evidence`/`actionbar` 소비처 0건 재확인(교체 전제).
- [ ] 기존 `chat_cards`/`composer`/`composer 테스트` 의존처 목록화(재작성 영향 범위).

## 10. 후속 (스펙 2 — management adapter 풍부화 + 관측)

1. `live_diagnosis(settings, campaign_id)` 툴 — `build_reader(settings).fetch_hourly_metrics` → `run_detection` → `DiagnosisResult`(+`build_sample_proposal`→`ActionProposal`). 출처는 `use_mock` 따름(실측이면 정직한 "이상 없음", mock이면 데모).
2. `AskResult`에 구조화 `diagnosis`/`proposal` 운반(loose evidence dict 대체).
3. composer가 `DiagnosisResult`/`ActionProposal`을 섹션으로 — anomaly_type·confidence·hypothesis·예산델타·`proposal_id`·`metrics_as_of`.
4. `derive_severity(confidence, status, tier)` → `ChatCard.status`/`badges.tone`(표시용 번역, 단일 헬퍼).
5. `fetch_hourly_metrics`를 reader 포트(`contracts/platform.py`)로 승격(소규모 contracts 변경).
6. **관측(LangSmith)** — `docs/management` LangSmith 가이드 준수. `live_diagnosis`·진단 LLM을 `core.tracing.make_trace_config`로 표준 run_name(`management.assistant`)·tags·metadata 부착. 어시스턴트 fallback(mock) 경로·CLIO(OpenAI/Gemini) 토큰 기록 갭(`get_current_run_tree().set(usage_metadata=...)`)도 함께 메움.
