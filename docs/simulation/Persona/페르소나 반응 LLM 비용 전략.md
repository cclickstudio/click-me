# 페르소나 반응 LLM — 비용·모델·배치 API 전략

> 페르소나 반응 생성(4-b)의 LLM 호출 비용 문제, 작은/로컬 모델 전환 검토, 배치 API 구현 설계를 한곳에 정리한 문서.
> 결론: **비용은 모델 다운그레이드가 아니라 배치 API + 표본가중으로 푼다. 모델 교체의 진짜 변수는
> 학습 데이터 시의성이 아니라 Persona Collapse(동질화)이며, 소형 모델은 파인튜닝을 동반할 때만 답이라
> 발표 후(Phase 2) 과제다. 배치 API는 "N콜을 독립 유지한 채 비동기로 절반값에" 돌리는 것으로
> 프롬프트 묶기(동질화 위험)와 다르며, 대규모 실행에만 적용한다.** (조사일: 2026-06-17 / 병합 정리: 2026-07-07)
>
> **병합 이력 (2026-07-07)** — `BATCH_API_STRATEGY.md`를 §5 이하로 흡수(원본 삭제). 잡 오케스트레이션은
> **인프로세스 asyncio로 확정**(SQS·Redis 미사용, CLAUDE.md Key Decisions)이라 원문의 SQS 통합 설계는 제거하고
> 인프로세스 폴러 기준으로 재기술했다. `LOCAL_MODEL_SELFHOST_STRATEGY.md`(80GB GPU 자체 호스팅 검토)는
> GPU 확보 계획이 없어져 삭제 — 결론만 요약하면 *"GPU가 생겨도 진짜 병목은 컴퓨트가 아니라 ① Persona Collapse
> ② 파인튜닝 라벨 데이터라, 학습부터 가지 말고 30B off-the-shelf + vLLM guided decoding부터 검증"*이었다.

---

## 0. 먼저 — "100명 = 100콜"의 정체

흔한 오해부터 정정한다. 현재 코드에서 **페르소나 속성 생성은 LLM을 쓰지 않는다.**

| 단계 | 무엇 | LLM 사용 | 비용 |
|---|---|---|---|
| 단계 1~3 (속성) | 인구·OCEAN·KISDI 분포에서 통계 샘플링 (`persona_sampler.py`) | ✗ | 공짜 |
| 4-a (서사) | `profile_narrative` 생성 | ○ | 패널 빌드 시 **1회 캐시** |
| **4-b (반응)** | 페르소나가 광고에 반응 (`GeminiReactionEngine`) | ○ | **페르소나당 1콜 = N콜** |

- 100콜이 나는 곳은 **반응(4-b)** 이다. `run_graph.py`가 페르소나마다 `Send("react")`로 fan-out한다.
- 4-b는 **설계상 캐시 금지**(반응은 광고마다 달라야 함, PERSONA §7). → 비용의 본체.
- 현재 모델은 Gemini Flash급(반응 모델은 `SIMULATION_REACTION_GEMINI_MODEL`로 교체 가능, GPT 폴백 체인 有) — **이미 작고 최신인 모델.**

> 즉 "페르소나 생성을 작은 모델로"라는 발상은 정작 비용이 나는 곳(반응)을 안 건드린다.

---

## 1. "작은/옛날 모델은 학습 데이터가 낡아 문제 아니냐"에 대한 답

방향 절반은 맞고, 타깃이 어긋나 있다.

이 시스템의 설계 철학 자체가 **LLM의 학습 지식 의존을 최대한 떼어내는 것**이다(PERSONA §2 원칙 1).
모델에게 "한국 30대가 어떤지 알아내라"를 시키지 않는다. 나이·OCEAN·소득·미디어습관·소비가치를
**외부 데이터로 박아 명세로 주고**, 모델은 "이 사람이 되어 이 광고에 반응해봐"만 한다
(`adapters/gemini/reaction.py`의 프롬프트).

- 인구통계·성격의 최신성 → KOSIS·Nature 논문·KISDI가 책임진다.
- 트렌드 시의성 → 분석 레이어의 RAG가 책임진다(파라메트릭 지식이 아니라).
- 반응은 "주어진 페르소나 + 주어진 광고"에 대한 **추론**이지 세계 지식 회상이 아니다.

