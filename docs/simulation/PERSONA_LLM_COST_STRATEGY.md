# 페르소나 반응 LLM — 비용 절감과 모델 선택 검토

> 페르소나 반응 생성(4-b)의 LLM 호출 비용 문제와, 작은/로컬 모델 전환에 대한 검토 메모.
> 결론: **비용은 모델 다운그레이드가 아니라 배치 API + 표본가중으로 푼다. 모델 교체의 진짜 변수는
> 학습 데이터 시의성이 아니라 Persona Collapse(동질화)이며, 소형 모델은 파인튜닝을 동반할 때만 답이라
> 발표 후(Phase 2) 과제다.** (조사일: 2026-06-17)

---

## 0. 먼저 — "100명 = 100콜"의 정체

흔한 오해부터 정정한다. 현재 코드에서 **페르소나 속성 생성은 LLM을 쓰지 않는다.**

| 단계 | 무엇 | LLM 사용 | 비용 |
|---|---|---|---|
| 단계 1~3 (속성) | 인구·OCEAN·KISDI 분포에서 통계 샘플링 (`persona_sampler.py`) | ✗ | 공짜 |
| 4-a (서사) | `profile_narrative` 생성 | ○ (현재 빈 문자열, P3 미구현) | 패널 빌드 시 **1회 캐시** |
| **4-b (반응)** | 페르소나가 광고에 반응 (`GeminiReactionEngine`) | ○ | **페르소나당 1콜 = N콜** |

- 100콜이 나는 곳은 **반응(4-b)** 이다. `run_graph.py`가 페르소나마다 `Send("react")`로 fan-out한다.
- 4-b는 **설계상 캐시 금지**(반응은 광고마다 달라야 함, PERSONA §7). → 비용의 본체.
- 현재 모델은 이미 `gemini-2.5-flash` — **이미 작고 최신인 모델**(`adapters/gemini/_common.py:15`).

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

→ 데모 즉시성도 살리고 비용도 깎는다. 7/8 마감 안에 들어갈 규모.

> **구현 설계는 [BATCH_API_STRATEGY.md](./BATCH_API_STRATEGY.md) 참조** — 배치 API vs 프롬프트 묶기 구분,
> SQS 연동, 대규모 한정 이유, 그래프 분할·폴러 설계가 정리돼 있다.

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

### 지금 (7/8 마감 안)
- **모델은 그대로.** 이미 `gemini-2.5-flash`(작고 최신·한국어 양호·구조화 안정).
- 비용은 **① 대규모 실행 배치화 + ② 표본가중(§3.7)으로 300명**으로 푼다.
- 더 깎으려면 반응만 **Flash-Lite급**으로, `interpret_ad`(시뮬당 1콜·레버리지 큼)는 강한 모델 유지(작업별 모델 분리).

### 발표 후 (Phase 2)
- 로컬 소형 한국어 모델(EXAONE / A.X Lite)을 **페르소나 파인튜닝과 함께** 검토.
- off-the-shelf로 작은 모델만 끼우면 Persona Collapse로 다양성이 오히려 무너짐.
- 도입 전 합격 기준:
  - (a) aggregator가 이미 내는 `variance_warning`/`effective_n`으로 **분산 보존** 확인.
  - (b) **§5 한국 조사 방향성 재현** 통과.
  - (c) 단일 EC2에 GPU 없으면 로컬 추론 인프라부터 결정 → 마감 안엔 무리.

### 한 줄 요약
**GPT·Claude·Gemini 다 배치로 50% 깎인다. 바로는 "대규모 실행만 배치화"가 현실적.
모델 교체는 시의성이 아니라 Persona Collapse가 변수이고, 소형 모델은 파인튜닝을 동반할 때만 답이라
발표 후 과제다.**

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
