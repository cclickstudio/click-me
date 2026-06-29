# P3 (초안) — 챗 소재·타깃·입찰 조치(REPLACE_CREATIVE·EXPAND_AUDIENCE·CHANGE_BID_STRATEGY)

> **상태: DRAFT.** Phase A(EXPAND/BID)는 구현 가능 수준, Phase B(REPLACE_CREATIVE)는 크로스도메인이라 **흐름·결정 정리** 중심(세부 코드는 결정 확정 + P2/P2b 머지 후).
> **루프 규칙(이 레포):** 서브에이전트 구현(커밋 안 함) → **커밋 전** `/codex:adversarial-review`(사용자) + `requesting-code-review` → 사소한 건 인라인·어려운 건 `/codex:rescue` → 커밋.

**Goal:** 챗에서 기존 캠페인의 **타깃 확장·입찰 전략 변경·소재 교체**를 사람 승인 프리뷰로 실행 → **8종 전부 챗 임베드 완료.**

**Architecture(두 부류, executor 입력 기준):**
- **Phase A — EXPAND_AUDIENCE · CHANGE_BID_STRATEGY (간단):** executor가 `target`만 읽음(파라미터 없음). 단 **Tier 3**라 `/pause`(한방 build+approve+execute) 미러가 아니라 **`budget_proposal` 미러** — proposal **빌드 엔드포인트 분리** → 카드 프리뷰(proposal_hash 노출) → approve+execute.
- **Phase B — REPLACE_CREATIVE (무거움·크로스도메인):** executor가 `evidence_metrics["selected_candidate_id"]`를 읽음. 소재 후보는 **generator**가 만들고(개선=IMPROVE는 **시뮬레이터에 연결**), 챗은 **맥락 resolver**로 후보 출처를 정한다. **⚠ `selected_candidate_id`는 generator DB UUID이지 Meta creative id가 아님**(아래 확인된 사실·Open).

**적용 원칙(P2·P2b 승계, 필수):** 서버 정본(클라/LLM 입력 불신), **canonical campaign_id 결속**, invalid action **pause 강등 금지**·재질문, no-op/범위/방향 **서버 검증**, 후보 id도 **서버 발급 토큰 결속**(임의 id 금지), 사람 승인 게이트, `chat.py`·executor·`/approve`·`/execute` 미수정.

**선행(의존):** **P2·P2b 머지.** Phase B는 **별도 plan 권장**(아래 결정·불확실성 해소 후).

---

## 확인된 사실 (구현 의존)

- `executor.py`: `EXPAND_AUDIENCE`→`writer.expand_audience(target)`, `CHANGE_BID_STRATEGY`→`writer.change_bid_strategy(target)` — **target만**. `REPLACE_CREATIVE`→`writer.replace_creative(campaign_id, creative_id)`, `creative_id=evidence_metrics["selected_candidate_id"]`. REPLACE는 v1 **캠페인 단위**(개별 광고 선택 없음).
- **Phase A 페이로드는 고정값**(`writer.py`): expand_audience=`{"targeting_optimization":"expansion_all"}`, change_bid_strategy=`{"bid_strategy":"LOWEST_COST_WITHOUT_CAP"}`. → 프리뷰에 **구체값을 그대로 표시 가능**(모호한 "플랫폼 위임" 불요).
- **기존 빌드 패턴 존재**: `/campaigns/.../pause`는 한방(build+approve+execute, Tier 1이라 무방)이나, `budget_proposal`(`management.py:2699`)은 **proposal만 빌드해 반환** → 카드가 `/approve`·`/execute`를 잇는다. **Phase A는 후자(budget_proposal) 패턴을 미러한다.**
- **⚠ id 불일치(확정):** `select_candidate`는 `generation.selected_candidate_id = <AdGenerationCandidate UUID>`를 저장(`generator_service.py:403`) — **generator DB UUID**이지 Meta adcreative id가 아니다. writer 독스트링도 "v1은 대상에 creative 참조를 거는 수준". 게다가 generator엔 별도 `publish_candidate`(IG 게시)가 있어 **select ≠ Meta creative 등록**. mock/dry에선 가려지나 LIVE 공통꼬리가 끊긴다. → Phase B 블로커.
- **⚠ REPLACE 대상 granularity(확정):** Meta creative는 **ad 레벨**에 붙는데 writer는 `campaign_id` 노드로 보낸다 → v1 mock 단순화. 실연동은 `activate_tree`의 `_child_ids` 패턴(`writer.py:478-505`)처럼 **하위 ad를 펼쳐** 대상을 정해야 하고, 프리뷰에 **영향받는 광고 수**를 보여야 한다. ③·④는 한 문제의 두 면(REPLACE writer가 Meta ad-creative 모델과 불일치).
- 소재 = **광고 소재(ad creative)**. 세 액션 모두 **TIER_3**(사람 승인 통과).
- generator(`origin/feat/generator`): `POST /generations`(mode CREATE|IMPROVE) → `GET /candidates/{candidate_id}/render` → `POST /generations/{id}/select`. **IMPROVE 필수 입력 = `existing_ad_s3_key` + `simulation_summary`**(시뮬 연결점) + `improvement_direction`.
- management↔simulation 링크: `CreatedCampaign.simulation_id`(+ `POST /campaigns/{id}/link-simulation`). **generation↔campaign 역링크는 없음**(`list_generations`는 Project→org 조인만) → Resolver ①의 게이팅 선결조건.