→ **"모델 학습 데이터의 시의성"은 이 아키텍처에선 생각보다 덜 중요하다.** 따라서 "옛날" 모델은
이득이 없다(시의성 문제는 데이터가 막고, "옛날/약한"이 깨먹는 건 따로 있다).

---

## 2. 배치 API — GPT에도 있나, 바로 적용되나

### 2.1 세 provider 모두 보유 (조사 결과)

| Provider | 할인 | 완료 SLA | 형식 |
|---|---|---|---|
| **Gemini** (현재 사용) | 입·출력 50% | **SLA 없음, 최대 24h** | 배치 잡 제출 |
| **OpenAI (GPT)** | 입·출력 50% | 24h 보장 (보통 1~2h) | JSONL, 최대 5만 요청 |
| **Anthropic (Claude)** | 입·출력 50% | 24h 보장 (보통 <1h) | 최대 10만 요청 |

셋 다 동일하게 **"비실시간 대량 작업을 절반값에"**. GPT도 당연히 있다(OpenAI Batch API).

### 2.2 함정 — "최대 24시간, 실시간 보장 없음"

대부분 수분~1시간 안에 끝나지만 **보장은 24시간**이다. 마케터가 광고 테스트하고 결과를 기다리는
**인터랙티브 경로에 그대로 박으면 "최악의 경우 내일 결과"**가 된다.

### 2.3 "바로 적용 가능한가" — 정직한 답

코드상 반응 단계(`GeminiReactionEngine`)가 잘 격리돼 있어 바꾸기 쉽지만, **드롭인 교체는 아니다.**

- **아키텍처**: 지금은 페르소나마다 온라인 병렬 호출(`Send("react")`). 배치는
  "N개 프롬프트 모아서 1잡 제출 → 폴링 → 결과 매핑" 패턴이라 LangGraph fan-out map 노드를 재설계해야 함.
- **UX**: 실시간 SSE 진행률 → 비동기 잡("제출했고 몇 분~몇 시간 뒤 완료").

### 2.4 현실적 정답 — 하이브리드

| 모드 | 규모 | 경로 | 이유 |
|---|---|---|---|
| 빠른 미리보기 | ≤50명 | 기존 온라인 호출 | 즉답(데모 즉시성) |
| 본 리포트 대규모 실행 | 300~1,000명 (§3.7 표본가중) | **배치 50% 절감** | 무거운 정밀 실행 → "제출하고 나중에 보기" 자연스러움 |

→ 데모 즉시성도 살리고 비용도 깎는다. 구현 설계는 아래 **§5~§8**.

---

## 3. 페르소나 반응에 적합한 LLM — 조사 결과

직감("Deepsona는 소형/로컬 모델을 쓴다")은 **문헌으로 뒷받침된다.** 단 "작은 모델로 그냥 바꾸기"와
"작은 모델을 제대로 쓰기"는 다르다.

### 3.1 진짜 위험은 시의성이 아니라 Persona Collapse(동질화)

최근 연구(arXiv "The Chameleon's Limit")가 입증 — 서로 다른 프로필을 줘도 에이전트들이 좁은 행동
모드로 수렴해 동질 집단이 되는 실패 모드. **작은 모델일수록 심하다.** (reaction.py가 `temperature=1.0`을
쓰는 이유.)

### 3.2 해법도 나와 있다 — 파인튜닝

Polypersona 연구: **persona-grounded fine-tuning을 하면 TinyLlama 1.1B·Phi-2 같은 초소형도
7~8B급 다양성·일관성을 따라잡는다.** 즉 Deepsona가 로컬 소형 모델로 되는 비결은 "작은 모델"이 아니라
**"작은 모델 + 페르소나 파인튜닝"**이다. 비용 절감 지름길이 아니라 투자.

### 3.3 한국어 모델 지형 (소형~중형)

| 모델 | 주체 | 규모 | 메모 |
|---|---|---|---|
| **HyperCLOVA X** | 네이버 | SEED 32B 오픈웨이트 | 한국어 데이터 압도적, KMMLU에서 GPT-4 상회 주장 |
| **EXAONE 4.0** | LG | 30B | 글로벌 벤치 경쟁력 |
| **A.X 3.1 Lite** | SKT (Qwen 기반) | 7B | KMMLU에서 대형의 ~96%. **소형 한국어 후보 1순위** |
| Solar Pro / Kanana | 각사 | — | 리더보드 비교 가능 |
| Qwen3.x / Gemma | 글로벌 | 소형 | 강하지만 한국어는 2순위 → `utterance` 품질 손해 |

