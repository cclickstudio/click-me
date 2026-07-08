# 광고 시뮬레이터 — 3가지 분석 방식 설명서

> 팀원들이 각 분석 방식의 목적, 페르소나 구성, 계산 과정을 이해하기 위한 문서입니다.

---

## 목차

1. [공통 지표 정의](#1-공통-지표-정의)
2. [접근법 1: Individual Persona](#2-접근법-1--individual-persona)
3. [접근법 2: Persona Set](#3-접근법-2--persona-set)
4. [접근법 3: Synthetic Population](#4-접근법-3--synthetic-population)
5. [세 접근법 비교](#5-세-접근법-비교)

---

## 1. 공통 지표 정의

세 가지 접근법 모두 동일한 3개 지표를 계산합니다.  
지표는 순서대로 의존 관계가 있으며, 모두 **0~100 점** 범위입니다.

```
광고 특성 추출 (LLM)
        ↓
  ┌─────────────┐
  │  Interest   │  광고에 얼마나 관심을 갖는가?
  └─────────────┘
        ↓
  ┌─────────────┐
  │    Trust    │  광고를 얼마나 신뢰하는가?
  └─────────────┘
        ↓
  ┌─────────────┐
  │     PI      │  실제로 구매할 의향이 있는가?
  └─────────────┘
       (Purchase Intention)
```

---

### 1-1. 광고 특성 (Ad Features) — STEP 1

모든 접근법이 공유하는 선행 단계입니다.  1
LLM이 광고 텍스트를 분석해서 아래 값을 추출합니다.

| 항목 | 설명 | 범위 |
|---|---|---|
| `ad_credibility` | 광고 신뢰성 (증거, 현실성, 정직성) | 0~100 |
| `ad_quality` | 광고 품질 (명확성, 매력, 구조, CTA) | 0~100 |
| `price_mentioned` | 가격 언급 여부 | True/False |
| `original_price` | 정가 | 숫자 |
| `discounted_price` | 할인가 | 숫자 |
| `brand_mentioned` | 브랜드 언급 여부 | True/False |
| `social_proof_strength` | 사회적 증거 강도 | high/medium/low/none |

**Ad Credibility 공식**
```
Ad Credibility = (증거 제시 × 0.3) + (주장 현실성 × 0.4) + (언어 정직성 × 0.3)
```

**Ad Quality 공식**
```
Ad Quality = (메시지 명확성 × 0.3) + (시각적 매력 × 0.3) + (구조·논리 × 0.2) + (CTA 명확성 × 0.2)
```

---

### 1-2. Interest (관심도)

소비자가 이 광고에 얼마나 관심을 가지는가를 나타냅니다.

```
Interest = (Ad Quality × 0.4) + (Interest Relevance × 0.35) + (Product Involvement × 0.25)
```

| 변수 | 설명 | 출처 |
|---|---|---|
| `Ad Quality` | 광고 자체의 품질 | STEP 1에서 추출 |
| `Interest Relevance` | 광고 상품이 소비자 관심사와 얼마나 일치하는가 | LLM 판단 (0~100) |
| `Product Involvement` | 이 상품 카테고리가 소비자에게 얼마나 중요한가 | LLM 판단 (0~100) |

> **Interest Relevance 판단 기준**
> - 정확히 일치: 80~100
> - 부분적 일치: 40~80
> - 관련 없음: 0~40

---

### 1-3. Trust (신뢰도)

소비자가 이 광고와 브랜드를 얼마나 신뢰하는가를 나타냅니다.

```
Trust = (Ad Credibility × 0.3)
      + (Brand Influence × 0.25)
      + (Social Proof Impact × 0.2)
      + (Risk Moderation × 0.25)
```

**각 구성 요소 계산**

```
Brand Influence =
  브랜드 언급 O → persona.brand_preference
  브랜드 언급 X → 50 (중립)

Social Proof Impact =
  social_proof_base × (persona.social_influence_sensitivity / 100)

  social_proof_base:
    high   → 85
    medium → 65
    low    → 45
    none   → 30

Risk Moderation =
  100 - (persona.risk_aversion × 0.3)
  (위험 회피도가 높을수록 신뢰도 낮아짐)
```

---

### 1-4. Purchase Intention, PI (구매 의향)

Interest와 Trust를 바탕으로 실제 구매 가능성을 계산합니다.  
5개 인수를 단순 곱하면 값이 지나치게 낮아지므로, **기하평균** 방식을 적용합니다.

```
PI = sqrt(Interest_norm × Trust_norm)
   × cbrt(Price_Relevance × Brand_Relevance × Propensity)
   × 100
```

**각 구성 요소 계산 (모두 0~1 범위)**

```
Interest_norm = Interest / 100
Trust_norm    = Trust / 100

Price_Relevance:
  가격 미언급 → 0.50 (중립)
  가격 언급   →
    월 가처분소득 = income × 0.15
    base_ratio  = min(1.0, 월가처분소득 / 광고가격)
    가격민감도 보정 = (price_sensitivity - 50) / 500
    Price_Relevance = max(0.1, base_ratio - 가격민감도 보정)

Brand_Relevance:
  브랜드 언급 O → persona.brand_preference / 100
  브랜드 언급 X → 0.50 (중립)

Propensity = (50 + price_sensitivity / 2) / 100
```

**PI 판정 기준**

| PI 점수 | 반응 유형 |
|---|---|
| 60 이상 | Positive (구매 의향 있음) |
| 40 ~ 60 | Neutral (관망) |
| 40 미만 | Negative (구매 의향 없음) |

---

## 2. 접근법 1 — Individual Persona

### 개념

**특정 1명의 소비자를 깊이 분석**하는 방식입니다.  
"이 광고가 우리 핵심 타겟 고객에게 통할까?"라는 질문에 답합니다.

### 페르소나 구성

`config.py`에 직접 정의하며, 3가지 접근법 중 **가장 풍부한 정보**를 갖습니다.

```python
INDIVIDUAL_PERSONA = {
    "age": 35,
    "gender": "F",
    "occupation": "직장인 (마케터)",
    "income": 4_500_000,          # 월 소득
    "interests": ["건강", "인테리어", "육아", "스마트홈"],
    "price_sensitivity": 60,       # 0=가격 무관심, 100=매우 민감
    "brand_preference": 70,        # 0=브랜드 무관심, 100=브랜드 중시
    "social_influence_sensitivity": 65,  # 타인 의견 민감도
    "risk_aversion": 55,           # 위험 회피 성향
}
```

> `interests`와 `occupation`은 LLM 프롬프트에 직접 전달되어  
> Interest Relevance와 Product Involvement 판단에 활용됩니다.

### 프로세스 흐름

```
[STEP 1] 광고 특성 추출
         ↓
[STEP 2-A] LLM에게 페르소나 + 광고 전달
           → Interest Relevance 판단
           → Product Involvement 판단
         ↓
[STEP 2-B] Interest 공식 계산
         ↓
[STEP 2-C] Trust 공식 계산 (LLM 없이 수식)
         ↓
[STEP 2-D] Purchase Intention 공식 계산
         ↓
[STEP 2-E] LLM에게 정성적 분석 요청
           → 긍정 요인 / 부정 요인
           → 구매 이유 / 비구매 이유
           → 종합 요약
         ↓
[출력] 점수 + 정성 분석
```

### LLM 호출 횟수

| 호출 | 목적 |
|---|---|
| 1회차 | 광고 특성 추출 (STEP 1) |
| 2회차 | Interest Relevance + Product Involvement 판단 |
| 3회차 | 정성적 분석 생성 |

총 **3회**

### 출력 예시

```json
{
  "metrics": {
    "interest": 86.7,
    "trust": 74.9,
    "purchase_intention": 66.0
  },
  "response_type": "Positive",
  "qualitative": {
    "positive_factors": "건강과 스마트홈에 관심이 높아 제품 연관성이 높음...",
    "negative_factors": "가격이 다소 부담스러울 수 있음...",
    "purchase_reasons": "아이 건강을 위한 투자로 정당화 가능...",
    "non_purchase_reasons": "실제 효과 의문, 대안 검색 가능성..."
  }
}
```

### 언제 사용하나

- 핵심 타겟 고객이 명확하게 정의되어 있을 때
- "이 사람이 살까?"에 대한 심층 분석이 필요할 때
- 광고 카피 A/B 테스트에서 특정 페르소나 기준으로 비교할 때

---

## 3. 접근법 2 — Persona Set

### 개념

**사전에 정의된 5가지 소비자 유형을 동시에 비교**하는 방식입니다.  
"어떤 타입의 소비자가 이 광고에 가장 잘 반응할까?"라는 질문에 답합니다.

### 5가지 소비자 유형

| 유형 | 설명 | 특성 |
|---|---|---|
| Value-Seeking | 가격 대비 가치 최우선 | 가격민감도 高, 브랜드 무관심 |
| Premium-Seeking | 품질·프리미엄 경험 추구 | 가격 무관심, 브랜드선호 高 |
| Brand Loyal | 특정 브랜드 충성도 高 | 브랜드선호 최고 (95) |
| Trend Follower | 트렌드·주변 영향 민감 | 사회적영향 민감도 최고 (90) |
| Careful Reviewer | 꼼꼼하게 검토 후 결정 | 위험회피도 高, 사회적영향 민감 |

```python
# 각 유형의 속성값 예시
"Value-Seeking": {
    "price_sensitivity": 85,
    "brand_preference": 30,
    "social_influence_sensitivity": 40,
    "risk_aversion": 70,
}
```

### 페르소나 구성의 한계

Persona Set의 대표 페르소나는 **일부 속성이 고정**됩니다.

```python
persona = {
    "age": 35,          # 모든 타입 동일
    "gender": "M",      # 모든 타입 동일
    "income": 4_000_000,  # 모든 타입 동일
    "interests": [],    # 비어있음 — LLM이 타입 이름으로 판단
    # 심리 속성 4개만 유형별로 다름
}
```

LLM 프롬프트에는 숫자 대신 **타입 이름과 설명**이 전달됩니다.

```
소비자 유형: Value-Seeking
유형 설명: 가격 대비 가치를 최우선으로 고려하는 소비자
```

### 프로세스 흐름

```
[STEP 1] 광고 특성 추출
         ↓
[STEP 3] 5가지 유형 각각에 대해 반복:

  ┌──────────────────────────────────────┐
  │  LLM: 이 유형의 Interest Relevance  │
  │       + Product Involvement 판단    │
  │            ↓                        │
  │  Interest / Trust / PI 계산          │
  │            ↓                        │
  │  Positive / Neutral / Negative 판정 │
  └──────────────────────────────────────┘
         ↓ (5번 반복)
[출력] 타입별 점수 비교표 + 순위
```

### LLM 호출 횟수

| 호출 | 목적 |
|---|---|
| 1회차 | 광고 특성 추출 (STEP 1) |
| 2~6회차 | 각 타입별 Interest 구성요소 판단 (×5) |

총 **6회**

### 출력 예시

```
순위  유형               PI     반응
────────────────────────────────────
 1   Brand Loyal        72.2   Positive
 2   Premium-Seeking    68.5   Positive
 3   Careful Reviewer   55.1   Neutral
 4   Trend Follower     51.3   Neutral
 5   Value-Seeking      45.8   Neutral

최고 반응 타입: Brand Loyal (PI=72.2)
최저 반응 타입: Value-Seeking (PI=45.8)
```

### 언제 사용하나

- 타겟 세그먼트를 아직 좁히지 못했을 때
- "어떤 타입에게 집중해야 하나?" 전략 도출 시
- 광고 메시지를 타입별로 다르게 가져갈지 결정할 때

---

## 4. 접근법 3 — Synthetic Population

### 개념

**통계적으로 생성된 1,000명의 가상 소비자를 시뮬레이션**하는 방식입니다.  
"시장 전체에서 몇 %가 이 광고에 반응할까?"라는 질문에 답합니다.

### 1,000명 생성 규칙

실제 인구 분포를 참고한 통계적 분포로 생성합니다.

**성별 분포**
```
M: 48%   F: 52%
```

**연령 분포**
```
20대: 18%   30대: 21%   40대: 24%   50대: 23%   60+: 14%
```

**심리 속성 4개 — 정규분포 (0~100 클리핑)**
```
price_sensitivity           : 평균 55, 표준편차 20
brand_preference            : 평균 50, 표준편차 25
social_influence_sensitivity: 평균 50, 표준편차 20
risk_aversion               : 평균 50, 표준편차 20
```

> **주의**: 현재 income은 모든 클러스터에서 4,000,000원으로 고정됩니다.  
> 연령별 소득 차등 적용이 향후 개선 과제입니다.

### K-Means 클러스터링

1,000명을 **15개 그룹**으로 묶습니다.  
클러스터링에 사용하는 특징 벡터는 5개입니다.

```
특징 벡터 = [age, price_sensitivity, brand_preference,
             social_influence_sensitivity, risk_aversion]

K-Means (k=15, random_state=42)
```

비슷한 성향의 소비자들이 같은 클러스터로 모이며,  
LLM은 1,000번이 아닌 **클러스터당 1번, 총 15번**만 호출됩니다.

### 프로세스 흐름

```
[STEP 1] 광고 특성 추출

[STEP 4-1] 1,000명 가상 소비자 생성
           (성별/연령/심리속성 분포 기반)
                    ↓
[STEP 4-2] K-Means 클러스터링 (k=15)
           → 15개 클러스터 생성
                    ↓
[STEP 4-3] 각 클러스터 분석 (×15 반복)
  ┌─────────────────────────────────────────┐
  │  클러스터 평균값으로 대표 페르소나 생성  │
  │               ↓                         │
  │  LLM: interest_relevance               │
  │       product_involvement               │
  │       cluster_description              │
  │               ↓                         │
  │  Interest / Trust / PI 계산             │
  └─────────────────────────────────────────┘
                    ↓
[STEP 4-4] 가중치 평균 집계

  Avg Interest = Σ (클러스터_Interest × 클러스터_비율)
  Avg Trust    = Σ (클러스터_Trust    × 클러스터_비율)
  Avg PI       = Σ (클러스터_PI       × 클러스터_비율)
                    ↓
[출력] 시장 전체 반응 + 분포 + Top/Bottom 클러스터
```

### LLM 호출 횟수

| 호출 | 목적 |
|---|---|
| 1회차 | 광고 특성 추출 (STEP 1) |
| 2~16회차 | 각 클러스터별 Interest 구성요소 + 설명 (×15) |

총 **16회**

### 가중치 평균 계산 예시

```
클러스터 0: 68명 (6.8%) × PI=64.3 = 4.37
클러스터 1: 71명 (7.1%) × PI=48.7 = 3.46
...
클러스터 14: 65명 (6.5%) × PI=39.2 = 2.55
─────────────────────────────────────────
Avg PI = Σ = 51.9
```

### 출력 예시

```json
{
  "market_response": {
    "avg_interest": 63.4,
    "avg_trust": 61.2,
    "avg_purchase_intention": 51.9,
    "overall_response": "Neutral"
  },
  "response_distribution": {
    "positive": { "count": 237, "percent": 23.7 },
    "neutral":  { "count": 579, "percent": 57.9 },
    "negative": { "count": 184, "percent": 18.4 }
  },
  "top3_high_reactivity": [
    { "description": "40대 중간소득, 브랜드 선호 高", "pi": 72.1 },
    { "description": "30대 후반, 위험회피 낮음",     "pi": 68.4 },
    { "description": "50대 초반, 가격 무감각",       "pi": 65.9 }
  ],
  "top3_low_reactivity": [
    { "description": "20대, 가격 매우 민감",        "pi": 31.2 },
    ...
  ]
}
```

### 언제 사용하나

- "시장 전체에서 몇 %가 반응할지" 추정이 필요할 때
- 타겟 세그먼트를 데이터 기반으로 발굴하고 싶을 때
- 광고 예산 투자 대비 도달 가능한 구매 전환층 규모 추정 시

---

## 5. 세 접근법 비교

### 핵심 차이

| | Individual Persona | Persona Set | Synthetic Population |
|---|---|---|---|
| **분석 대상** | 1명 | 5가지 유형 | 1,000명 → 15 클러스터 |
| **답하는 질문** | 이 사람이 살까? | 어떤 타입이 반응할까? | 시장 몇 %가 반응할까? |
| **페르소나 구성** | 가장 풍부 (직업, 관심사 포함) | 유형 이름 + 4개 속성 | 수치 5개 (클러스터 평균) |
| **LLM 호출** | 3회 | 6회 | 16회 |
| **결과 형태** | 점수 + 정성 분석 | 타입별 순위 비교 | 시장 분포 + 세그먼트 |
| **분석 깊이** | 깊음 | 중간 | 넓음 |

### 출력의 성격 차이

```
Individual   →  "35세 여성 마케터는 PI=66, 살 가능성 있음. 이유는..."
                (누가, 왜)

Persona Set  →  "Brand Loyal이 가장 반응 좋고, Value-Seeking이 가장 낮음"
                (어떤 타입이)

Synthetic    →  "시장의 23.7%가 Positive, 핵심 세그먼트는 40대 중소득층"
                (얼마나 많이, 어느 집단이)
```

### 공통 계산 공식 요약

```
Interest = Ad_Quality×0.4 + Interest_Relevance×0.35 + Product_Involvement×0.25

Trust = Ad_Credibility×0.3 + Brand_Influence×0.25 + Social_Proof_Impact×0.2 + Risk_Moderation×0.25

PI = sqrt(Interest/100 × Trust/100)
   × cbrt(Price_Relevance × Brand_Relevance × Propensity)
   × 100
```

### 현재 구현의 한계 및 개선 방향

| 한계 | 현재 | 개선 방향 |
|---|---|---|
| 심리 모델 | 4개 임의 속성 | Big Five (OCEAN) 학술 모델 |
| 인구 통계 | 임의 파라미터 | 국가 통계청 데이터 기반 |
| income | 전 클러스터 고정 | 연령별 조건부 샘플링 |
| 속성 간 상관 | 없음 | 조건부 샘플링 (age→income 등) |
| LLM 편향 | 미처리 | 적대적 페르소나 추가 |
| 검증 | 없음 | 실제 캠페인 결과 대비 비교 |