---

## Phase A — EXPAND_AUDIENCE · CHANGE_BID_STRATEGY (먼저, 간단)

> 파라미터 없음. P2 rescue 결과(canonical id 카드)를 그대로 잇는다. **단 Tier 3 — `/pause` 한방이 아니라 `budget_proposal`처럼 빌드/프리뷰/집행 분리.**

- **A-0 현재값 소스 확인 (선결 Task):** 프리뷰의 "현재 → 변경"과 **no-op 판정이 같은 현재값에 의존**한다. **현 리더로는 부족**(확정):
  - **BID**: 리더에 `bid_strategy` 필드 **없음**(`CampaignInfo`·`get_campaign_targeting` 미노출) → 현재값 조회 **불가**.
  - **EXPAND**: `get_campaign_targeting`(`reader.py:784`)은 age/gender·objective는 읽지만 writer가 토글하는 **`targeting_optimization`(expansion 플래그)는 안 읽음** → **부분만** 가능.
  - **분기 결정:** ⓐ 리더에 현재값 조회(campaign `bid_strategy`, adset `targeting_optimization`) **소량 추가** → 완전한 "현재 → 변경" + 서버 no-op 가능, ⓑ 추가 안 하면 프리뷰는 "**현재값 미확인, 변경 예정값만**"으로 정직하게 표기 + no-op는 best-effort. **plan에서 ⓐ/ⓑ 택1.**
- **A-1 백엔드:** `POST /campaigns/{id}/expand-audience-proposal`·`/change-bid-strategy-proposal` — `budget_proposal`(`management.py:2699`) 미러로 **proposal만 빌드해 반환**(TIER_3, 즉시 집행 안 함). 집행은 기존 `/approve`+`/execute` 재사용(미수정). 프론트 api `buildExpandAudienceProposal(id)`·`buildChangeBidStrategyProposal(id)`.
  - **왜 한방 금지:** EXPAND/BID는 Tier 3라 사용자가 **프리뷰에서 proposal_hash 결속 내용을 보고** 승인해야 한다. `/pause` 한방을 미러하면 카드 확인 클릭이 곧 집행이 돼 프리뷰↔승인 분리·감사 동등성이 흐려진다.
- **A-2 툴:** `manage_campaign` enum에 `expand_audience`·`change_bid_strategy` 추가(+프롬프트 1줄). invalid는 재질문(pause 강등 금지).
- **A-3 카드:** `ChatCampaignActionCard`에 두 라벨 추가 → canonical id 결속 → **프리뷰 표시** → approve+execute → 결과. **프리뷰 내용(모호한 "플랫폼 위임" 금지):**
  - **변경 의도(구체값):** expand=`targeting_optimization: expansion_all`(타깃 확장), bid=`bid_strategy: LOWEST_COST_WITHOUT_CAP`(최저비용 자동입찰)로 전환.
  - **현재 상태:** A-0 분기에 따름 — ⓐ면 현 값과의 diff, ⓑ면 "현재값 미확인, 변경 예정값만".
  - **플랫폼 위임 범위:** v1은 캠페인 단위 단일 토글(세부 타깃·입찰 수치 위임).
  - **되돌림·영향:** 되돌리려면 역조치(별도 승인) 필요함을 명시.
- **A-3b no-op 조건(액션별, 서버 검증):** 이미 같은 값이면 집행 무의미 → 빌드 단계에서 차단·재질문(line 12 no-op 원칙의 Phase A 구체화). 현재값 의존이라 **A-0 ⓐ에서만 강제**, ⓑ면 best-effort.
  - **EXPAND_AUDIENCE no-op:** 이미 `targeting_optimization=expansion_all`.
  - **CHANGE_BID_STRATEGY no-op:** 이미 `bid_strategy=LOWEST_COST_WITHOUT_CAP`.
- **A-4 검증:** pytest(빌더·tier·no-op)·lint/build·수동.

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