### 3.4 작은 모델이 진짜로 깨먹는 지점 (우선순위순)

1. **동질화(Persona Collapse)** — 최대 리스크. 명세를 다르게 줘도 반응이 비슷해지면 데이터로 강제한 다양성이 출력단에서 뭉개짐.
2. **한국어 발화 품질** — `utterance`는 보고서에서 가장 설득력 있는 부분(REPORT §3-2). 어색한 한국어는 킬러 파트를 죽임.
3. **구조화 출력 준수** — §3.5 스키마(AISAS bool, enum 태그, 1~5 정수)를 안 깨고 지키는 능력. 작은 모델이 더 자주 어김.

---

## 4. 권고

### 지금 (발표 전)
- **모델은 그대로.** 이미 Gemini Flash급(작고 최신·한국어 양호·구조화 안정) + GPT 폴백.
- 비용은 **① 대규모 실행 배치화 + ② 표본가중(§3.7)으로 300명**으로 푼다.
- 더 깎으려면 반응만 **Flash-Lite급**으로, `interpret_ad`(시뮬당 1콜·레버리지 큼)는 강한 모델 유지(작업별 모델 분리).

### 발표 후 (Phase 2)
- 로컬 소형 한국어 모델(EXAONE / A.X Lite)을 **페르소나 파인튜닝과 함께** 검토.
- off-the-shelf로 작은 모델만 끼우면 Persona Collapse로 다양성이 오히려 무너짐.
- 도입 전 합격 기준:
  - (a) aggregator가 이미 내는 `variance_warning`/`effective_n`으로 **분산 보존** 확인.
  - (b) **§5 한국 조사 방향성 재현** 통과.
  - (c) 로컬 추론 인프라(GPU) 확보가 선행 — 현재 계획 없음(자체 호스팅 검토 메모는 삭제, 결론 요약은 문서 머리말 참조).

---

# 배치 API 구현 전략 (구 BATCH_API_STRATEGY.md)

> 잡 오케스트레이션은 **인프로세스 asyncio**(SQS·Redis 미사용)가 프로젝트 확정 사항이다.
> 아래 설계의 폴링·상태 관리는 전부 인프로세스 기준이다.

## 5. 용어 정리 — 배치 API vs 프롬프트 묶기 (헷갈리기 쉬운 지점)

> 나중에 또 헷갈릴 수 있어 박아둔다. "10개 페르소나를 한 번에 호출"이라는 말이 두 가지를 의미할 수 있다.

### 5.1 두 개념은 완전히 다르다

| | **프롬프트 묶기** (multi-persona-in-one-call) | **배치 API** (이 문서가 말하는 것) |
|---|---|---|
| 호출 수 | 10콜 → 1콜 (감소) | 100요청 그대로 |
| 컨텍스트 | 10명이 **한 컨텍스트 공유** | 페르소나마다 **독립** |
| 절약 원천 | 호출 수 ↓ | 토큰 단가 50% ↓ (실시간 포기 대가) |
| 응답 시점 | 즉시 | 비동기 (보통 분~시간, 최대 24h) |
| 다양성 | **오염 위험** | 보존 |

### 5.2 프롬프트 묶기를 쓰지 않는 이유 (금지)

이게 더 싸 보이지만 **이 프로젝트가 싸우는 실패 모드를 정확히 부른다.**

- 10명을 한 컨텍스트에 넣으면 **서로의 응답에 오염**된다(앞 반응이 뒤에 영향) → Persona Collapse(동질화)
  가속. PERSONA §7의 "클러스터를 대표답으로 축약 금지"와 같은 결의 위반.
- 출력 길이 제한, 구조화 JSON 깨짐(10개 분량 한 번에), 한 명 오류가 전체 응답을 망침.
- 다양성은 단계 1~3에서 데이터로 강제해 놨는데, 출력단에서 한 컨텍스트에 몰면 그 다양성이 다시 뭉개진다.

→ **배치 API는 "독립성 유지하며 싸게"라 안전, 프롬프트 묶기는 "싸지만 동질화"라 철학과 충돌.**

## 6. 왜 대규모 실행에만 배치인가 — 진짜 이유

