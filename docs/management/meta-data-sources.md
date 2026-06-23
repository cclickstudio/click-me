# ClickMe 광고 매니지먼트 — 메타 광고 지표 데이터 소스 & 가상화 전략

문서 v1.0 · 2026-06-11 · 쌍 문서: `structure-and-roles.md`

> **[갱신 2026-06-21]** 이 문서는 06-11 작성분으로, §9의 "전환·ROAS = Won't"는 이후
> `docs/superpowers/specs/2026-06-20-cvr-roas-재정의.md`(멘토 피드백)로 **해제**됐다.
> 전환은 설치·가입·리드로 재정의되고, 추정 ROAS·목표 기준 이상판정이 In scope다.
> §2②·§3.1·§5의 신호 스펙은 그대로 유효하며, 진단 agent의 LLM ReAct tool 세트 근거다
> (`agents/diagnosis_llm.py`). 추가된 성과 미달 축은 §5 표에 반영했다.
>
> **[갱신 2026-06-21 — 라이브 집행]** 읽기·Mock 너머로 **실 Meta 생성(PAUSED)·이미지 소재·
> 샘플 시안·실측 최소예산(₩1,521)**이 구현됐다 → **§11 신설**. 캠페인 생성은 자동 배치(FB/IG),
> 소재 미리보기는 `generatepreviews`(GET), 정책은 `campaign_policy.py` 단일원천→프론트 자동 반영.
> §9의 "LIVE 집행 = Won't"는 **생성 한정 부분 해제**(게재·과금은 여전히 사람이 활성화).

> **목적**: 실제 광고비를 쓰지 않고(가상/Mock) 인스타그램 광고 매니지먼트 에이전트를 구동하기 위해,
> "어떤 지표를, 어디서, 어떤 근거로" 가져올지 정리한 단일 참조 문서.
> 핵심 질문 = **"돈 안 쓰고 실제 메타 기준에 근거한 가상 지표를 만들 수 있는가?"** → 결론: **가능하다.**

---

## 0. 출발점 — 우리가 이미 가진 것

`delivery_estimate` 호출 결과 (`backend/domain/management/evals/fixtures/meta_delivery_estimate.json`):

```json
{
  "data": [
    {
      "estimate_mau_lower_bound": 17500000,
      "estimate_mau_upper_bound": 20600000,
      "estimate_ready": true,
      "daily_outcomes_curve": [
        { "spend": 0, "reach": 0, "impressions": 0, "actions": 0 }
      ],
      "estimate_dau": 0
    }
  ]
}
```

**중요 — 이건 "과거 데이터"가 아니라 "미래 예측치(forecast)"다.**
- `delivery_estimate`는 "이 타겟·예산이면 도달이 이 정도 나올 것"이라는 사전 추정.
- `estimate_mau 17.5M~20.6M` = 타겟 오디언스 모수 규모 (성과 아님).
- `daily_outcomes_curve`가 spend=0 한 점뿐 → 사실상 비어 있음.

→ **지표를 "명확히" 하려면 예측 엔드포인트가 아니라 실제 성과(actuals)를 주는 소스로 가야 한다.**

---

## 1. 핵심 전제 — 인스타 광고도 결국 Meta Marketing API

인스타그램은 별도 API가 없다. **메타 광고 시스템 안의 게재 지면(`publisher_platform = instagram`)** 일 뿐.
→ Facebook용으로 알려진 Insights / delivery_estimate / Ad Library가 그대로 적용되고, **인스타 필터만 추가**하면 된다.

### 인스타 광고에 꼭 필요한 계정 연결 구조
```
광고 계정(act_xxx) → 페이스북 페이지 → 연결된 인스타그램(프로페셔널/비즈니스) 계정
```
- 인스타 단독으로는 집행/조회 불가 → **반드시 FB 페이지에 인스타 계정 연동** 필요.
- 권한: 읽기 `ads_read`, 인스타 계정 정보까지 `instagram_basic` (+페이지 권한).

---

## 2. 메타가 광고를 "분석하는" 3가지 기준 (criteria)

소스보다 **분석 축**이 먼저다. 메타는 광고를 3개 렌즈로 본다.

### ① 경매 로직 (왜 내 광고가 안 나가는가)
```
경매 낙찰값 = 입찰가 × 추정 행동률(estimated action rate) × 광고 품질(ad quality)
```
→ 돈을 많이 써도 "추정 행동률 + 품질"이 낮으면 노출이 안 됨. `BID_LOSS`, `QUALITY_DEGRADED` 진단의 이론적 근거.

