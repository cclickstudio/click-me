# 페르소나 반응 — 배치 API 구현 전략

> 반응 생성(4-b)의 LLM 비용을 50% 절감하기 위한 배치 API 도입 설계·전략.
> 선행: [PERSONA_LLM_COST_STRATEGY.md](./PERSONA_LLM_COST_STRATEGY.md) (비용·모델 선택 검토).
> 결론: **배치 API는 "N콜을 독립 유지한 채 비동기로 절반값에" 돌리는 것이다. 프롬프트 묶기(동질화 위험)와
> 다르고, SQS(우리 잡 오케스트레이션)와도 별개이며 함께 쓴다. 대규모 실행에만 적용하는 이유는 온라인 코드가
> 손상돼서가 아니라 지연 허용도·절감 규모가 대규모에서만 맞기 때문이다.** (작성일: 2026-06-17)

---

## 0. TL;DR

1. **배치 API ≠ 프롬프트 묶기.** 배치는 요청 수를 줄이지 않는다(100명=100요청). 토큰 단가를 50% 깎고
   비동기로 돌릴 뿐, 각 페르소나는 독립 컨텍스트를 유지한다. → 다양성 보존.
2. **배치 API ≠ SQS.** 배치는 *provider*(Gemini/OpenAI/Claude)의 비용 할인 비동기 엔드포인트. SQS는 *우리*
   잡 큐. 둘은 대체재가 아니라 **층이 다른 보완재** — SQS가 "런 접수·배치 상태 폴링"을 맡고, 배치 API가
   "싼 LLM 처리"를 맡는다.
3. **대규모만 배치, 소규모는 온라인.** 이유는 코드 손상이 아니라 (지연 허용도 + 절감 규모)가 대규모에서만
   맞아서다. 온라인 경로 보존은 *부차적 이점*이지 *이유*가 아니다.
4. **구현은 공유 로직 추출 + 비동기 경계에서 그래프 분할 + SQS 폴러.** 기존 온라인 코드는 손대지 않고
   프롬프트 조립·파싱만 공유로 빼서 양쪽이 함께 쓴다.

---

## 1. 용어 정리 — 배치 API vs 프롬프트 묶기 (헷갈리기 쉬운 1지점)

> 나중에 또 헷갈릴 수 있어 박아둔다. "10개 페르소나를 한 번에 호출"이라는 말이 두 가지를 의미할 수 있다.

### 1.1 두 개념은 완전히 다르다

| | **프롬프트 묶기** (multi-persona-in-one-call) | **배치 API** (이 문서가 말하는 것) |
|---|---|---|
| 호출 수 | 10콜 → 1콜 (감소) | 100요청 그대로 |
| 컨텍스트 | 10명이 **한 컨텍스트 공유** | 페르소나마다 **독립** |
| 절약 원천 | 호출 수 ↓ | 토큰 단가 50% ↓ (실시간 포기 대가) |
| 응답 시점 | 즉시 | 비동기 (보통 분~시간, 최대 24h) |
| 다양성 | **오염 위험** | 보존 |

### 1.2 프롬프트 묶기를 쓰지 않는 이유 (금지)

이게 더 싸 보이지만 **이 프로젝트가 싸우는 실패 모드를 정확히 부른다.**

- 10명을 한 컨텍스트에 넣으면 **서로의 응답에 오염**된다(앞 반응이 뒤에 영향) → Persona Collapse(동질화)
  가속. PERSONA §7의 "클러스터를 대표답으로 축약 금지"와 같은 결의 위반.
- 출력 길이 제한, 구조화 JSON 깨짐(10개 분량 한 번에), 한 명 오류가 전체 응답을 망침.
- 다양성은 단계 1~3에서 데이터로 강제해 놨는데, 출력단에서 한 컨텍스트에 몰면 그 다양성이 다시 뭉개진다.

→ **배치 API는 "독립성 유지하며 싸게"라 안전, 프롬프트 묶기는 "싸지만 동질화"라 철학과 충돌.**

---

## 2. 배치 API vs SQS — 별개이고 함께 쓴다 (헷갈리기 쉬운 2지점)

같은 "비동기"라는 단어 때문에 SQS로 배치를 대체할 수 있다고 오해하기 쉽다. **불가능하다.**

| | **SQS** (우리 인프라) | **배치 API** (provider 인프라) |
|---|---|---|
| 소유 | 우리 (AWS 계정) | Gemini/OpenAI/Anthropic |
| 역할 | 런 요청 큐잉·워커 분배·재시도·DLQ·**배치 상태 폴링 스케줄** | N개 요청을 싸게 비동기 처리 |
| 50% 할인 | ✗ (큐일 뿐) | ✅ |
| LLM과 통신 | ✗ | ✅ |

### 2.1 그래서 SQS로 "비동기"가 되나

**된다 — 단, SQS는 *우리 쪽* 비동기 오케스트레이션을 맡고, 배치 할인은 못 준다.** 둘은 스택처럼 쌓인다.