질문: "배치를 대규모에서만 쓰는 건 기존 온라인 호출 코드가 손상돼서인가?"
**아니다.** 코드 손상이 이유가 아니라, 다음 두 축이 대규모에서만 맞아떨어지기 때문이다.

| 축 | 소규모 미리보기 (≤50명) | 대규모 본실행 (300~1,000명) |
|---|---|---|
| **지연 허용도** | 즉답 필요(SSE로 한 명씩 스트리밍 보며 확인) | "제출하고 나중에 보기"가 자연스러움(1,000명을 실시간으로 안 봄) |
| **절감 규모** | 50%를 깎아도 절대액 미미 → 비동기 복잡도 손해 | 콜이 많아 50% 절감액이 큼 → 도입 가치 |

→ 즉 **배치 적합성은 "런 크기"가 아니라 "지연 허용도 × 절감 규모"의 함수**이고, 그게 대규모와 정렬된다.

- "온라인 코드 보존"은 이유가 아니라 부차적 이점 — (a) 즉시 미리보기 UX, (b) 데모 핵심인 실시간 SSE 경험,
  (c) "수술적 변경" 원칙(작동 코드 유지) 때문이며, 하이브리드 선택의 *결과*지 원인이 아니다.
- **손상 없이 가는 설계 — 공유 로직 추출.** 배치와 온라인은 같은 프롬프트 조립·파싱(`reaction.py`의
  `_prompt()`·`PersonaReaction` 파싱)을 쓴다. 공유 함수로 빼면 코드를 복제·손상하지 않고 양쪽이 재사용한다.
  → 배치는 *추가*지 *교체*가 아니다.

## 7. 현재 구조에서 무엇이 바뀌나

**현재 (온라인) — 유지:**
```
run_graph: interpret_ad → load_panel → Send×N react(온라인 1콜씩) → aggregate
                                        └ GeminiReactionEngine.react() 페르소나당 호출
```

**추가 (배치) — 비동기 경계에서 분할:**
```
1부: interpret_ad → load_panel → build_batch(프롬프트 N개 조립) → submit_batch(job_id 저장) → 반환
              ⋯⋯⋯⋯⋯ 비동기 경계 (인프로세스 폴러가 넘김) ⋯⋯⋯⋯⋯
2부: collect_results(N개 파싱·가중 부여) → aggregate → 영속화 → 완료 알림
```

- `Send×N react` 온라인 fan-out은 배치 경로에선 쓰지 않는다(대신 build/submit/collect).
- `interpret_ad`·`load_panel`·`aggregate`는 **양 경로 공통** — 재사용.
- 배치 각 요청은 온라인과 **동일한 generation config**(`response_mime_type=application/json`, `temperature=1.0`)를
  담는다 → 구조화 출력·다양성 동일.

## 8. 배치 경로 설계 상세

### 8.1 제출 (submit)
- `load_panel` 후 페르소나 N명 각각에 대해 `_prompt(persona, ad, exposure)`로 프롬프트 생성.
- N개를 배치 잡 1건으로 묶어 제출 → `batch_job_id` 수령.
- `시뮬레이션` 행에 `status=PENDING_BATCH`, `batch_job_id` 기록(영속화). 제출 후 손을 뗀다(블로킹 X).
- **custom_id 규칙**: 각 요청에 `persona_id`를 custom_id로 부여 → 결과 회수 시 페르소나와 1:1 매핑.

### 8.2 폴링 (poll) — 인프로세스 asyncio 폴러
- `asyncio.create_task`로 도는 폴러가 주기적으로(예 1~15분 백오프) `batch_job_id` 상태를 조회.
- **미완료** → 다음 주기까지 `asyncio.sleep` 후 재확인(`attempts` 상한 + 24h 타임아웃 처리).
- **완료** → 결과 파일 회수.
- **서버 재시작 내성**: 폴러 태스크는 프로세스와 함께 죽으므로, 기동 시(lifespan)
  `status=PENDING_BATCH`인 시뮬레이션 행을 스캔해 폴러를 재기동한다 — `batch_job_id`가 DB에 있어
  잡 자체는 유실되지 않는다(배치는 provider 쪽에서 계속 돈다).
- 멱등성 보장(같은 batch_job_id 중복 확인 무해하게).

