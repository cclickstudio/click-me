# 시뮬레이션 결과 JSON — 정리된 스키마 (전달용)

> 시뮬레이터 7번(반응 출력) 산출물 = 토론·분석 파이프라인의 입력 포맷.
> 현재 포맷에서 **중복·빈값·키 불일치**를 정리한 권장 스키마. 데이터 생성 측에 전달용.

## 1. 무엇을 바꿨나 (요약)

| 구분 | 현재 | 권장 | 이유 |
| --- | --- | --- | --- |
| `ad_analysis.structured_analysis` | 최상위 `detected_*`와 **완전 중복** | 하나만(평탄화) | 같은 값 두 벌 |
| `ad_features` | `structured_analysis` 안에 또 포함 | `ad_analysis.ad_features` 한 곳 | 중복 |
| `mismatch_detail` + `rubric_scores` | note·score가 **같은 내용 두 곳** | `ad_analysis.alignment[]` 하나로 통합 | 중복 |
| `_source` | persona마다 media+socio에 **40회 반복** | `meta.source` 전역 1회 | 같은 문자열 반복 |
| `consumption_values` | **3키 / 5키 혼재**(페르소나마다 다름) | **5키 고정**(누락 시 `false`) | 집계 분모 깨짐 |
| `profile_narrative` | 전부 `""` | 채우거나 **필드 제거** | 빈값 |
| `weight` | 전부 `1` | 기본 1이면 생략 가능 | 의미 없음 |
| `ad.asset_url` | 로컬 임시경로(`C:\Users\804\...Temp\...`) | **S3/접근가능 URL** | 다른 PC 경로·유출 |
| `target_filter` | `ad`·`simulation` 양쪽 `null` | 한 곳만(`simulation`) | 중복 null |
| `run_id` / `simulation_id` | 최상위 둘 다 | `meta`로 묶기 | 식별자 분산 |

> **유지(그대로 좋음)** — `personas`/`reactions`를 `persona_id`로 분리한 정규화 구조, `aggregate`, `aisas` 5단계 플래그.

## 2. 정리된 스키마