```
[HTTP 요청] 시뮬 실행
   │  (즉시 run_id 반환, 블로킹 X)
   ▼
SQS 런 큐  ──► 워커: 프롬프트 N개 조립 → Gemini Batch 제출 → batch_job_id 저장(status=PENDING_BATCH)
   │
   ▼
SQS 폴링(지연 메시지)  ──► 폴러: batch 상태 확인
        │ 미완료 → 지연 재투입(루프)
        │ 완료   → 결과 N개 회수 → 집계 → 영속화 → 완료 알림(SSE)
        ▼
     [DLQ] 실패 격리
```

> 현재 코드: 비동기를 `asyncio.create_task`(인프로세스)로 처리(`simulation_service.start`). SQS는
> `config`·`.env.example`에 **설정만 존재, 워커 미구현.** 배치 도입이 SQS 실착수의 자연스러운 계기가 된다.

---

## 3. 왜 대규모 실행에만 배치인가 — 진짜 이유

질문: "배치를 대규모에서만 쓰는 건 기존 온라인 호출 코드가 손상돼서인가?"
**아니다.** 코드 손상이 이유가 아니라, 다음 두 축이 대규모에서만 맞아떨어지기 때문이다.

| 축 | 소규모 미리보기 (≤50명) | 대규모 본실행 (300~1,000명) |
|---|---|---|
| **지연 허용도** | 즉답 필요(SSE로 한 명씩 스트리밍 보며 확인) | "제출하고 나중에 보기"가 자연스러움(1,000명을 실시간으로 안 봄) |
| **절감 규모** | 50%를 깎아도 절대액 미미 → 비동기 복잡도 손해 | 콜이 많아 50% 절감액이 큼 → 도입 가치 |

→ 즉 **배치 적합성은 "런 크기"가 아니라 "지연 허용도 × 절감 규모"의 함수**이고, 그게 대규모와 정렬된다.

### 3.1 "온라인 코드 보존"은 이유가 아니라 부차적 이점

온라인 경로를 남기는 건 (a) 즉시 미리보기 UX, (b) 데모 핵심인 실시간 SSE 경험, (c) "수술적 변경"
원칙(작동 코드 유지) 때문이다. 이건 하이브리드 선택의 *결과*지 배치를 대규모로 미는 *원인*이 아니다.

### 3.2 손상 없이 가는 설계 — 공유 로직 추출

배치와 온라인은 **같은 프롬프트 조립·파싱**을 쓴다(`reaction.py`의 `_prompt()`·`PersonaReaction` 파싱).
이걸 공유 함수로 빼면 코드를 **복제하거나 손상하지 않고** 양쪽이 재사용한다. → 배치는 *추가*지 *교체*가 아니다.

---

## 4. 현재 구조에서 무엇이 바뀌나

**현재 (온라인) — 유지:**
```
run_graph: interpret_ad → load_panel → Send×N react(온라인 1콜씩) → aggregate
                                        └ GeminiReactionEngine.react() 페르소나당 호출
```

**추가 (배치) — 비동기 경계에서 분할:**
```
1부: interpret_ad → load_panel → build_batch(프롬프트 N개 조립) → submit_batch(job_id 저장) → 반환
              ⋯⋯⋯⋯⋯⋯⋯ 비동기 경계 (SQS 폴러가 넘김) ⋯⋯⋯⋯⋯⋯⋯
2부: collect_results(N개 파싱·가중 부여) → aggregate → 영속화 → 완료 알림
```

- `Send×N react` 온라인 fan-out은 배치 경로에선 쓰지 않는다(대신 build/submit/collect).
- `interpret_ad`·`load_panel`·`aggregate`는 **양 경로 공통** — 재사용.
- 배치 각 요청은 온라인과 **동일한 generation config**(`response_mime_type=application/json`, `temperature=1.0`)를
  담는다 → 구조화 출력·다양성 동일.

---

## 5. 배치 경로 설계 상세

### 5.1 제출 (submit)
- `load_panel` 후 페르소나 N명 각각에 대해 `_prompt(persona, ad, exposure)`로 프롬프트 생성.
- N개를 배치 잡 1건으로 묶어 제출 → `batch_job_id` 수령.
- `시뮬레이션` 행에 `status=PENDING_BATCH`, `batch_job_id` 기록(영속화). 워커는 여기서 손을 뗀다(블로킹 X).
- **custom_id 규칙**: 각 요청에 `persona_id`를 custom_id로 부여 → 결과 회수 시 페르소나와 1:1 매핑.

### 5.2 폴링 (poll) — SQS 지연 재투입
- 폴러가 `batch_job_id` 상태 조회.
- **미완료** → SQS 지연 메시지로 재투입(아래 §6.2 15분 캡 유의).
- **완료** → 결과 파일 회수.

### 5.3 회수·확정 (collect & finalize)
- 결과 N개를 custom_id로 페르소나에 매핑 → `PersonaReaction` 파싱(온라인과 동일 파서).
- 페르소나 `weight`를 반응에 사본 부여(§3.7) → `aggregator.aggregate()` → `SimulationAggregate`.
- 영속화(`save_completed_run`) → `status=COMPLETED` → SSE `completed` emit.
- **부분 실패 처리**: 일부 요청 실패 시 온라인과 동일하게 건너뛰고(`run_graph.react`의 try/except 정책) 성공분만
  집계. 전부 실패면 `FAILED`.

