# 광고 이미지 해석 — 공유 해석 vs 페르소나별 vision 재투입

> 현재 광고 이미지를 VLM이 1회 해석해 모든 페르소나에 공유한다. "페르소나마다 보는 시점이 다르니
> 각자 원본 이미지를 보게 하자"는 제안을 검토한 메모.
> 결론: **페르소나별 원본 이미지 재투입은 하지 않는다 — 비용·지연뿐 아니라 노리는 효과("다르게 본다")가
> 정작 안 잡히고 의도 교차검증이 깨진다. Deepsona·연구도 공유 텍스트 해석을 택한다. "다르게 본다"는
> 공유 해석을 풍부하게 + 페르소나별 salience를 텍스트 단계에서 조건화해 거의 공짜로 살린다.**
> (작성일: 2026-06-17)

---

## 0. 출발 질문

> 현재 광고 이미지 분석을 하나의 VLM이 해석해 각 페르소나에게 전달한다. 페르소나마다 광고 보는 시점이
> 다르니 각 페르소나가 광고 이미지를 직접 보게 하는 게 좋을 것 같은데, 토큰·지연이 무리일 것 같다.
> 어떻게 생각하나? Deepsona는 어떻게 하나?

→ **직감이 맞다 — 지금은 하지 않는 게 맞다.** 단 이유는 토큰·지연만이 아니다. 아래에서 정리한다.

---

## 1. 지금 구조 (사실 확인)

```
interpret_ad: VLM이 이미지를 1회 해석 → AdInterpretation(텍스트 구조화)
        ↓ (이 1개를 모든 페르소나에 동일 전달)
react ×N: 페르소나는 detected_message·industry·target·ad_features만 봄 (원본 이미지 안 봄)
```

- 비싼 vision 토큰은 `interpret_ad`에서 **딱 1번** 낸다 (`ad_interpreter.py:56-62`, `types.Part.from_bytes`).
- 페르소나 반응 프롬프트(`reaction.py:76-77`)에 들어가는 건 **텍스트 요약**뿐 — 이미지 픽셀은 안 들어간다.
- `run_graph.py`의 `fan_out`은 같은 `ad`(해석 1개)를 `Send`로 N명에게 복사한다 (`run_graph.py:104-106`).

제안은 이 텍스트 요약 대신 **원본 이미지를 N명에게 각각** 넣자는 것 → vision 호출이 1회에서 N회가 된다.

---

## 2. "사람마다 보는 시점이 다르다"는 맞다 — 근데 재투입으로는 안 잡힌다

선택적 주의(selective attention)는 실제 현상이다. 가격에 민감한 사람은 가격을, 브랜드 충성자는 로고를 먼저
본다. 하지만 **같은 픽셀을 같은 VLM에 N번 넣어도 그게 안 생긴다.**

| # | 문제 | 설명 |
|---|---|---|
| 1 | **추출이 거의 동일** | VLM은 페르소나의 시선을 모른다. 같은 이미지면 같은 salient feature를 뱉는다. "다르게 보는" 차이는 *지각*이 아니라 *해석·가중*에서 오고, 그건 텍스트 추론 단계에서 페르소나 프로필로 이미 만든다. |
| 2 | **비용이 비싼 쪽에서 N배** | 이미지 1장 토큰 ≫ 짧은 JSON 해석. 1회로 끝나던 vision을 300~1,000회로 곱하면 배치·표본가중으로 깎으려던 비용을 정면으로 되돌린다. |
| 3 | **지연·레이트리밋** | vision 호출이 텍스트보다 느리고, N개 동시 vision은 TPM 한도에 더 잘 걸린다. |
| 4 | **단일 진실원천 붕괴** | 지금은 공유 해석이 `detected_message`·의도 교차검증(§3.5-3, `intent_mismatch`)·리포트의 기준점이다. 페르소나마다 따로 지각하면 "이 광고가 뭐라 말하는가"의 canonical 값이 사라지고 교차검증이 무너진다. |

> 요지: 노리는 건 "같은 자극, 다른 주의 배분"인데, 재투입은 "같은 자극, 같은 추출"을 N번 비싸게 할 뿐이다.

---

## 3. Deepsona는 어떻게 하나 (조사 결과)

**우리와 같다 — 공유 텍스트 해석 방식.**

- Deepsona(6-agent 프레임워크)는 광고 크리에이티브를 **"visual descriptions"(시각 요소를 텍스트로 기술)**
  로 입력받고, 별도의 **controlled exposure** 에이전트가 이를 다룬다. 각 페르소나는 이 구조화된 크리에이티브
  컴포넌트를 보고 평가하지, **원본 픽셀로 독립 vision을 N번 돌리지 않는다.**
- 즉 "한 번 해석 → 공유"가 업계 레퍼런스의 선택이다.