### ② 광고 관련성 진단 (Ad Relevance Diagnostics) — "메타 본인의 채점표"
광고(ad) 단위로 경쟁 광고 대비 백분위 제공. **"메타가 어떤 기준으로 분석하는지"의 가장 직접적인 답.**
- `quality_ranking` (품질 순위)
- `engagement_rate_ranking` (참여율 순위)
- `conversion_rate_ranking` (전환율 순위)
- 값: `above_average` / `average` / `below_average_10` / `below_average_20` / `below_average_35` / `unknown`
→ `QUALITY_DEGRADED` 감지의 1차 신호.

### ③ 성과 지표 (Insights) — 실제 숫자
①②가 "왜/얼마나 좋은가"라면 이건 "결과 숫자". 아래 §3 참조.

---

## 3. 지표 소스 — 두 트랙 (정의 vs 실제 값)

| | 트랙 1 — 지표 "정의/기준" | 트랙 2 — 지표 "실제 값" |
|---|---|---|
| 무엇 | 메타가 뭘 측정하는지(필드 정의) | 그 값이 현실에서 얼마인지 |
| 어디서 | **Meta Ads Insights API 공식 레퍼런스** | **업계 벤치마크 리포트** 또는 본인/테스트/대행 계정 Insights |
| 돈 | 무료(문서) | 무료(리포트) / 계정 과거 데이터 무료 |
| 한계 | 값은 없음, 정의만 | 남의 상업광고 실값을 주는 무료 공개 메타 API는 **없음** → 리포트로 대체 |

> **핵심**: 남이 돌린 인스타 광고의 실제 성과 숫자를 그냥 뽑아오는 **무료 공개 엔드포인트는 메타에 없다.**
> (Ad Library는 정치광고 + 범위값뿐.) → 실제 값은 ① 본인/테스트/대행 계정의 과거 Insights(무료) 또는 ② 공개 벤치마크 리포트로 잡는다.

### 3.1 트랙 1 — 실제로 사용하는 지표 (Meta Insights 공식 정의)
출처: <https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights>
참고: <https://developers.facebook.com/docs/marketing-api/reference/ad-report-run/insights/>

| 필드 | 메타 공식 정의 |
|---|---|
| `impressions` | 광고가 화면에 표시된 횟수 |
| `reach` | 광고를 본 순 계정 수 |
| `frequency` | 계정당 평균 노출 횟수 (impressions/reach) |
| `ctr` | 노출 대비 클릭 비율 |
| `inline_link_clicks` | 목적지 링크 클릭 수 (트래픽 목표의 진짜 KPI) |
| `inline_link_click_ctr` | 링크 클릭률 |
| `cpc` | 클릭당 평균 비용 |
| `cpm` | 1000노출당 평균 비용 |
| `spend` | 지출 |

호출 예시 (인스타 과거 데이터, 시계열 + 지면 분해):
```
GET /v23.0/act_{ad_account_id}/insights
  ?fields=impressions,reach,frequency,clicks,ctr,cpc,cpm,inline_link_clicks,inline_link_click_ctr,spend,actions
  &breakdowns=publisher_platform,platform_position
  &time_increment=1
  &time_range={'since':'...','until':'...'}
  &level=ad
```
- `publisher_platform` → `instagram` 행만 골라내면 인스타 성과만 분리.
- `platform_position` → `instagram_feed` / `instagram_stories` / `instagram_reels` / `instagram_explore`.
- `time_increment=1` → 하루 단위 시계열 (일중 곡선 모델링용).

> **주의 (Mock 설계에 직접 영향)**: breakdowns(시간/지면)를 걸면 `reach`·`frequency`는 **합산 불가**(중복 도달 때문에 추정치).
> → 누적 포화 모델로 reach를 따로 계산해야 맞는다.

#### 상태·심사·학습 단계 (Insights 아님 — Ad/AdSet 객체에서)
```
effective_status   # ACTIVE / PAUSED / DISAPPROVED / PENDING_REVIEW ...
issues_info        # 심사 거절 사유
learning_stage_info  # {status: LEARNING / SUCCESS / FAIL} (adset)
```
→ `REVIEW_*` / `LEARNING_PHASE` 감지용. Insights 호출과 합쳐야 진단이 완성됨.

### 3.2 트랙 2 — 실제 값 (2026 벤치마크)

**전 산업 중앙값**
- 출처: <https://www.triplewhale.com/blog/facebook-ads-benchmarks> (35,000개 브랜드, 2025)
- 출처: <https://redclawey.com/en/blog/meta-ads-benchmarks-2026-industry-data/>
  - CTR **1.7% ~ 2.2%** (상위 25% 2.8%+, 하위 25% 0.9%)
  - CPC **$1.18** (상위 $0.65 ~ 하위 $2.10)
  - CPM **$14 ~ $15** (상위 $8.5 ~ 하위 $28)

