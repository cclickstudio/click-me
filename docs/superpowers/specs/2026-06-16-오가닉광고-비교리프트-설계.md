# 오가닉↔광고 게시물 비교·리프트 검증 설계 (🅰 백엔드)

작성: 2026-06-16 · 도메인: management(4-2) · 역할: 🅰 (감지·진단·분석, Writer 미호출)

## Context

광고 매니지먼트에 **"일반 게시물(오가닉) vs 실제 광고 태운 게시물"의 성과를 비교·검증**하는 기능이 필요하다. 같은 크리에이티브를 오가닉으로 올렸을 때와 광고로 집행했을 때의 도달·노출 차이(증분 리프트)를 보여, "광고가 실제로 추가 성과를 만들었는가"를 판정한다.

현재 백엔드 상태:
- `domain/management/adapters/meta/reader.py` — **광고(paid) insights만** 읽음 (`get_metrics`·`get_estimate`·`get_state`).
- **오가닉 게시물 인사이트를 읽는 코드는 전무.** IG 미디어/페이지 게시물 insights 어댑터·계산·DTO 모두 미구현.
- 토큰 스코프(`instagram_manage_insights`·`pages_read_engagement`·`read_insights`)는 이미 보유.

즉 비교 기능은 **백엔드부터 신규**다. 화면(SVG 시안 2종, `docs/management/mockup-organic-vs-paid-*.svg`)은 선행 작성됨 — 본 설계는 그 화면을 떠받칠 백엔드만 다룬다(프론트는 후속).

## 역할 경계 (🅰 기준)

- 본 기능은 **읽기 + 분석**뿐 — Writer 호출·지출 제안 없음 → A 경계 자연 충족.
- **공유 `contracts/`(platform·schemas·enums)는 건드리지 않는다.** 비교 산출물은 아직 A↔B 핸드오프 계약이 아니라 **A-내부 분석 결과**이므로, 전용 서브패키지 `comparison/`에 **A-로컬 DTO·Port**로 둔다. → 🤝 조율(별도 브랜치·골든샘플) 불요, A 단독 진행 가능.
- 추후 이 산출물이 B에게 넘어가는 계약이 되면 그때 `contracts/`로 승격(개정 시한 박기 원칙).

## 핵심 설계 결정

1. **새 서브패키지 `domain/management/comparison/`** — `detection/`·`execution/` 패턴 미러(순수로직 + `service/`). A 소유.
2. **A-로컬 계약** — `comparison/schemas.py`(`PostInsights`·`LiftResult`·`PostType`·`LiftVerdict`), `comparison/ports.py`(`OrganicInsightsReader`). `Contract` 베이스(frozen·extra=forbid·schema_version)는 기존 것 재사용.
3. **오가닉 어댑터 신규** — `adapters/meta/organic_reader.py`(`MetaOrganicReader`), 기존 `client.py` 재사용. v1은 IG 미디어 인사이트(`{media-id}/insights`).
4. **비교는 합성** — `ComparisonService`가 `OrganicInsightsReader`(오가닉) + 기존 `AdPlatformReader`(광고)를 합쳐 `LiftResult` 산출. 광고측은 기존 `reader.get_metrics` 재사용.
5. **판정 기준(SVG 시안과 동일)** — 증분 도달 배수 ≥ ×3 → 통과, ×1.5~×3 → 주의, 그 미만 → 미달. CI(신뢰구간)는 집계 데이터만으로 산출 불가 → **v1 제외(exploratory, 후속)**.
6. **mock 우선** — `adapters/mock.py`에 `MockOrganicReader` 추가. 데모·eval은 mock만으로 성립, `use_mock` 게이트 유지(실연동 영향 0).

## 아키텍처

### 폴더 (신규/수정)

```
domain/management/
├── comparison/                         [신규 · 🅰]
│   ├── __init__.py
│   ├── schemas.py    PostInsights · LiftResult · PostType · LiftVerdict
│   ├── ports.py      OrganicInsightsReader (Protocol)
│   ├── lift.py       compute_lift() 순수 함수
│   └── service/
│       ├── __init__.py
│       └── comparison_service.py       ComparisonService
├── adapters/
│   ├── meta/organic_reader.py          [신규 · 🅰] MetaOrganicReader
│   └── mock.py                         [수정 · 🅰] MockOrganicReader 추가
└── wiring.py                           [수정 · 🤝 append] build_organic_reader / build_comparison_service
```

### 데이터 흐름

```
organic_post_id ─▶ OrganicInsightsReader.get_post_insights ─▶ PostInsights(organic)
campaign_id     ─▶ AdPlatformReader.get_metrics ─▶ MetricsSnapshot ─▶ PostInsights(paid)
                                          │
                                          ▼
                              compute_lift(organic, paid) ─▶ LiftResult(증분·배수·판정)
```

### DTO 요지

- `PostInsights` — `post_id·post_type·as_of·reach·impressions·engagement·clicks·spend_krw`
- `LiftResult` — `post_id·organic·paid·reach_lift_abs·reach_lift_ratio·impressions_lift_abs·verdict·computed_at`

## 비고

- 오가닉/광고 도달은 중복될 수 있어 **단순 합산 금지** — 증분은 추정(분포·exploratory 표기). CLAUDE.md KPI 원칙(예측 CTR 실측 환산 금지) 준수.
- 오가닉 도달 0 시 배수 0division 방지 위해 분모 최소 1로 보수 처리(문서화된 근사).
- 페이지(FB) 게시물 insights·여러 게시물 일괄(테이블 뷰 B)은 v2.
- 라우터 노출(`/api/management/compare`)은 공유 파일이라 append-only + A 합의 후.
```
