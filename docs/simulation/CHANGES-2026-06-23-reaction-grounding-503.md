# 반응 생성 보강 — 프롬프트 grounding + 제미나이 503 내성 (2026-06-23)

> 시뮬레이터 4-b 반응 생성의 두 갈래 문제를 정리하고 적용한 변경을 기록한다.
> ① 반응 프롬프트의 근거 부족(신뢰도 기준·세대 프레임 과증폭), ② 제미나이 콜 거부(503 과부하).
> 담당 yeotaeho(페르소나·반응). 모두 시뮬레이터 소유 영역(반응 어댑터/서비스/wiring) 안.

---

## 1. 배경 — 발견된 문제

반응 생성 코드·문서·실증 연구를 교차 검토해 아래를 확인했다.

| # | 문제 | 근거 | 상태 |
| --- | --- | --- | --- |
| A | **trust(신뢰도) 판단 기준 부재** — 프롬프트에 `"trust": 1~5 정수`만 있고 척도 정의가 없어 LLM이 자기 통념으로 매김 → 4대 KPI 중 가장 약한 신호 | `reaction.py` 출력 스펙, `schemas.py` PersonaReaction.trust(범위만) | ✅ 수정 |
| B | **세대 프레임 무조건 주입** — `_generation_lines`가 광고 종류와 무관하게 "내 세대 vs 젊은 세대 친숙도/낯섦" 프레임을 전 페르소나에 심어, 40+가 연령 무관 광고에도 "젊은 애들용"으로 균질 수렴. 프로젝트 자체 데이터(KOSIS 기준 페북 40~59세 편중)와도 모순 | `reaction.py` `_generation_lines`, PERSONA_PIPELINE §9 | ✅ 수정 |
| C | **클릭의향률 과대(10~30% vs 실측 CTR 1~5%)** — 설계상 CTR이 아니라 강제노출·의도-행동 격차·LLM 긍정편향·직접 elicitation의 합산. 미보정 상대 신호 | CLAUDE.md, `schemas.py` ObjectiveFit docstring, AD_Simulator_Improvement_Notes §5 | ⏳ 설계상 의도(보정 보류) — 본 변경 범위 밖 |
| D | **제미나이 503(과부하) 콜 거부 빈발** — `gemini-2.5-flash`의 알려진 일시 과부하. 우리 코드가 증폭: API 재시도 0 + 반응 fan-out 동시성 상한 0(최대 1000콜 동시) + 실패 조용히 드롭 | `_common.py`(재시도 無), `run_graph.py`(상한 無), `run_graph.py` react 노드 드롭 | ✅ 수정 |

> C는 "버그"가 아니라 설계상 미보정 상대 지표다. 절대 CTR 환산은 실측 누적 후 calibration 해금 전까지 금지(CLAUDE.md). 본 문서는 A·B·D를 수정 대상으로 다룬다.

---

## 2. 적용한 변경

### ① trust 척도 앵커 (문제 A)

- `reaction.py`에 `_trust_anchor_line()` 헬퍼 신설 → "주의:" 블록에 배선. LLM이 **1=과장·허위 같아 전혀 못 믿겠다 / 3=반신반의 / 5=내용이 사실 같고 충분히 믿을 만하다** 기준으로 판단.
- 같은 줄의 `purchase_intent`는 **건드리지 않음** — KOBACO 베이스라인 검증 대상이라 문구 변경 시 분포 이동으로 calibration 비교가 틀어짐.

### ② `_generation_lines` 분할 게이팅 (문제 B)

`_generation_lines`는 두 기능이 묶여 있었다 — (a) 세대 친숙도/낯섦 프레임(과증폭 원인), (b) "내 나이대 말투로 말하라"(전 페르소나 유익·무해).

- 새 헬퍼 `_has_age_or_brand_cue(ad)` — 다음 중 하나면 True: `brand_era.identified` / 비어있지 않은 `awareness_by_age` / 연령 특정 `detected_target`(로컬 `_BROAD_TARGET_TERMS`로 포괄어 제외).
- `_generation_lines(age)` → `_generation_lines(age, ad)`. **말투·형성기 문맥은 항상 유지**, 친숙도 프레임만 단서 있을 때 주입 → 연령 무관 광고의 "젊은 애들" 과증폭 차단.
- 동료(분석·토론) 소유 `tools/debate/selector.py`의 유사 리스트는 **import 않고 로컬 복제**(도메인 경계 보호).

### ③ 503 지수 백오프 재시도 (문제 D-1)

- `_common.py`의 `_agen_json`을 `tenacity.AsyncRetrying`으로 감쌈 — 503/429/500/502/504 및 네트워크 일시오류에 **지수 백오프 재시도(최대 5회, 지터 포함 최대 30초)**.
- `_is_transient()`로 재시도 대상 판정(상태코드 + 메시지/클래스명 매칭). **안전블록·4xx(429 제외)·JSON 파싱 실패는 비재시도**(영속 오류).
- 이 함수는 reaction뿐 아니라 ad_interpreter·rubric·qa 어댑터가 공유 → 광고해석·루브릭도 함께 503 내성 획득.

### ④ 반응 fan-out 동시성 상한 (문제 D-2)

- `simulation_service.py`의 `astream` config에 `max_concurrency` 설정 → LangGraph가 `Send` fan-out 병렬 수를 제한. 과부하 엔드포인트에 1000콜 동시 발사로 503을 자초하던 것을 차단.
- 기본 8, 환경변수 `SIMULATION_MAX_CONCURRENCY`로 튜닝. preamble 노드(단일)에는 영향 없음.

### ⑤ GPT 폴백 (포트 뒤) (문제 D-3, 벤더 리스크 완충)