**목표(objective)별** — v1은 트래픽이라 이게 가장 중요
- 출처: <https://www.adamigo.ai/blog/meta-ads-benchmarks-2026-by-objective-and-placement>
  - **트래픽 목표: CTR ~1.71%, CPC ~$0.70** (목표 중 가장 저렴)
  - **인스타 지면별**:
    - 인스타 **Reels**: CPM **$4~$8** (가장 쌈)
    - 인스타 **Feed**: CPM **$10~$16** (비쌈, 전환은 높음)
    - 인스타 **Stories**: CTR ~1.34%, CPC ~$1.83

**한국 CPM (미국보다 낮은 경향)**

| 출처 | 한국 CPM | 미국 CPM | 배율 |
|---|---|---|---|
| lebesgue.io (2026, 이커머스) | **$5.80** | $16.08 | 미국이 약 2.8배 |
| AdAmigo.ai (2026, 45개국) | **$10.20** (범위 $8.5~12) | $23.00 | 미국이 약 2.3배 |

- 출처: <https://lebesgue.io/facebook-ads/facebook-cpm-by-country>, <https://www.adamigo.ai/blog/meta-ads-cpm-cpc-benchmarks-by-country-2026>
- **한계**:
  - 메타 공식이 아니라 **서드파티 집계**(자사 광고주 데이터 기반 추정). 공식 국가별 CPM은 메타 비공개.
  - 소스마다 한국 값이 **$5.80 vs $10.20**으로 2배 차이 → 절대값 신뢰구간 넓음. **방향성(한국<미국)은 일관**되나 정확한 숫자는 출처 의존적.
  - 대부분 이커머스/전 목표 혼합 → v1 트래픽 단독값 아님.

**데모용 발언**: "글로벌 벤치마크 근사치, 한국은 [lebesgue $5.80 / AdAmigo $10.20] 사이로 중간값 채택" 식으로 출처·불확실성 같이 공개 (정직성 전략, 문서 §7).

---

## 4. 가상(Mock) 지표 모델 — "원천 4개 + 파생 다수"

지표를 다 따로 랜덤 생성하면 모순 발생(예: CTR 좋은데 CPC도 비쌈). **3~4개 원천만 모델링하고 나머지는 수식 파생.**

### 4.1 원천 변수 (Mock이 직접 생성 — 노이즈/고장 주입은 여기에만)
| 변수 | 의미 | 성격 |
|---|---|---|
| `daily_budget` | 일일 예산 (입력 고정) | 입력 |
| `audience_size` | 타겟 모수 (= estimate_mau) | 입력 |
| `cpm(t)` | 1000노출당 경매가(₩) | 경매 환경 → BID_LOSS가 건드림 |
| `base_ctr` | 크리에이티브 본연의 클릭률 | 광고 품질 → QUALITY가 건드림 |

### 4.2 파생 지표 (수식 계산 — 절대 따로 안 만듦)
```
spend(t)        = daily_budget × pacing(t)          # pacing = 일중 곡선
impressions(t)  = spend(t) / cpm(t) × 1000
clicks(t)       = impressions(t) × ctr(t)
ctr(t)          = base_ctr × fatigue(frequency)     # 빈도 오를수록 감소

# 누적 도달/빈도 (오디언스 포화 모델)
cum_impr        = Σ impressions
reach           = audience_size × (1 − exp(−cum_impr / audience_size))
frequency       = cum_impr / reach

# 효율 지표 — 전부 나눗셈 파생
cpc             = spend / clicks
cpp             = spend / reach × 1000
inline_link_ctr = link_clicks / impressions
```
→ `ctr × impressions = clicks`, `spend / clicks = cpc`가 항상 일치 → 모순 없음.

### 4.3 일중 곡선 (pacing) — `exposure_model.py`의 baseline
인스타 노출은 균등하지 않고 **이중 봉우리**(점심 12~13시, 저녁 20~23시).
```
pacing(t): 0~6시 낮음 → 12~13시 1차 피크 → 오후 완만 → 20~23시 최대 피크
```
**정상 곡선 = 이 패턴**, 벗어나면 이상 감지.

### 4.4 현실적 기준값 (Mock 앵커, 한국 인스타 트래픽 기준)