### 8.3 회수·확정 (collect & finalize)
- 결과 N개를 custom_id로 페르소나에 매핑 → `PersonaReaction` 파싱(온라인과 동일 파서).
- 페르소나 `weight`를 반응에 사본 부여(§3.7) → `aggregator.aggregate()` → `SimulationAggregate`.
- 영속화(`save_completed_run`) → `status=COMPLETED` → SSE `completed` emit.
- **부분 실패 처리**: 일부 요청 실패 시 온라인과 동일하게 건너뛰고(`run_graph.react`의 try/except 정책) 성공분만
  집계. 전부 실패면 `FAILED`.

## 9. 구현 단계 (점진)

### Phase A — 배치 코어
1. `reaction.py`에서 프롬프트 조립·`PersonaReaction` 파싱을 **공유 함수로 추출**(온라인 무손상 확인).
2. `GeminiBatchReactionEngine` 추가 — N 프롬프트 제출/폴링/회수. `_common.py`에 배치 호출 래퍼.
3. `wiring.py`에 배치 경로 분기(`build_simulation_service(..., mode="batch")` 등). 온라인은 기본 유지.
4. 테스트: mock 배치(즉시 완료)로 N입력→N반응 매핑·부분 실패·가중 집계 검증.

### Phase B — 비동기 오케스트레이션 (인프로세스)
5. asyncio 폴러로 제출→폴링→확정 한 바퀴(SSE에 `PENDING_BATCH` 단계 추가).
6. `시뮬레이션` 영속화에 `batch_job_id`·`PENDING_BATCH` 상태 반영(스키마 변경은 공통부 협업 규칙 + Alembic).
7. lifespan에 `PENDING_BATCH` 스캔·폴러 재기동(§8.2 재시작 내성).

### 하이브리드 라우팅 (전 구간 공통)
- `sample_size ≤ THRESHOLD`(예 50) → 온라인(기존 경로). 초과 → 배치. THRESHOLD는 제품 결정값.

## 10. 미해결·결정 필요

- **THRESHOLD 값** — 온라인/배치 분기 기준 표본수(잠정 50). UX·비용 보고 확정.
- **최대 대기 정책** — 배치 24h 타임아웃 시 사용자 노출 문구·부분결과 허용 여부.
- **provider** — 현재 Gemini로 충분. GPT/Claude 배치는 동일 패턴이라 어댑터만 추가하면 교체 가능(락인 회피).
- **DB 스키마** — `batch_job_id`·`PENDING_BATCH`는 `core/models.py`·`시뮬레이션` 변경 → **단독 변경 금지, 사전 공지 + Alembic**(협업 규칙).
- **재현성** — 배치도 모델 버전 핀 유지(§3.6). 배치/온라인 결과 동등성 1회 검증.

---

## 한 줄 요약

**GPT·Claude·Gemini 다 배치로 50% 깎인다. 배치 API는 N콜을 독립 유지한 채 비동기로 절반값에 돌리는 것이라
프롬프트 묶기(동질화)와 다르고, 대규모 실행에만 적용한다(지연 허용도 × 절감 규모). 오케스트레이션은
인프로세스 asyncio로 확정(SQS 미사용). 모델 교체는 시의성이 아니라 Persona Collapse가 변수이고,
소형 모델은 파인튜닝을 동반할 때만 답이라 발표 후 과제다.**

---

## 참고 자료

- [Google Gemini API Batch Mode is Here and 50% Cheaper](https://apidog.com/blog/gemini-api-batch-mode/)
- [OpenAI Batch API | OpenAI API docs](https://developers.openai.com/api/docs/guides/batch)
- [Anthropic Message Batches API](https://anthropic.com/news/message-batches-api)
- [Meet South Korea's LLM Powerhouses (HyperCLOVA X, A.X, Solar Pro)](https://www.marktechpost.com/2025/08/21/meet-south-koreas-llm-powerhouses-hyperclova-ax-solar-pro-and-more/)
- [Best Korean LLMs — Korea AI Leaderboard 2026](https://benchlm.ai/leaderboards/korean-llm)
- [The Chameleon's Limit: Persona Collapse and Homogenization in LLMs](https://arxiv.org/html/2604.24698)
- [Polypersona: Persona-Grounded LLM for Synthetic Survey Responses](https://arxiv.org/pdf/2512.14562)
- [Verbalized Sampling: Mitigating Mode Collapse and Unlocking LLM Diversity](https://arxiv.org/html/2510.01171v1)