**공통 꼬리:** 후보 선택 → **Meta creative 등록/변환**(Open 0 — generator candidate_id → publish 가능한 Meta adcreative id) → **대상 ad 해상**(Open 0b — campaign 하위 ad 펼침) → `REPLACE_CREATIVE` proposal(서버 빌드·finalize, 영향 ad 수 포함) → 프리뷰(선택 소재·영향 ad) → approve+execute → `replace_creative(...)`. (변환·해상 미해소 시 LIVE 미동작 — Open 0/0b 블로커.)

### 결정 (이 초안에서 확정)
- **③ 생성 방식 = CREATE 모드**(시뮬 없이 받은 소재로 신규 생성). IMPROVE는 ②(시뮬 있음)에서만. — 콜드스타트에 시뮬 강제 회피.
- **맥락 감지 = 캠페인 링크 우선**(`CreatedCampaign.simulation_id` 등 영속 링크). 세션 "방금 돌린 것" 추적은 nice-to-have(후속).

### Open (구현 전 해소 — 별도 plan에서)
0. **[블로커] candidate_id → Meta creative 변환/등록** — `selected_candidate_id`는 generator DB UUID라 `replace_creative`가 그대로 쓰면 LIVE에서 끊긴다(확인된 사실). generator가 publish 가능한 **Meta adcreative id를 발급/등록**하는 단계가 있는지, 없으면 **변환 단계(소재 S3 → /adimages 업로드 → adcreative 생성 → 그 id로 replace)**를 어디(management writer vs generator)가 책임지는지 확정. **이게 안 풀리면 공통꼬리(REPLACE 집행)가 LIVE에서 동작하지 않는다.**
0b. **[블로커] REPLACE 대상 granularity** — campaign 단위 호출을 `_child_ids`로 **하위 ad에 펼칠지** 결정 + 프리뷰에 **영향받는 광고 목록/개수** 노출. (0과 한 묶음)
1. **[게이팅 선결] ① 후보 검색 키 — generation↔campaign 역링크 신설** — 현재 **역링크 없음**(확정). 따라서 ①은 "가벼운 첫 단계"가 아니라 **신규 데이터 모델·링크 작업**이다. 역링크가 서는 게 ① 착수의 선결조건 — **별도 plan에서 제일 먼저 확인**. 없으면 ① 보류하고 ②③부터.
2. **② `existing_ad_s3_key` 출처** — 캠페인 현재 광고 소재의 s3 키를 management가 들고 있나? 없으면 ②도 입력 필요.
3. **핸드오프 vs 임베드** — 풀 체인을 챗 카드에 임베드 vs generator 화면으로 핸드오프 후 결과만 반영. 크로스도메인 무게상 **핸드오프 1안** 가능.
4. **후보 id 신뢰** — `selected_candidate_id`는 서버 발급 generation/selection 토큰에 묶인 것만 허용(§보안). (0의 변환 결과 id도 같은 결속 적용.)
5. **비동기 UI** — `/generations`는 task(스트림/폴링) + 이미지 후보 렌더 — 챗 카드의 대기·표시 처리.

### 단계적 구현 제안
- **B-0: 블로커 spike (선행, 필수)** — Open 0(creative id 변환/등록) + Open 0b(대상 ad granularity)를 먼저 검증. 이게 풀려야 공통 꼬리가 LIVE에서 성립하므로 **B-1보다 앞선다.**
- **B-1: ① 경로부터**(연결된 generation 시안 선택 → 교체) — **단, 역링크(Open 1) 신설도 선결**(현재 없음). B-0 + 역링크가 서야 ①이 비로소 "가장 가벼운 경로"가 된다.
- **B-2: ② IMPROVE**(연결 시뮬 → 개선 시안).
- **B-3: ③ 콜드스타트**(업로드/링크 → CREATE).
- **순서:** B-0 → B-1 → B-2 → B-3. 각 단계가 후보 선택→(변환/해상)→proposal→집행 **공통 꼬리**를 공유.

---

## 순서·종료
> 큰 그림은 같은 P3에 두되, **구현 plan은 도메인 경계로 분리**한다 — Phase A=management 도메인 확장, Phase B=generator/simulation 크로스도메인 핸드오프.

- **P3a(EXPAND/BID) 먼저** — management 단독. P2 카드/툴 재사용 + `budget_proposal` 빌드 패턴 미러, 2종 빠르게.
- **P3b(REPLACE_CREATIVE) 그다음** — resolver ①→②→③, **별도 plan**으로 정식화. 선결: **Open 0/0b(id 변환·granularity 블로커) + Open 1(역링크) 해소 후** 착수. ①부터 단계 출하.
- **종료(8종 완성):** CREATE·PAUSE·ACTIVATE·INCREASE·DECREASE + EXPAND·BID + REPLACE → **8종 전부 챗 임베드.**

> **정식화 시:** P2 rescue·P2b 확정 코드(canonical id 결속, invalid action 재질문, 서버 검증 빌더, 라이브 소스 조회)를 A 엔드포인트·카드에 그대로 이식.