연구도 같은 방향이다 — 멀티모달 LLM은 페르소나·입력을 줄 때 **이미지보다 텍스트 표현을 뚜렷이 선호**하고
vision 이해에 갭이 있다(arXiv 2502.20504). reasoning 단계에 원본 이미지를 밀어넣는 게 오히려 품질을 깎을 수 있다.

---

## 4. 더 나은 대안 — "공유 해석을 풍부하게 + 페르소나별 salience는 텍스트에서"

원하는 "다르게 본다"를 **거의 공짜로** 살리는 길. vision은 여전히 1회.

- **(a) 해석을 더 풍부하게 (여전히 1회 vision). ✅ 적용 완료.** 지금 `interpret_ad`가 메시지·타깃·가격만 뽑는데, 여기에
  **"시각 요소 인벤토리"**(모델 얼굴/제품샷/로고/카피 배치/색감/첫눈에 띄는 것)를 추가 추출해 공유 해석에 담는다.
  vision 비용은 그대로 1회. (`ad_interpreter.py` — 해석 프롬프트에 `visual_elements`, `structured_analysis`에 영속.)
- **(b) salience를 반응 프롬프트에서 페르소나 조건화. ✅ 적용 완료.** `reaction.py:_prompt`에서 "당신의 성격·소비가치상
  이 광고에서 *가장 먼저 눈에 들어오는 요소*는 무엇인가"를 페르소나 프로필 기반으로 고르게 한다. 가격민감
  페르소나는 가격에, 개방성 높은 페르소나는 비주얼에 — **같은 인벤토리, 다른 가중.** 추가 비용은 텍스트 토큰 약간.
  (`reaction.py` — 출력 `noticed_first` 필드 + salience 선택 지시, `PersonaReaction.noticed_first` 계약 필드로 흐름.)

이게 "보는 시점이 다르다"의 진짜 메커니즘(같은 자극, 다른 주의 배분)에 더 충실하고, vision N배 비용 없이 된다.

> **구현 상태(2026-06-19):** §4-(a)·(b) 모두 코드 반영 완료 — 시각 인벤토리(`visual_elements`)는 공유 해석에서 1회 추출되고,
> `noticed_first`(페르소나별 salience)는 같은 인벤토리를 프로필로 다르게 가중해 반응 JSON·`PersonaReaction` 계약·분석 핸드오프로 흐른다.
> `noticed_first`는 탐색적 텍스트 신호라 **DB 컬럼은 미반영**(필요 시 별도 PR로 `persona_reactions.noticed_first` + Alembic). §5 권고대로 페르소나별 원본 이미지 재투입은 **여전히 안 함**(vision 1회 유지).

### 비용 비교 (개념)

| 방식 | vision 호출 | 텍스트 호출 | "다르게 본다" 효과 | 교차검증 |
|---|---|---|---|---|
| 현재 (공유 해석) | **1** | N | 약함(공유 텍스트만) | 유지 |
| 제안 (페르소나별 재투입) | **N** | N | **거의 동일 추출 → 효과 미미** | 깨짐 |
| §4 대안 (풍부한 공유 + salience) | **1** | N | **강함(프로필별 주의 배분)** | 유지 |

---

## 5. 권고

- **지금(7/8 마감 안)** 원본 이미지 페르소나별 재투입은 **무리 맞다 — 하지 않는다.** 비용·지연 외에 효과
  자체가 안 나오고 교차검증이 깨진다.
- **개선하려면 §4 방식** — 공유 해석에 시각 인벤토리 추가(1회 vision) + 페르소나별 salience 텍스트 조건화.
  작고 안전한 변경이라 마감 안에 가능.
- **Phase 2 노트로만** 둘 변종 — 텍스트 해석 신뢰도가 낮을 때만 소수에게 downscale 이미지 보강, 또는
  "첫인상" A/B. 일반화는 발표 후.

### 한 줄 요약

**페르소나별 원본 이미지 재투입은 vision을 N배로 비싸게 하면서 "다르게 본다"는 정작 못 잡고 교차검증을
깬다. Deepsona·연구도 공유 텍스트 해석을 택한다. "다르게 본다"는 공유 해석을 풍부하게 만들고 페르소나별
salience를 텍스트 단계에서 조건화해 거의 공짜로 살린다.**

---

## 참고

- `backend/domain/simulation/adapters/gemini/ad_interpreter.py` (1회 VLM 해석 — 공유 해석 생성)
- `backend/domain/simulation/adapters/gemini/reaction.py` (`_prompt` — 페르소나에 텍스트 요약만 전달)
- `backend/domain/simulation/graph/run_graph.py` (`fan_out` — 같은 해석을 N명에 복사)
- [Deepsona — Agent-Based Framework for Multi-Trait Synthetic Audiences](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5805805)
- [Deepsona — AI market research platform](https://www.deepsona.ai/synthetic-audiences)
- [A Thousand Words or An Image: Persona Modality in Multimodal LLMs](https://arxiv.org/pdf/2502.20504)
- [Analyzing Persona Effects in Multimodal LLM Agents](https://arxiv.org/html/2605.29064)
