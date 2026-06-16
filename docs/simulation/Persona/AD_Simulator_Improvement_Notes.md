# 광고 시뮬레이터 — 현재 로직 보완점 (분석방식 비교 기반)

> 현재 구현(실데이터 grounding + 페르소나별 LLM 반응 + 가중 분포 집계)을 `AD_Simulator_Analysis_Methods.md`(공식 기반 3-접근법)와 비교해 도출한 **보완 과제**를 정리한다.
> 선행 문서: `PERSONA_GENERATION_STRATEGY (1).md`(§3.7 표본·가중) · `AD_Simulator_Analysis_Methods.md` · `checklist.md`.

---

## 0. 한 줄 요약

우리 방식은 MD가 적은 "개선 방향"(OCEAN·통계청 인구·연령별 소득·조건부 상관·검증)을 **이미 구현한 상위 버전**이다. 다만 MD의 **정량 모델(광고 특성·가격적합도)** 과 **3-모드 UX**는 흡수할 가치가 있고, 우리 쪽엔 **재현성·calibration·core 병합** 등 별도 보완점이 남는다.

---

## 1. 현재 방식 vs MD 방식 (요약)

| 축 | MD (3-접근법) | 현재 구현 |
|---|---|---|
| 페르소나 속성 | 임의 4속성, income 고정 | 실데이터(행안부·OCEAN·대학내일·KISDI·소득학력) |
| 점수 산출 | 공식(Interest/Trust/PI 가중·기하평균) | 페르소나별 LLM 반응(§3.5) → 코드 집계 |
| 규모 처리 | K-means 15클러스터 → 대표답 | 표본 N + 가중 평균·부트스트랩 CI·effective_n |
| 분석 모드 | Individual / Persona Set / Synthetic | 단일 파이프라인(sample_size·target_filter·allocation) |
| 검증 | 없음 | P9 방향성(연령×광고반응) |

---

## 2. 보완할 점 (우선순위)

### P1 — MD에서 흡수 (저비용·고효용)

1. **광고 특성 정량 추출 강화**
   - 현재: `GeminiAdInterpreter`가 업종·타깃·메시지만 추출.
   - 보완: `ad_credibility`·`ad_quality`·`price_mentioned`·`original_price`·`discounted_price`·`brand_mentioned`·`social_proof_strength`를 구조화 추출 → 반응 프롬프트·루브릭 입력으로 전달(반응 충실도↑, 루브릭 근거 강화).
   - 위치: `adapters/gemini/ad_interpreter.py`, `contracts/schemas.py(AdInterpretation)`.

2. **가격–소득 적합도 신호**
   - 현재: 소득(KISDI `socioeconomic.income_bracket`)은 페르소나에 있으나 가격 적합도에 미사용.
   - 보완: 광고가(①에서 추출) × 소득 구간으로 "이 사람에게 비싼가/적당한가" 신호를 반응 프롬프트에 주입(MD `Price_Relevance` 취지). 공식 강제 아닌 **LLM 입력 힌트**로.
   - 위치: `adapters/gemini/reaction.py` 프롬프트.

3. **3-모드 분석 UX**
   - 현재: 단일 파이프라인.
   - 보완: 같은 엔진 위에 **Individual(1명 심층)·Persona Set(대표 세그먼트 비교)·Synthetic(시장 전체 분포)** 3가지 보고서 형태로 노출. Individual = `sample_size=1` + 정성분석, Set = `target_filter`로 세그먼트별 호출, Synthetic = 현재 기본.
   - 위치: `api/routers/simulation/` + 서비스 옵션.

### P2 — 우리 내부 보완

4. **OCEAN 연령밴드별 유형비율**
   - 현재: 전체 유형비율(40대+도 20대와 동일 비율).
   - 보완: 논문 보충자료/BFI-K 확보 시 밴드별 `type_proportions` 분리. (데이터 의존 — 미공개)

5. **calibration / KOBACO 베이스라인 대비**
   - 현재: KPI는 미보정 분포(`click_intent_rate`는 실측 스케일 미환산). 구매의도 베이스라인 비교 없음.
   - 보완: 기획서 요구대로 KOBACO/공개조사 구매의도 베이스라인과 방향·상대크기 비교(절대값 환산은 금지 유지).

6. **재현성·비용 관리**
   - 현재: 반응 temperature↑(다양성용)이라 동일 입력 재현 어려움. 반응은 캐시 금지(설계상).
   - 보완: 모델 버전 핀 + `panel_version` 기록은 됨. 추가로 "재현 모드"(temperature 낮춤·seed) 옵션, 대규모 시 표본+가중(이미 §3.7)로 비용 통제 명문화.

7. **검증 확대 (P9)**
   - 현재: 연령×광고반응 미스매치 방향성 1건.
   - 보완: KOBACO/공개 한국 조사 1건 직접 대조 시연 추가(비순환 유지).

### P3 — 구조/운영 (발표 후)

8. **core/models 병합 + Alembic 정식화** — 현재 `domain/simulation/models.py`(로컬 SimBase). 추후 `core/models.py` 병합 + 마이그레이션 일원화.
9. **MDIS 심층 소비심리** — 체면·동조·눈치 등(`social_values_deep`) 추가.
10. **LLM QA 정밀화** — `GeminiQaGate`(opt-in) 존재. 광고무관·설정모순 판정 프롬프트 고도화 + 기본 활성화 검토.
11. **광고해석 VLM 입력 확장** — 현재 단일 이미지. 다중 프레임/영상 썸네일·A/B 소재 비교.

---

## 3. 유지할 강점 (MD 대비 우위 — 후퇴 금지)

- **실데이터 grounding**으로 다양성 강제(동질화 방어) — 임의 4속성으로 회귀 금지.
- **분포·신뢰구간 보존** — 클러스터 대표답(MD Synthetic)으로 축약 금지(§7 금지). 비용은 표본+가중(§3.7)으로.
- **§3.5 구조화 반응 계약**(AISAS 퍼널·거부사유 taxonomy·발화) — 분석팀 핸드오프.
- **검증(P9)·영속화(P8)·실 VLM** — MD엔 없음.

---

## 4. 권장 착수 순서

1. **①광고 특성 정량 추출** → ②가격–소득 신호 (반응·루브릭 충실도, 데이터 이미 보유).
2. **③3-모드 UX** (제품 가치, 엔진 재사용).
3. **⑤calibration·⑦검증 확대** (발표 설득력).
4. 나머지(P3)는 발표 후.

> 핵심 원칙은 변함없다 — **"숫자는 코드(집계), 문장·반응은 LLM", "다양성은 실데이터가 강제", "분포로 표기".** 보완은 이 원칙 위에서만.
