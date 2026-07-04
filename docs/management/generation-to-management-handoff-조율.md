# 광고 생성 → 매니지먼트 집행 핸드오프 — generator 팀 조율 문서

작성 2026-06-18 · 작성자 🅱(feat/management-boeun) · 대상 generator 팀 리뷰
관련 정본 `docs/management/structure-and-roles.md` (§4 승인·실행 파이프라인, §5 import 경계, §7 스코프)
관련 코드 `api/routers/generator.py`(/select·/advertise) · `domain/management/agents/regeneration.py`(CREATE_CAMPAIGN) · `domain/management/adapters/meta/writer.py`(create_campaign)

> **목적** 생성된 광고 후보를 **매니지먼트의 통제된 집행 파이프라인**(승인·멱등·예산 tier·감사)을 거쳐 캠페인으로 올리는 핸드오프 경로를 정의한다.
> 현재는 generator가 Meta로 **직접 집행**(`/advertise`)해 매니지먼트를 우회한다. 이 문서는 **(A) 집행 문 통일**을 목표 설계로 제안하되, **7/14 발표까지는 (C) 현행 공존**을 인정한다.

---

## 0. 전제 — 발표까지는 공존(C), 통일(A)은 발표 후

- **현행 유지**: generator `/advertise`(Meta 직행, PAUSED)는 발표 데모용으로 **그대로 둔다**. 단 "governed 아님(승인·감사 미적용)"으로 명시한다.
- **이 문서가 정의하는 (A)는 7/14 이후 착수.** 지금은 계약을 미리 못 박아 양 팀이 합의해두는 준비 작업이다.
- 근거 — 두 경로 모두 **PAUSED만 생성(실 지출 0, LIVE 비활성)** 이라 공존 리스크가 LIVE 전까지 이론적이고, 최종 7/8 직전 타 팀 리팩터는 일정 리스크가 크다.

---

## 1. 현재 상태 — Meta로 가는 문이 둘

```
경로 ① generator 직행 (현행, governed 아님)
  /select → /advertise → generator_service.advertise_candidate
          → adapters/meta_ads.MetaMarketingPublisher.create_ad_campaign
          → Meta Graph API (campaign→adset→creative→ad, PAUSED)
  ※ 승인·멱등·예산 tier·감사 전부 미적용

경로 ② 매니지먼트 통제 집행 (CREATE_CAMPAIGN, 재생성 처방에서만 사용 중)
  ActionProposal(CREATE_CAMPAIGN) → approval(Tier3) → executor 4단계
          → writer.create_campaign(PAUSED, idem_key) → audit_log
  ※ generator 후보를 받아들이는 입구가 없음
```

문제 — 매니지먼트 불변식("모든 집행은 executor를 거친다 / 무승인 액션은 어떤 경로로도 Writer에 닿지 않는다")이 ①에는 적용되지 않는다. **집행이 두 군데로 갈라져 감사·예산 통제에 구멍**이 생긴다(LIVE 시 실재화).

---

## 2. 목표 설계 (A) — 집행 문을 매니지먼트로 통일

generator는 **생성까지**, 집행은 **매니지먼트 한 문**으로. 매니지먼트가 후보를 **당겨오는**(pull) 방식이라 generator 쪽 변경이 최소다.

```
POST /api/management/campaigns/from-generation        ← 신규(매니지먼트 소유)
  body: { generation_id, candidate_id, daily_budget_krw, run_days, target_filter }
  흐름:
   1. 매니지먼트가 generator HTTP로 선택 후보 조회 (GET /api/generator/generations/{id})
        → s3_key · copy · (strategy·template 메타)
   2. CampaignConfig 구성 (creative=s3_key/copy · 예산 · 기간 · target · objective=traffic[v1])
   3. ActionProposal(CREATE_CAMPAIGN, campaign_config=…) 생성
   4. approval(Tier3 → 사용자 승인) → executor 4단계 → writer.create_campaign(PAUSED) → audit_log
  반환: { proposal_id, approval_status }
```

이미 존재하는 것 — `GeneratorHttpTool`(당겨오기 패턴) · `CampaignConfig` · `CREATE_CAMPAIGN` · `writer.create_campaign(PAUSED)` · 승인·executor·감사.
**신규로 만들 것 — 인입 엔드포인트 + 후보 fetch 어댑터(매니지먼트 소유) 둘뿐.**

---

## 3. generator 팀에 요청하는 것 (계약 1개)

(A)는 매니지먼트가 generator를 **HTTP로 당겨오므로**, generator 팀에 필요한 건 **"선택 후보 조회 응답 모양을 고정"** 하는 것뿐이다. 새 엔드포인트를 만들 필요 없음 — 기존 `GET /generations/{id}` 응답에 아래 필드가 **안정적으로** 포함됨을 보장.

### 3.1 핸드오프에 필요한 후보 필드 (기존 응답에서)

```
generation_id · candidate_id(선택된 것) · s3_key(크리에이티브) · copy(광고 카피)
· (선택) strategy · template_id · width/height
```

### 3.2 골든 샘플 (정상 1)

`fixtures/contracts/generator_candidate_for_handoff.json`
```json
{
  "generation_id": "g-11111111",
  "selected_candidate_id": "c-22222222",
  "candidate": {
    "candidate_id": "c-22222222",
    "s3_key": "generations/g-11111111/2.png",
    "copy": "지금 시작하면 첫 달 무료 — 오늘만.",
    "strategy": "urgency",
    "template_id": "t-promo-01",
    "width": 1080, "height": 1080
  }
}
```

---

## 4. generator 팀이 정해줄 결정 항목

- [ ] **D1. 후보 조회 응답 고정** — 위 3.1 필드를 `GET /generations/{id}` 응답에 안정 계약으로 둘 수 있나(필드명·구조 동결).
- [ ] **D2. /advertise 운명** — (A) 도입 후 generator 직행 `/advertise`는 (가)제거 / (나)매니지먼트 핸드오프 호출로 내부 전환 / (다)데모용으로 유지(governed 아님 명시) 중 무엇인가. (발표까지는 (다))
- [ ] **D3. 선택 상태 공유** — 핸드오프는 `/select`로 선택된 후보만 받나, 아니면 candidate_id를 직접 받나.
- [ ] **D4. 미선택/만료 의미** — generation 만료·후보 없음 시 매니지먼트 인입의 폴백.
- [ ] **D5. objective 매핑** — v1은 traffic 고정. generator의 `campaign_objective`(conversion 기본)와 매니지먼트 objective(traffic)의 매핑 규칙.

---

## 5. 경계·영향 (낮은 리스크)

- **(A)는 발표 후 작업** — 발표 데모는 현행 ① 그대로라 발표 일정 무영향.
- **generator 측 변경 최소** — 새 엔드포인트 불필요, 응답 계약 고정만(D1). `/advertise`의 운명은 D2에서 별도 합의.
- **매니지먼트 측** — 인입 엔드포인트·후보 fetch 어댑터 신설(매니지먼트 소유). generator 내부 import 0, HTTP로만(§5).
- **소유권** — 인입·어댑터·`CampaignConfig` 구성은 매니지먼트. generator는 후보 조회 응답 모양만 보장.

> 요청 요약 — **"선택된 후보 조회 응답(s3_key·copy 포함)을 안정 계약으로 고정"** 하나가 핵심이다. 그러면 매니지먼트가 당겨와 CREATE_CAMPAIGN으로 통제 집행한다. `/advertise` 직행의 운명(D2)은 발표 후 별도 합의.
