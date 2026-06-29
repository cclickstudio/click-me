# P3 (초안) — 챗 소재·타깃·입찰 조치(REPLACE_CREATIVE·EXPAND_AUDIENCE·CHANGE_BID_STRATEGY)

> **상태: DRAFT.** Phase A(EXPAND/BID)는 구현 가능 수준, Phase B(REPLACE_CREATIVE)는 크로스도메인이라 **흐름·결정 정리** 중심(세부 코드는 결정 확정 + P2/P2b 머지 후).
> **루프 규칙(이 레포):** 서브에이전트 구현(커밋 안 함) → **커밋 전** `/codex:adversarial-review`(사용자) + `requesting-code-review` → 사소한 건 인라인·어려운 건 `/codex:rescue` → 커밋.

**Goal:** 챗에서 기존 캠페인의 **타깃 확장·입찰 전략 변경·소재 교체**를 사람 승인 프리뷰로 실행 → **8종 전부 챗 임베드 완료.**

**Architecture(두 부류, executor 입력 기준):**
- **Phase A — EXPAND_AUDIENCE · CHANGE_BID_STRATEGY (간단):** executor가 `target`만 읽음(파라미터 없음). PAUSE처럼 확인 카드 → 빌드+approve+execute.
- **Phase B — REPLACE_CREATIVE (무거움·크로스도메인):** executor가 `evidence_metrics["selected_candidate_id"]`를 읽음. 소재 후보는 **generator**가 만들고(개선=IMPROVE는 **시뮬레이터에 연결**), 챗은 **맥락 resolver**로 후보 출처를 정한다.

**적용 원칙(P2·P2b 승계, 필수):** 서버 정본(클라/LLM 입력 불신), **canonical campaign_id 결속**, invalid action **pause 강등 금지**·재질문, no-op/범위/방향 **서버 검증**, 후보 id도 **서버 발급 토큰 결속**(임의 id 금지), 사람 승인 게이트, `chat.py`·executor·`/approve`·`/execute` 미수정.

**선행(의존):** **P2·P2b 머지.** Phase B는 **별도 plan 권장**(아래 결정·불확실성 해소 후).

---

## 확인된 사실 (구현 의존)

- `executor.py`: `EXPAND_AUDIENCE`→`writer.expand_audience(target)`, `CHANGE_BID_STRATEGY`→`writer.change_bid_strategy(target)` — **target만**. `REPLACE_CREATIVE`→`writer.replace_creative(campaign_id, creative_id)`, `creative_id=evidence_metrics["selected_candidate_id"]`. REPLACE는 v1 **캠페인 단위**(개별 광고 선택 없음).
- 소재 = **광고 소재(ad creative)**. 세 액션 모두 **TIER_3**(사람 승인 통과).
- generator(`origin/feat/generator`): `POST /generations`(mode CREATE|IMPROVE) → `GET /candidates/{candidate_id}/render` → `POST /generations/{id}/select`. **IMPROVE 필수 입력 = `existing_ad_s3_key` + `simulation_summary`**(시뮬 연결점) + `improvement_direction`.
- management↔simulation 링크: `CreatedCampaign.simulation_id`(+ `POST /campaigns/{id}/link-simulation`).

---

## Phase A — EXPAND_AUDIENCE · CHANGE_BID_STRATEGY (먼저, 간단)

> PAUSE 동형. 파라미터 없음. P2 rescue 결과(canonical id 카드)를 그대로 잇는다.

- **A-1 백엔드:** `POST /campaigns/{id}/expand-audience`·`/change-bid-strategy` — `/pause` 미러(빌드 TIER_3 proposal + approve + execute). 프론트 api `expandAudience(id)`·`changeBidStrategy(id)`.
- **A-2 툴:** `manage_campaign` enum에 `expand_audience`·`change_bid_strategy` 추가(+프롬프트 1줄). invalid는 재질문(pause 강등 금지).
- **A-3 카드:** `ChatCampaignActionCard`에 두 라벨 추가 → canonical id 결속 → 확인 → 엔드포인트 → 결과. 프리뷰에 "Meta가 타깃 확장/입찰 변경 수행(세부 플랫폼 위임)" 안내.
- **A-4 검증:** pytest(빌더·tier)·lint/build·수동.

---

## Phase B — REPLACE_CREATIVE (그다음, 무거움) — 소재 출처 resolver

> 핵심: **대화/캠페인 맥락에서 후보 출처를 먼저 찾고, 없으면 받는다.** 우선순위 ①→②→③.