잘 튜닝된 프롬프트·파싱은 공유하고 LLM 호출만 교체하는 구조.

- `reaction.py` 리팩토링 — `_prompt`(메서드) → `build_reaction_prompt()`, 파싱 → `build_persona_reaction()`, 오케스트레이션 → `generate_reaction(json_call, persona, ad)` 의 **프로바이더 무관 모듈 함수**로 추출. `GeminiReactionEngine`는 자기 `json_call`만 넘기는 얇은 껍데기로 축소(`_pick_exposure`는 테스트 의존이라 유지).
- 신규 `openai_reaction.py` — `OpenAIReactionEngine`(OpenAI `chat.completions` JSON mode, 동일 백오프 재시도, 기본 `gpt-4.1-mini`).
- 신규 `reaction_fallback.py` — `FallbackReactionEngine([primary, fallback])`. primary가 자체 재시도까지 소진하고 실패하면 다음으로 폴백, 모두 실패 시 마지막 예외 전파.
- `wiring.py` `_build_reactor()` — 기본 Gemini. **OPENAI_API_KEY 있고 폴백 ON이면** Gemini→GPT 체인. 키 없으면 Gemini 단독(기존 동작 보존). `_is_transient`에 OpenAI 연결/타임아웃/5xx 추가.

---

## 3. 동작 흐름 (1·3단계 결합)

```
반응 1건 → Gemini(503 백오프 5회 재시도) ── 성공 ──▶ 반응 JSON
                       └─ 재시도 소진/실패 ──▶ GPT(gpt-4.1-mini, JSON mode) ──▶ 반응 JSON
                                                       └─ 실패 ──▶ react 노드가 드롭(기존 graceful)
  └ fan-out 동시성 max_concurrency(기본 8)로 제한 — 동시 폭주로 인한 503 자체를 감소
```

- 폴백은 **기본 ON이되 OPENAI_API_KEY 있을 때만 작동** → 키 없는 개발/테스트는 Gemini 단독 그대로(회귀 0).
- GPT는 **Gemini 실패분만** 호출 → 비용은 실패율에 비례. `SIMULATION_REACTION_FALLBACK=0`으로 즉시 차단(되돌리기 쉬움).

---

## 4. 변경 파일

| 파일 | 변경 |
| --- | --- |
| `domain/simulation/adapters/gemini/reaction.py` | trust 앵커, 세대 게이팅, 프로바이더 무관 함수 추출 |
| `domain/simulation/adapters/gemini/_common.py` | `_is_transient` + `_agen_json` 백오프 재시도 |
| `domain/simulation/service/simulation_service.py` | `max_concurrency` 동시성 상한 |
| `domain/simulation/adapters/openai_reaction.py` | **신규** OpenAI 반응 엔진 |
| `domain/simulation/adapters/reaction_fallback.py` | **신규** 폴백 래퍼 |
| `domain/simulation/wiring.py` | `_build_reactor` 폴백 배선 |
| `.env.example` | 신규 환경변수 문서화 |
| `tests/simulation/test_reaction_prompt.py` | trust 앵커·게이팅 테스트(+3) |
| `tests/simulation/test_gemini_common.py` | **신규** 재시도 테스트(5) |
| `tests/simulation/test_reaction_fallback.py` | **신규** 폴백·오케스트레이션 테스트(4) |

---

## 5. 환경변수

| 변수 | 기본 | 역할 |
| --- | --- | --- |
| `SIMULATION_MAX_CONCURRENCY` | 8 | 반응 fan-out 동시성 상한 |
| `SIMULATION_REACTION_FALLBACK` | 1(ON) | GPT 폴백 토글(0/false면 끔, OPENAI_API_KEY 있을 때만 작동) |
| `SIMULATION_REACTION_FALLBACK_MODEL` | gpt-4.1-mini | 폴백 OpenAI 모델 |

---

## 6. 검증

- `cd backend && uv run pytest tests/simulation/ -q` → **123 passed, 7 skipped**. Ruff 클린.
- 신규/추가 테스트 12종 — trust 앵커 존재, `_has_age_or_brand_cue` 분기, 세대 프레임 게이팅, 503 재시도/포기/비재시도, 폴백 전환·예외 전파, `generate_reaction` 프로바이더 무관 파싱.

---

## 7. 남은 과제 / 범위 밖

- **purchase_intent 앵커** — KOBACO 분포 재검증 부담으로 보류.
- **`_TRUST_HIGH=3.5` 임계 재조정**(`tools/debate/kpi.py`, 동료 소유) — trust 앵커로 분포가 이동할 수 있어 관찰 후 협의.
- **OpenAI Structured Outputs(strict json_schema)** — JSON mode보다 엄격해 파싱 실패성 드롭을 더 줄일 수 있으나 §3.5 스키마를 JSON Schema로 옮기는 추가 작업이라 제외.
- **클릭의향률 calibration**(문제 C) — 실측 CTR 누적 후 단조 매핑으로 해금(CLAUDE.md 방침).
- **SQS 미사용** — 큐 수신은 여전히 in-process `asyncio.create_task`(SQS_SIMULATION_QUEUE_URL 미연동).

---

## 8. 후속 공지 (동료·팀)

- **trust_avg 분포 이동 가능** — 계약 스키마(`SimulationAggregate`)는 불변이나, 값을 소비하는 `tools/debate/kpi.py`(`_TRUST_HIGH`)·`tools/objective_fit.py`(정규화)는 그대로 두었다. 분포 이동은 의도된 개선 → 동료에게 공유.
- **폴백 ON 시 토큰 비용이 두 벤더로 분산**된다(Gemini 실패분만큼 OpenAI 호출). LangSmith에 `openai.chat_json` span으로 추적.