| 원천/지표 | 정상 중심값 | 정상 범위 | 근거 |
|---|---|---|---|
| `cpm` | ₩10,800 | ₩7,800 ~ ₩13,800 | 한국 실측 lebesgue $5.80~AdAmigo $10.20 중앙값 |
| `inline_link_ctr` | 1.7% | 0.8% ~ 2.5% | 트래픽 CTR 1.71% |
| `cpc` (파생 검증용) | ₩635 | ₩600 ~ ₩2,400 | cpm/(ctr×1000) 파생, 트래픽 CPC $0.70 범위 내 |
| `frequency` | — | 1.0~2.5 정상 / 3+ 피로 | 도달 포화 |

> `cpm` 중심값 ₩10,800 = 한국 실측 두 출처(lebesgue $5.80≈₩7,800, AdAmigo $10.20≈₩13,770)의 중앙값.
> 코드 `policy.py`의 `CPM_ANCHOR_KRW=10_800`·`CPM_NORMAL_RANGE_KRW=(7_800, 13_800)`와 일치.

→ Mock이 `cpm`·`base_ctr`만 이 범위에서 뽑고 나머지를 파생하면 **실측 벤치마크와 정합하는 가상 데이터** 생성.

### 4.5 고장 5종 = 원천 변수를 비트는 방식 (정답 라벨 보존)

| FaultMode | 비트는 원천 | 결과 증상 |
|---|---|---|
| `BID_LOSS` | `cpm(t)` 급등 / 낙찰률↓ | 예산 남는데 impressions 급감, cpm↑ |
| `AUDIENCE_TOO_NARROW` | `audience_size` 작게 | reach 빨리 포화 → frequency 폭등, impressions↓ |
| `QUALITY_DEGRADED` | `base_ctr` 빠른 감쇠 + cpm↑ | ctr 하락, quality_ranking=below_average |
| `REVIEW_REJECTED` | `effective_status=DISAPPROVED` | impressions=0 (전 구간) |
| `REVIEW_DELAY` | 시작 시점 지연 | 승인 전까지 impressions=0 |

→ 고장을 주입한 원천 변수 = `AnomalyType` eval 정답 라벨.

---

## 5. AnomalyType ↔ 분석 신호 매핑 ("무엇을 분석해야 하는가")

| AnomalyType | 분석할 신호 (어떤 필드를 보나) |
|---|---|
| `REVIEW_REJECTED` | `effective_status=DISAPPROVED`, `issues_info` |
| `REVIEW_DELAY` | `effective_status=PENDING_REVIEW`가 grace 초과 |
| `BID_LOSS` | 예산 대비 `impressions`↓ + `cpm`↑ + `quality_ranking` 낮음 |
| `AUDIENCE_TOO_NARROW` | `reach` 정체 + `frequency`↑ + `estimate_mau` 작음 |
| `QUALITY_DEGRADED` | `quality_ranking`/`engagement_rate_ranking` below_average + `ctr`↓ + `frequency`↑(피로도) |
| `BUDGET_EXHAUSTED` | `spend`가 일일예산 도달 + 하루 끝 게재 급감 |
| `SCHEDULE_GAP` | 시간대별 노출 공백 (시계열 분석) |
| `LEARNING_PHASE` | `learning_stage_info.status=LEARNING` |
| `PERFORMANCE_BELOW_TARGET` ★신규 | `conversion_rate_ranking` 평균 이하 + 실/추정 `roas`가 고객 목표 미달(×0.7) + 세그먼트 breakdown(어떤 층이 끌어내리나) — **게재 고장이 아닌 성과 부진 축**(실데이터·고객 목표, FaultMode 아님) |

→ frequency 상승·CTR 하락 같은 "추세"는 단일 스냅샷으로 안 보임 → 시계열(`time_increment=1`) + 지면 분해 필요.

---

## 6. 타겟층(세그먼트) 데이터 — 근거화 방법

### 6.0 핵심 인식 — 지금까지 벤치마크는 "타겟층별"이 아니다
제공된 모든 벤치마크(CTR·CPC·CPM)는 아래 축으로만 분해됨:

| 분해된 축 | 안 된 축 (= 타겟층) |
|---|---|
| 산업, 지면, 목표, 국가 | **연령, 성별, 관심사, 오디언스 세그먼트** |