```jsonc
{
  "meta": {
    "run_id": "7d011148-...",            // 시뮬레이션 실행 1회
    "simulation_id": "488147f9-...",     // 영속화 FK
    "source": "KISDI 한국미디어패널 2024(d25)",  // (구) persona별 _source → 전역 1회
    "model_version": "gemini-2.5-flash-vision"
  },

  "ad": {
    "id": "96321d51-...",
    "project_id": "e561c41e-...",
    "title": "신라면",
    "media_type": "image",
    "asset_url": "https://<bucket>.s3.../ad.png",  // ★ 로컬경로 금지 → S3 URL
    "copy_text": "농심 신라면",
    "product_category": "음식",
    "ad_objective": "브랜드 인식 강화",
    "status": "DRAFT"
  },

  "ad_analysis": {                       // ★ 평탄화 — structured_analysis 제거, 필드 직접
    "detected_industry": "식품/라면",
    "detected_objective": "브랜딩 및 인지 유지",
    "detected_target": "라면을 즐겨먹는 일반 대중",
    "detected_message": "강렬하고 깊은 맛으로 삶에 활력을 주는 신라면",
    "intent_mismatch": false,
    "ad_features": {                     // 한 곳만
      "ad_credibility": 90,
      "ad_quality": 90,
      "price_mentioned": false,
      "original_price": null,
      "discounted_price": null,
      "brand_mentioned": true,
      "social_proof_strength": "none"
    },
    "alignment": [                       // ★ mismatch_detail + rubric_scores 통합
      { "dimension": "category", "declared": "음식", "detected": "식품/라면",
        "match": true, "score": 98, "note": "하위 범주로 정확히 일치." },
      { "dimension": "objective", "declared": "브랜드 인식 강화", "detected": "브랜딩 및 인지 유지",
        "match": true, "score": 90, "note": "핵심 목표 일치." },
      { "dimension": "message", "declared": "신라면", "detected": "강렬하고 깊은 맛...",
        "match": true, "score": 95, "note": "브랜드명 포함 + 특장점." }
    ]
  },

  "simulation": {
    "id": "7d011148-...",
    "ad_id": "96321d51-...",
    "panel_id": "panel-v1",
    "organization_id": "bd9df2e2-...",
    "target_mode": "AUTO",
    "target_filter": null,               // 타깃 지정 시만 채움(미지정 null)
    "sample_size": 20,
    "qa_passed_count": 20,
    "low_sample_warning": false,
    "status": "COMPLETED"
  },

  "personas": [
    {
      "persona_id": "P-00000",
      "age": 17,
      "gender": "M",                     // "M" | "F"
      "region": "서울",                   // 행정구역 or "기타"
      "ocean": { "openness": -0.15, "conscientiousness": 1.09, "extraversion": -0.84,
                 "agreeableness": 0.8, "neuroticism": -0.44 },
      "media_behavior": {
        "primary_medium": "스마트폰/휴대폰",
        "daily_media_minutes": 671,
        "meta_reach": 0.0807,            // Meta(인스타/페북) 광고 도달 확률
        "social_feed_reach": 0.1188,     // 소셜 피드 도달 확률
        "exposure_candidates": [
          { "timeband": "저녁", "medium": "PC", "activity": "동영상/개인방송", "place": "집" }
        ]
        // (구) _source 제거 → meta.source
      },
      "consumption_values": {            // ★ 5키 고정(누락 시 false, 3키 혼재 금지)
        "성능": false, "품질": true, "편의": true, "저렴한 가격": true, "취향·덕질": true
      },
      "socioeconomic": {                 // (구) _source 제거
        "income_bracket": "소득 없음", "income_code": 1, "education": "초등학교"
      }
      // weight: 기본 1이면 생략 / profile_narrative: 빈값이면 제거
    }
    // … personas N명
  ],

  "reactions": [
    {
      "persona_id": "P-00011",           // personas와 조인 키
      "exposure_context": "저녁·집·PC·동영상/개인방송",
      "aisas": { "attention": true, "interest": true, "search": false,
                 "action": false, "share": false },
      "drop_stage": "search",
      "drop_reason_tag": "no_reason_to_explore",
      "purchase_intent": 3,              // 1~5
      "trust": 5,                        // 1~5
      "rejected": false,
      "rejection_reason_tag": null,
      "emotion_tag": "indifference",
      "perceived_message": "신라면은 여전히 강렬하고 깊은 맛으로...",
      "perceived_target": "라면을 좋아하는 일반적인 사람들.",
      "utterance": "신라면은 늘 먹던 맛이니까...",
      "qa_passed": true,
      "qa_fail_reason": null
    }
    // … reactions N건 (personas와 1:1, persona_id로 매칭)
  ],

  "aggregate": {
    "click_intent_rate": 0.1, "ci_low": 0.0, "ci_high": 0.25,
    "purchase_intent": 3.6, "trust_avg": 4.85, "rejection_rate": 0.0,
    "variance_warning": false, "effective_n": 20
    // payload.qa_passed_count 제거 → simulation.qa_passed_count와 중복
  }
}
```

## 3. 필드 핵심 규칙

- **`personas` ↔ `reactions`** — `persona_id`로 1:1 매칭. 분리 유지(정규화 좋음).
- **`consumption_values`** — 키 5개(`성능`·`품질`·`편의`·`저렴한 가격`·`취향·덕질`) **항상 전부**, 값은 `true`/`false`. ← 현재 가장 큰 품질 이슈.
- **`gender`** — `"M"`/`"F"` 고정.
- **`meta_reach`·`social_feed_reach`** — 0~1 확률. 매체 전략 분석에 사용하므로 유지 권장.
- **`alignment[]`** — `dimension` ∈ {category, objective, message}, 각 declared/detected/match/score/note.
- **빈값 정책** — `profile_narrative`·`weight`처럼 항상 같은 값/빈값이면 생략(스키마에서 빼거나 기본값 문서화).

> 이 포맷이면 중복 4건·40회 반복·키 불일치가 사라지고, 같은 정보를 한 곳에서만 읽는다.