### Resolver (우선순위)
**① generator 시안(후보)이 이미 있나?** (이 캠페인에 연결/최근 generation — **시뮬 유무 무관**)
→ 후보가 이미 있으니 **그대로 선택**. "이 시안들 중 고르시겠어요?" → 후보 렌더(`/candidates/{id}/render`) → 선택.
→ **"generator만 돌린(시뮬 없는) 결과만 있는 경우"가 바로 이 경로** — 시뮬 안 거치고 후보를 바로 쓴다. 가장 가벼움.

**② generator 후보는 없고, 연결된 시뮬 결과만 있나?** (`CreatedCampaign.simulation_id`)
→ "그 결과로 개선 시안 만들까요?" → generator **IMPROVE**(`existing_ad_s3_key` + 그 시뮬의 `simulation_summary`) → 후보 → 선택.

**③ 둘 다 없나?**
→ "교체할 소재가 필요해요 — 이미지를 올리거나 기존 광고 링크를 주세요." → 소재 확보 → generator **CREATE 모드**로 생성(시뮬 불요) → 후보 → 선택.

**맥락 조합 → 경로 (정리):**

| generator 후보 | 시뮬 결과 | → 경로 |
|---|---|---|
| 있음 | 있음/없음(무관) | **① 후보 바로 선택** (시뮬 불요) |
| 없음 | 있음 | **② IMPROVE** (시뮬 summary로 개선 시안 생성) |
| 없음 | 없음 | **③ 콜드스타트** (업로드/링크 → CREATE 생성) |

> 핵심: **generator 후보가 있으면 ①이 최우선**(시뮬이 있든 없든) — "generator만 돌린 경우"·"generator+시뮬 둘 다"는 모두 ①. 시뮬은 후보가 **없을 때** ②의 개선 입력으로만 쓰인다.

**공통 꼬리:** 후보 선택 → `REPLACE_CREATIVE` proposal(`selected_candidate_id`, 서버 빌드·finalize) → 프리뷰(선택 소재) → approve+execute → `replace_creative(campaign_id, creative_id)`.

### 결정 (이 초안에서 확정)
- **③ 생성 방식 = CREATE 모드**(시뮬 없이 받은 소재로 신규 생성). IMPROVE는 ②(시뮬 있음)에서만. — 콜드스타트에 시뮬 강제 회피.
- **맥락 감지 = 캠페인 링크 우선**(`CreatedCampaign.simulation_id` 등 영속 링크). 세션 "방금 돌린 것" 추적은 nice-to-have(후속).

### Open (구현 전 해소 — 별도 plan에서)
1. **① 후보 검색 키** — generation↔campaign **역링크**가 있나? (있으면 ①이 가능; 없으면 ① 보류하고 ②③부터.)
2. **② `existing_ad_s3_key` 출처** — 캠페인 현재 광고 소재의 s3 키를 management가 들고 있나? 없으면 ②도 입력 필요.
3. **핸드오프 vs 임베드** — 풀 체인을 챗 카드에 임베드 vs generator 화면으로 핸드오프 후 결과만 반영. 크로스도메인 무게상 **핸드오프 1안** 가능.
4. **후보 id 신뢰** — `selected_candidate_id`는 서버 발급 generation/selection 토큰에 묶인 것만 허용(§보안).
5. **비동기 UI** — `/generations`는 task(스트림/폴링) + 이미지 후보 렌더 — 챗 카드의 대기·표시 처리.

### 단계적 구현 제안
- **B-1: ① 경로부터**(연결된 generation 시안 선택 → 교체) — 역링크(Open 1)만 있으면 제일 가벼움.
- **B-2: ② IMPROVE**(연결 시뮬 → 개선 시안).
- **B-3: ③ 콜드스타트**(업로드/링크 → CREATE).
- 각 단계가 후보 선택→proposal→집행 **공통 꼬리**를 공유.

---

## 순서·종료
- **A(EXPAND/BID) 먼저** — P2 카드/툴 재사용, 2종 빠르게.
- **B(REPLACE_CREATIVE) 그다음** — resolver ①→②→③, **별도 plan**으로 정식화(Open 5건 해소 후). ①부터 단계 출하.
- **종료(8종 완성):** CREATE·PAUSE·ACTIVATE·INCREASE·DECREASE + EXPAND·BID + REPLACE → **8종 전부 챗 임베드.**

> **정식화 시:** P2 rescue·P2b 확정 코드(canonical id 결속, invalid action 재질문, 서버 검증 빌더, 라이브 소스 조회)를 A 엔드포인트·카드에 그대로 이식.
