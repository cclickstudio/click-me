# B-0 Spike 설계 — REPLACE_CREATIVE 소재 변환·등록 + ad 레벨 교체

> **성격**: 조사 spike의 spec. "무엇을 확정하고, 어떻게 조사하고, 무엇으로 끝나나"를 고정한다.
> 산출물은 **결정 문서 + 던질 probe**이며 **프로덕션 코드는 0**이다(변환 구현은 B-1).
>
> **브랜치**: `feat/management` · **날짜**: 2026-06-29.
> **상위 plan**: `docs/superpowers/plans/2026-06-29-p3-chat-campaign-creative-targeting-bid.md`(P3) — 이 spike는 그 plan의
> **B-0(블로커 spike)** 를 정식화한 것이다. P3b(REPLACE_CREATIVE) 착수 전 선결.

---

## 1. 목표

B-1(REPLACE_CREATIVE resolver 경로 ①) 착수 전에, 다음 사슬이 **LIVE에서 성립하는지·어떻게 성립하는지** 확정한다.

```
generator 후보(S3 PNG + 카피)  →  Meta 게재 가능한 adcreative(creative_id)  →  캠페인 하위 ad의 creative 교체
```

종료 시 **B-1 경로 ① go/no-go 판정**과, 변환 책임 위치·크로스도메인 핸드오프 방식의 **추천안 잠금**을 제시한다.

---

## 2. 배경 (확인된 사실 — 코드 근거)

- **generator는 Meta Ads adcreative를 만들지 않는다.** 게시는 **Instagram Content Publishing**(`generator/adapters/instagram.py` — image_url+caption으로 미디어 컨테이너)으로만 한다. 후보(`AdGenerationCandidate`)가 가진 것은 **S3 PNG(`s3_key`) + 카피**뿐이다.
- **`select_candidate`는 generator DB UUID를 저장**한다(`generator_service.py:403`) — Meta creative id가 아니다.
- **management writer엔 부품만 일부 있다**: `upload_image`(→`/adimages`, image_hash 반환, `writer.py:330`) · `_build_link_creative`(object_story_spec 빌드). 그러나 **독립 `/act_/adcreatives` POST(creative 생성·id 반환)는 없고**, `replace_creative(campaign_id, creative_id)`는 **캠페인 노드에 mock 수준 참조만** 건다(`writer.py:123`, 독스트링 "v1은 대상에 creative 참조를 거는 수준").
- **executor**는 `REPLACE_CREATIVE`에서 `evidence_metrics["selected_candidate_id"]`를 그대로 `writer.replace_creative`에 넘긴다(`executor.py:387`). → mock/dry에선 가려지나 **LIVE 공통 꼬리가 끊긴다.**
- **참조 패턴**: `activate_tree`가 `_child_ids`로 캠페인 하위 adset/ad를 펼쳐 순회한다(`writer.py:478-505`) — ad 레벨 fan-out의 기존 본보기.

---

## 3. 조사할 질문 (spike의 본체)

### Open 0 — 변환/등록

- **Q0.1 변환 단계** — 후보 S3 PNG + 카피 → Meta adcreative까지 정확한 단계 사슬? (JPEG 변환 필요 여부 → `upload_image`(`/adimages`)로 image_hash → `_build_link_creative`로 object_story_spec → **`/act_{id}/adcreatives` POST → creative_id**). 빠진 부품·순서를 코드/문서로 확정.
- **Q0.2 변환 책임 위치** — management writer(부품 보유) vs generator 중 어디가 변환을 소유하나? **추천안 + 근거 고정**(도메인 경계·기존 자산 재사용 관점).
- **Q0.3 크로스도메인 핸드오프** — 도메인 경계상 management는 generator 내부를 import 못 한다. 후보 **S3 키·카피**를 **(a) HTTP contract / (b) S3 키 직접 전달 / (c) contracts 스키마** 중 무엇으로 받나? **추천안 고정.**
- **Q0.4 [라이브 게이트]** `/act_{id}/adcreatives` POST가 우리 payload·토큰 권한(예: `ads_management`)으로 통과하나? `validate_only`를 지원하나?

### Open 0b — ad granularity

- **Q0b.1 fan-out 방식** — campaign 단위 → ad 단위 교체를 `activate_tree`의 `_child_ids` 패턴으로(하위 ad 펼쳐 각 `ad.creative` 갱신) 가는 게 맞나? 대안은?
- **Q0b.2 [라이브 게이트]** Meta에서 **기존 ad의 creative 교체**가 `POST /{ad_id} {creative:{creative_id}}`로 되나, 아니면 ad.creative가 사실상 불변이라 **새 ad 생성 + 기존 비활성** 패턴이 필요한가?
- **Q0b.3 영향 ad 조회** — 프리뷰용 "영향받는 광고 목록/개수"를 어떤 reader 호출로 얻나? (`_child_ids` / ads 리스트)

---

## 4. 방법 (하이브리드)

- **정적 조사 (대부분)** — Meta Graph API 문서(adcreatives 생성, ad 업데이트) + 기존 `writer.py`·`reader.py`·`client.py` 정독으로 **Q0.1~0.3 · Q0b.1 · Q0b.3** 추론.
- **라이브 게이트 (Q0.4 · Q0b.2 한정)** — 자격증명이 있을 때만 **`validate_only` probe**로 확정한다.
  - 던질 스크립트는 **scratchpad 또는 `backend/scripts/`에 두되 커밋하지 않는다.** mode=`validate_only`로 **실변경 0**.
  - 자격증명·권한이 없으면 해당 답을 **"문서 근거 추정 — B-1 구현 시 재확인"** 으로 정직하게 표기한다(추정을 확정으로 적지 않는다).
- 모든 probe는 읽기/검증 전용 — **실 게재·실과금·실 객체 생성 금지.**

---

## 5. 종료 기준 (Exit)

1. §3의 모든 Q가 **"확정(근거)"** 또는 **"추정(문서 근거 + B-1 검증 항목)"** 으로 닫힘.
2. **Q0.2(변환 책임 위치) · Q0.3(핸드오프 방식) 추천안 잠금.**
3. **B-1 경로 ① go/no-go 판정** 제시 — 막히면 무엇이 선결인지.
4. 결정 문서에 **B-1이 만들 Port/메서드 후보**(예: `create_ad_creative` 시그니처, ad-레벨 `replace_creative`)를 *제안*으로 정리(계약 잠금은 B-1에서 — 본 spike는 추천까지).

---

## 6. Non-goals

- 변환·교체 **코드 작성** (= B-1).
- **역링크(Open 1, generation↔campaign)** — 결이 다른 데이터 모델 작업이라 별도.
- 실 **LIVE 게시·과금** (probe는 `validate_only`까지만).
- contracts/Port **잠금** (본 spike는 추천안까지, 확정은 B-1).