---

## 6. SQS 통합 설계

### 6.1 큐 구성
| 큐 | 용도 | 메시지 | 비고 |
|---|---|---|---|
| `simulation-run` (기존 `SQS_SIMULATION_QUEUE_URL`) | 런 접수 | `{run_id, request}` | 워커가 소비 → 배치 제출 |
| `batch-poll` | 배치 상태 확인 | `{run_id, batch_job_id, attempts}` | 폴러가 소비 → 미완료면 재투입 |
| `*-dlq` | 실패 격리 | — | maxReceiveCount 초과분 |

> MVP에선 큐 1개 + 메시지 타입 필드로 시작해도 된다(`type: submit|poll`). 운영 분리는 이후.

### 6.2 폴링 루프 — SQS 지연 캡 주의
- **SQS `DelaySeconds` 최대 = 900초(15분).** 배치는 최대 24h라 한 번 지연으론 못 기다린다.
- → 폴러는 "확인 후 미완료면 15분 지연으로 *재투입*"하는 루프를 돈다(`attempts` 증가, 상한 두고 타임아웃 처리).
- `VisibilityTimeout`을 폴 주기보다 넉넉히. 멱등성 보장(같은 batch_job_id 중복 확인 무해하게).

### 6.3 단일 EC2 제약
- 폴러를 별도 프로세스/스케줄(EC2 내 백그라운드 태스크 또는 cron성 워커)로. Lambda 도입은 선택.
- 7/8 마감 기준 **인프로세스 폴러(asyncio)로 시작**하고 SQS는 런 큐부터 붙이는 점진안도 가능(아래 §7).

---

## 7. 구현 단계 (점진)

### Phase A — 배치 코어 (인프라 없이)
1. `reaction.py`에서 프롬프트 조립·`PersonaReaction` 파싱을 **공유 함수로 추출**(온라인 무손상 확인).
2. `GeminiBatchReactionEngine` 추가 — N 프롬프트 제출/폴링/회수. `_common.py`에 배치 호출 래퍼.
3. `wiring.py`에 배치 경로 분기(`build_simulation_service(..., mode="batch")` 등). 온라인은 기본 유지.
4. 테스트: mock 배치(즉시 완료)로 N입력→N반응 매핑·부분 실패·가중 집계 검증.

### Phase B — 비동기 오케스트레이션
5. 인프로세스 폴러로 제출→폴링→확정 한 바퀴(SSE에 `PENDING_BATCH` 단계 추가).
6. `시뮬레이션` 영속화에 `batch_job_id`·`PENDING_BATCH` 상태 반영(스키마 변경은 공통부 협업 규칙 + Alembic).

### Phase C — SQS 전환
7. `simulation-run` 큐 워커 도입(현 `asyncio.create_task` → SQS 소비로 교체).
8. `batch-poll` 지연 재투입 루프 + DLQ.

### 하이브리드 라우팅 (전 구간 공통)
- `sample_size ≤ THRESHOLD`(예 50) → 온라인(기존 경로). 초과 → 배치. THRESHOLD는 제품 결정값.

---

## 8. 미해결·결정 필요

- **THRESHOLD 값** — 온라인/배치 분기 기준 표본수(잠정 50). UX·비용 보고 확정.
- **최대 대기 정책** — 배치 24h 타임아웃 시 사용자 노출 문구·부분결과 허용 여부.
- **provider** — 현재 Gemini로 충분(이미 `gemini-2.5-flash`). GPT/Claude 배치는 동일 패턴이라 어댑터만 추가하면 교체 가능(락인 회피).
- **DB 스키마** — `batch_job_id`·`PENDING_BATCH`는 `core/models.py`·`시뮬레이션` 변경 → **단독 변경 금지, 사전 공지 + Alembic**(협업 규칙).
- **재현성** — 배치도 모델 버전 핀 유지(§3.6). 배치/온라인 결과 동등성 1회 검증.

---

## 9. 한 문장 요약

**배치 API는 N콜을 독립 유지한 채 비동기로 절반값에 돌리는 것이라 프롬프트 묶기(동질화)와 다르고, SQS는
그 비동기를 우리 쪽에서 오케스트레이션하는 별개 층이며 함께 쓴다. 대규모에만 적용하는 건 코드 손상이 아니라
지연 허용도·절감 규모가 거기서만 맞기 때문이고, 온라인 경로는 공유 로직 추출로 손대지 않고 보존한다.**

---

## 참고 자료

- [Google Gemini API Batch Mode is Here and 50% Cheaper](https://apidog.com/blog/gemini-api-batch-mode/)
- [OpenAI Batch API | OpenAI API docs](https://developers.openai.com/api/docs/guides/batch)
- [Anthropic Message Batches API](https://anthropic.com/news/message-batches-api)
- [The Chameleon's Limit: Persona Collapse and Homogenization in LLMs](https://arxiv.org/html/2604.24698)