→ "$0.70 CPC, 1.71% CTR" = 전 연령·성별 평균(blended). 이 데이터로는 "20대 여성 vs 40대 남성" 진단 불가.
→ **메타는 연령·성별별 벤치마크를 공개하지 않는다** (<https://www.facebook.com/business/help/264160060861852>). 서드파티(Triple Whale, WordStream 등)도 산업·목표까지만, demographic 미제공.

### 6.1 세그먼트 데이터를 3개 층으로 분리

| 층 | 무엇 | 근거화 가능? | 소스 |
|---|---|---|---|
| ① **모수/구성** | 어떤 층이 인스타에 몇 명 있나 | ✅ 무료·실데이터 | Meta 추정 + 나스미디어/NapoleonCat |
| ② **수용도/구매의향** | 어떤 층이 광고에 반응·구매하나 | ✅ 무료·실데이터(한국) | **KOBACO MCR** |
| ③ **성과 효율** | 층별 실제 CTR/CPC/CPM | ❌ 공개 소스 없음 | 본인 계정 Insights뿐 |

### 6.2 ① 모수/구성 — 실데이터로 완전 근거화 (무료)

- **Meta 본인 제공**: `delivery_estimate`를 **타겟 연령별로 바꿔가며** 호출 → 메타가 직접 주는 **세그먼트별 `estimate_mau`**. **지출 0원**, 토큰만 필요. 가장 정확한 근거.
- **공개 통계** (나스미디어 NPR 2025, NapoleonCat/Statista): 한국 인스타 MAU **2,418만**, 도달률 52.6%, 1939세대 45.5%.

한국 인스타 연령×성별 실측 분포 (NapoleonCat, 2024-11, 13세+ 24,223,200명):

| 연령 | 여성 | 남성 |
|---|---|---|
| 18–24 | 16.9% | 12.8% |
| 25–34 | **18.6%** | 15.3% |
| 35–44 | 12% | 9.1% |
| 45–54 | 5.8% | 4.5% |
| 55–64 | 2.1% | 1.6% |
| 65+ | 0.6% | 0.7% |

→ "20·30대 여성이 핵심층(25~34세 전체 33.9%), 55+는 미미"가 **실데이터로 확정**. 문서 §7 "60+ 연령 데이터 약점"의 근거.
출처: <https://www.fortunekorea.co.kr/news/articleView.html?idxno=45680>, <https://blog.nasmedia.co.kr/entry/202510-trendissue-media1>

### 6.3 ② 수용도/구매의향 — KOBACO로 근거화 (무료·한국·이미 프로젝트 baseline)

**문서가 이미 KOBACO를 구매의향 baseline으로 못박음** (CLAUDE.md: "Purchase intent validation: Compare against **KOBACO baseline**").
KOBACO 소비자행태조사(MCR):
- 전국 13~64세 **5,000명**, 연1회, 싱글소스 면접조사
- 측정: **구매 시 광고 영향력**, 매체별 광고 집중도, 제품별 광고 관심도, **향후 지속 이용 의향**(=구매의향) — **연령·성별 교차분석 가능**
- **원시데이터(마이크로데이터) CSV/엑셀 무료 개방** (공공데이터포털, adstat.kobaco.co.kr) — 2018년 국가중점데이터 선정으로 전면 개방

→ "층별 광고 수용도/구매의향 가중치"를 **임의가 아니라 KOBACO 실측에서** 추출. 기존 검증 기준과 정합.
출처: <https://adstat.kobaco.co.kr/mcr/portal/introPage.do>, <https://www.data.go.kr/data/15034488/fileData.do>

### 6.4 ③ 성과 효율 (CTR/CPC/CPM by 층) — 여기만 진짜 임의

공개 소스 없음. 근거화하려면:
- **본인/테스트/대행 계정 Insights `breakdowns=age,gender`** — 단 실제 게재 = **소액 지출 필요** (예: 며칠 ₩5,000/일이면 층별 실CTR/CPC 확보).
- 또는 **Ad Library DSA**: EU 게재 광고는 **연령·성별 도달 분포** 공개(실데이터)지만 비용/CTR 없음 → 효율 아닌 도달 구성만.

### 6.5 합성 — "임의"가 "근거 기반"으로
```
세그먼트 지표 = ① 모수분포(NapoleonCat/Meta 실측)
              × ② 광고수용도·구매의향(KOBACO MCR 실측)
              × ③ 효율배수(이 부분만 가정 — 또는 소액 보정)
```
→ 3개 중 2개가 실데이터 → **"전부 임의 분배"가 아니라 "효율 배수 하나만 가정"**. 정직성 ↑.
발표 발언: "구성·구매의향은 NapoleonCat·KOBACO 실측, 효율 배수만 모델 가정."

> **단, Mock의 본질**: 이 프로젝트의 Mock은 "예측기"가 아니라 "테스트 하니스".
> eval 정답 = "현실과 일치"가 아니라 "주입한 고장을 맞혔는가". → 임의 분배 자체는 죄가 아니나, **"현실 반영"이라 주장하면 죄.**
> 세그먼트 breakdown은 문서상 **P2(7/8 이후)** 이므로, v1 데모는 blended로 가고 층별은 "가정"으로 라벨하거나 로드맵으로 시연.

---

## 7. Ad Library API & R&F (보조 소스)

### 7.1 Ad Library API (완전 공개, 단 지표는 부족)
- **일반 상업/인스타 광고**: 크리에이티브, 게재 시작일, 페이지 정도만. **성과 지표(CTR/CPC/노출수) 없음.**
- **정치·사회 이슈 광고만**: `impressions`(범위값), `spend`(범위값), `demographic_distribution`, `delivery_by_region`.
- 인스타 필터: `publisher_platforms=["INSTAGRAM"]`.
→ **크리에이티브 벤치마킹/트렌드용**으로는 유용, 지표 수치 보정용으로는 부족.

### 7.2 reachfrequencypredictions (R&F 예약형)
`/act_{id}/reachfrequencypredictions`로 `delivery_estimate`보다 정밀한 곡선 예측. 단 v1 "트래픽" 스코프 밖 → 우선순위 낮음.

---

## 8. 소스 정리표 (문서 스코프 기준 추천)

| 목적 | 엔드포인트/소스 | 공개여부 | 권한/비용 |
|---|---|---|---|
| **과거 실제 지표 (baseline·임계치·fixture)** | `insights` (`time_increment=1`, breakdowns) | 본인 계정 | `ads_read` |
| 미래 도달 추정 (이미 가져옴) | `delivery_estimate` | 본인 계정 | `ads_read` |
| 세그먼트별 모수 | `delivery_estimate` (타겟 연령별 반복 호출) | 본인 계정 | `ads_read`, 0원 |
| 공개 광고 크리에이티브/정치광고 지표 | Ad Library API | 완전 공개 | 앱 토큰 |
| 한국 인스타 연령×성별 구성 | 나스미디어 NPR / NapoleonCat / Statista | 공개 | 무료 |
| 한국 층별 광고 수용도·구매의향 | KOBACO MCR | 공개 | 무료 |
| 층별 실제 성과 효율(CTR/CPC) | 본인 계정 Insights `breakdowns=age,gender` | 본인 계정 | 소액 지출 |

### 운영 원칙 (structure-and-roles.md 연계)
- **§7 Should**: "Meta 읽기/`delivery_estimate`는 *실제 API 계약 검증* 수준까지만, 막히면 1일 내 철수." → Insights도 스키마/응답 형태 검증용으로만 붙이고, 데모는 `adapters/mock.py`로 구동.
- **§8**: "Meta API가 하루 이상 막히면 Mock 완성도로 인력 전환."

### 권장 흐름
1. 본인/테스트 계정으로 Insights를 **한 번** 호출 → 실제 응답을 `evals/fixtures/`에 **정상 골든 샘플**로 커밋.
2. 그 분포를 `exposure_model.py` baseline·`AnomalyType` 임계치 초기값으로 사용.
3. 데모는 Mock 곡선으로 재현 (게이트 #9 "Meta 연결 없이 데모 전체 사이클 재현" 충족).
→ "지표가 실제 메타 데이터에 근거한다" + "Meta 없이 데모 재현" 동시 만족.

---

## 9. 에이전트 기능 커버리지 (이 설계 기준)

> 결론: **이 데이터 설계는 "에이전트 로직 전체"를 커버한다. 단 "실제 성과 충실도"는 못 늘린다.** (둘은 다른 축)

### ✅ 완전 커버 — 에이전트 루프 전체 (Mock으로 충분)
정답 = "현실 일치"가 아니라 "주입한 고장을 맞혔는가" → Mock + 일중곡선 + 고장 5종으로 end-to-end 작동.

| 기능 (문서) | 커버 근거 |
|---|---|
| 게재 감지 (exposure baseline vs 관측) | Mock 일중곡선 = baseline |
| 이상감지 8종 (`AnomalyType`) | 고장 5종 주입 + 결정론 3종(예산소진·일정·학습) |
| 진단 agent ReAct (read-tool 4종) | metrics/상태/estimate/이력 전부 Mock 제공 |
| 승인 플레인 HITL (Tier 라우팅·만료·멱등) | 데이터 무관, 순수 로직 |
| 멱등 실행기 + 감사로그 | DRY_RUN/SANDBOX로 검증 |
| 재생성 agent (ActionProposal) | 시뮬 연계, 제안 패키징 |
| eval (정확도·혼동행렬·복구율) | 정답 라벨 = 주입 고장 |

→ **데모 1사이클(§11.4) 전부, 완료 게이트 11종(§6) 전부 커버.** 취업 키워드 5종(Agentic·Tool-use·HITL·Eval·리스크) 성립.

### 🟡 부분 커버 — 근거는 있으나 "방향성"까지
| 층 | 상태 |
|---|---|
| 집계 기준선 (CPM/CTR 임계치) | blended 벤치마크 근거 O, 절대값 신뢰구간 넓음 |
| 모수·도달 분포 by 세그먼트 | Meta estimate + NapoleonCat 실측 → 근거 O |
| 구매의향 by 세그먼트 | KOBACO MCR 실측 → 근거 O (기존 baseline과 정합) |

→ "이 광고는 20·30대 여성 도달이 핵심" 같은 **구성 기반 진단** 가능. "40대에서 CTR이 죽는다" 같은 **효율 기반 층별 진단**은 약함.

### ❌ 미커버 — 데이터로도 안 되는 것 (대부분 문서가 이미 Won't로 명시)
| 항목 | 이유 |
|---|---|
| **층별 실제 성과효율** (CTR/CPC by 연령·성별) | 효율 배수가 가정 → P2 + 소액 지출 없인 불가 |
| **시뮬점수 ↔ 실성과 상관** | 미검증 (문서: 발표에서 정직 공개, 로드맵만) |
| ~~전환·ROAS~~ → **해제(06-20)** · ~~LIVE 생성~~ → **부분해제(06-21, §11)** · 다중 플랫폼 | 전환·ROAS In scope. **LIVE 캠페인 생성(PAUSED)·이미지·시안도 구현**(게재·과금은 사람 활성화). 다중 플랫폼은 §7 **Won't** 유지 |
| 자동 Tier2 재배분, A/B 통계적 승자판정 | 문서 §7 **Won't** |

### 한 줄 요약
- **기능적 커버리지 = 100% (문서 Must 전부).** 진단→승인→실행→재생성→eval 루프가 정직하게 다 작동.
- **늘지 않는 것 = 실성과 충실도.** Mock은 예측기가 아니라 테스트 하니스 → 실제 광고 성과를 "맞히는" 능력은 이 설계로 안 생김(실계정 데이터의 영역).
- 이 미커버 목록 = 문서 §7 "발표에서 정직하게 말할 한계" 슬라이드 그 자체. **못 채운 게 아니라 의도적으로 그어둔 스코프 경계.**

---

## 11. 라이브 집행·소재·정책 (2026-06-21 추가 — 읽기 너머)

이 문서는 본래 **읽기/Mock 지표**가 중심이지만, 이후 **실 Meta 쓰기(생성)·소재·미리보기**와
**실측 정책**이 구현됐다. 모두 **생성은 PAUSED(무과금)**, 실제 게재(과금)는 사람이 활성화.

### 11.1 실측 최소 일예산 — 휴리스틱 금지·단일원천

- 소스: 광고계정 노드 `min_daily_budget` (실시간 조회, KRW floor). **2026-06 실측 ₩1,521.**
- `validate_only` 광고세트 검증으로 경계 확인 — **트래픽·리드 둘 다 ₩1,521 허용**, ₩1,000 거부.
  → 기존 2,021(버퍼)·10,000(리드 휴리스틱)은 **틀린 추측**이라 폐기. 목표별 최소 = floor 동일.
- 단일원천: `domain/management/campaign_policy.py` → `GET /api/management/campaign-policy`
  → 프론트가 숫자·라벨 그대로 렌더. **Meta 정책 변경 시 백엔드 한 곳만 고치면 프론트 자동 반영**
  (프론트 하드코딩 금지). 특별광고카테고리 라벨(신용→금융 상품·서비스 등)·연령(18~65)도 동일.

### 11.2 캠페인 생성 — 최적 구조(자동 분배)

```
캠페인(OUTCOME_LEADS/TRAFFIC) → 광고세트(예산·기간, is_adset_budget_sharing_enabled=false)
  → (리드면) 즉석 폼(leadgen_forms) → 광고(소재)
```
- **배치는 Meta 자동**: 광고세트 targeting에 `publisher_platforms` 미지정 → Advantage+ 자동
  배치로 **FB·인스타 등에 최적 분배**(우리가 수동 안 함). geo/age/gender만 지정.
- 일정: 일예산 광고세트는 **최소 24h 게재 예약 필수**(subcode 1487793) → start=미래, end≥+24h 보정.

### 11.3 광고 소재 이미지 + 샘플 시안

- 업로드: `POST /act_{id}/adimages` (멀티파트) → `images.<file>.hash` = **image_hash**. 자산 등록=무과금.
- 소재: `object_story_spec.link_data.image_hash`로 첨부.
- 시안(미리보기): **`GET /act_{id}/generatepreviews`** (`creative`+`ad_format`) → `data[].body` = Meta
  호스팅 iframe. **POST는 subcode 33으로 거부 → GET 전용.** 포맷 MOBILE_FEED_STANDARD·INSTAGRAM_STANDARD.

### 11.4 전환 실측 → CVR·ROAS (재정의 구현)

- `insights.actions`에서 전환 일반화: 구매뿐 아니라 **리드/가입/설치**도 전환으로 집계.
- **CVR = 전환수 ÷ 클릭(실측)**. **ROAS = (전환수 × 고객입력 전환가치) ÷ 지출(추정, '추정' 표기)**.
- 프론트 하이브리드: 실측 있으면 읽기전용, 전환 데이터 없는(미설정) 캠페인만 직접 추정 입력.

### 11.5 운영 안전·영속

- 목록: `GET /act_{id}/campaigns` **페이징 끝까지**(cursors.after) — 25개 초과도 누락 없음. 초안은 미반환.
- 삭제: `DELETE`(Meta 캠페인+자식) + DB는 **소프트 삭제(`deleted_at`)** 로 감사 이력 보존.
- 적재: 생성분을 `created_campaigns`(NeonDB)에 누적(meta_campaign_id 포함).
- 요청 한도(code 17): 대시보드는 **500 대신 안내 배너 + 기존 데이터 유지**(폴링 자동 복구).
- **GET 캐시(rate limit 절감)**: 공통 Meta 클라이언트가 GET 응답을 **TTL 캐시**(쓰기 시 무효화)해, 대시보드·예산·비교·어시스턴트가 같은 조회를 반복해도 한도를 덜 먹는다. 폴링 주기도 완화(+탭 비활성 시 중단).

### 11.6 파생 분석 데이터 소스 (읽기 위)

- **예산 페이싱**: 계정 단위 `insights(date_preset=this_month)` 소진 + 일자별(`time_increment=1`) + `funding`(선불 잔액) → 월 목표 대비 소진·런레이트·여력.
- **성과 전후 비교**: 시뮬 **예측(슬롯, PredictionReader)** ↔ **실측(RealOutcome)**. 예측=상대·실측=절대라 **환산 없이 방향성**만(`docs/superpowers/specs/2026-06-21-chat-management-agentic-rag.md` 원칙과 동일).
- **에이전틱 RAG 어시스턴트**: 위 실시간 지표(툴) + 정책·플레이북·KPI 규칙(pgvector KB)을 하이브리드 검색해 근거+인용 답변. 숫자는 항상 실측 툴에서(환각 방지).

---

## 10. 출처 모음

**메타 공식**
- Ads Insights API: <https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights>
- Insights 필드 레퍼런스: <https://developers.facebook.com/docs/marketing-api/reference/ad-report-run/insights/>
- 연령·성별 벤치마크 미공개 안내: <https://www.facebook.com/business/help/264160060861852>

**벤치마크 (서드파티)**
- Triple Whale (35,000 브랜드): <https://www.triplewhale.com/blog/facebook-ads-benchmarks>
- redclawey (2026 산업별): <https://redclawey.com/en/blog/meta-ads-benchmarks-2026-industry-data/>
- AdAmigo (목표·지면별): <https://www.adamigo.ai/blog/meta-ads-benchmarks-2026-by-objective-and-placement>
- AdAmigo (국가별 CPM/CPC): <https://www.adamigo.ai/blog/meta-ads-cpm-cpc-benchmarks-by-country-2026>
- lebesgue (국가별 CPM): <https://lebesgue.io/facebook-ads/facebook-cpm-by-country>

**한국 세그먼트 데이터**
- 나스미디어 NPR 2025: <https://blog.nasmedia.co.kr/entry/202510-trendissue-media1>
- NapoleonCat/Statista (포춘코리아 인용): <https://www.fortunekorea.co.kr/news/articleView.html?idxno=45680>
- KOBACO 소비자행태조사(MCR): <https://adstat.kobaco.co.kr/mcr/portal/introPage.do>
- KOBACO MCR 공공데이터포털: <https://www.data.go.kr/data/15034488/fileData.do>

> ⚠️ 벤치마크 수치는 서드파티 추정이며 절대값 신뢰구간이 넓다. 발표·문서에서는 항상 출처와 불확실성을 병기한다.
