# B-1 설계 — 챗 명시적 후보 선택으로 소재 교체 (REPLACE_CREATIVE)

> 브랜치 feat/management · 날짜 2026-06-29.
> 상위: `docs/superpowers/plans/2026-06-29-p3-chat-campaign-creative-targeting-bid.md`(P3 Phase B) ·
> 선행 spike findings: `docs/management/2026-06-29-replace-creative-conversion-spike-findings.md`(B-0).
> 이 문서는 P3b의 첫 출하분(공통 꼬리 + 명시적 후보)을 정식화한다.

---

## 1. 목표

매니지먼트 챗 카드에서, 기존 캠페인의 소재를 **사용자가 직접 고른 generator 후보**로 교체한다(REPLACE_CREATIVE).
핸드오프 → 변환 → 광고 단위 fan-out 교체를 **사람 승인 프리뷰**로 처리하며, 기존 정식 승인 경로
(`/approve`·`/execute`)를 재사용한다. spike가 닫은 공통 꼬리를 구현하고 **mock으로 계약·흐름을 고정**한다.

## 2. 범위 (잠금)

- **경로 = 명시적 후보 선택.** 사용자가 기존 generation의 후보를 고른다(신규 generation의 무거운 비동기는 최소화).
- **UX = 챗 카드 임베드.** 후보 목록·선택·프리뷰·승인을 카드 안에서 완결.
- **검증 = mock.** LIVE adcreative 생성은 Meta 앱 개발모드로 차단됨(B-0 Q0.4). 따라서 B-1은 mock에서 계약·흐름만 고정한다.

### 후속으로 미루는 것 (명시)

- **B-2 — 경로 ① 자동선택 + generation↔campaign 역링크(Open 1).** 캠페인에 연결된 시안을 자동 제시하는 경로는
  역링크 데이터모델이 선결이라 **별도 plan으로 후속 진행**한다. 본 plan은 역링크에 의존하지 않는다.

## 3. 아키텍처 — 빌드 시점 / 집행 시점 분리 (핵심 결정)

변환 사슬을 두 시점으로 나눈다. **adcreative(고아 위험 객체)는 승인 후에만 만든다.**

### 빌드 시점 (라우터/서비스, 승인 전)

1. **캠페인 소유권 검증** — `_require_owned_campaign(db, org_id, campaign_id)`로 "자기 캠페인만 교체"(파괴적 행위 차단).
2. **후보 핸드오프 (org 스코프)** — `GeneratorReadClient.get_candidate(generation_id, candidate_id, org_id=org_id)`. **org_id를 전달**해 generator GET이 내부 호출에도 `get_detail_for_org`로 스코프 → 타 org 후보면 404(§6-③). 프론트 `candidate_id` 불신.
3. **이미지 규격 검증** — 최소 사이즈·비율·파일크기·색상모드·alpha·JPEG 품질 확인(§6-⑥). 실패 시 **proposal 생성 실패(422), 집행 없음.**
4. **이미지 업로드 (mock 한정)** — PNG→JPEG 변환 후 `upload_image`(adimages) → `image_hash`. **B-1은 non-sending(mock)에서만 업로드한다** — `_is_sending_mode()`(validate/live)면 실제 `/adimages` 호출이 되므로 **sending mode는 LIVE 범위로 차단**(§6-⑦). (업로드 자산은 해시 dedupe라 고아 위험 낮음.)
5. **영향 광고 해상 (프리뷰·evidence용)** — `reader.get_creatives(campaign 하위 ads)`로 광고 목록을 얻어 **evidence_metrics(`affected_ad_count`)·프리뷰에만** 싣는다. **`target_object_ids`는 캠페인 id 단일**(§4) — 하위 광고 fan-out은 집행 시점 writer가 한다.
6. **proposal 빌드** — `budget_proposal` 미러로 서버가 빌드·finalize(아래 §5). evidence_metrics에 image_hash·copy(headline/body)·link_url·generation_id·candidate_id·영향 광고 수.
7. **프리뷰** — 후보 이미지 + 영향 광고별 현재 썸네일/이름(§6-⑤).

### 집행 시점 (executor → writer, 승인 후)

8. **오케스트레이션 = writer `replace_creative_tree(campaign_id, ...)`** (`activate_tree` 패턴). executor의 REPLACE_CREATIVE 분기는 target=캠페인으로 이 메서드 1개를 호출(executor 변경 최소).
9. writer 내부: **adcreative 1회 생성**(`create_ad_creative` → creative_id, **승인된 건만** → 고아 없음) → `_child_ids(campaign/ads)`로 하위 광고 해상 → 각 광고에 **ad 단위 `replace_creative(ad_id, creative_id)`** fan-out.
10. **멱등** — `create_ad_creative`는 같은 idem_key면 같은 creative_id를 돌려준다(mock: `mockcreative_{idem_key}` 결정적). 집행 retry(timeout/rate)나 멱등 재생 시 creative가 중복 생성되지 않는다. LIVE 멱등(Meta adcreatives create는 native idem 없음 → 이름 기반 dedup 또는 사전 조회)은 후속(§9).

> executor를 per-target 루프로 바꾸려면 "creative 1회 생성"을 루프 밖으로 빼는 배선이 필요해 변경이 커진다. 기존 `activate_tree`가 이미 "한 번 처리 후 자식 fan-out"을 writer 안에서 하므로, 동일 패턴으로 writer에 위임해 executor를 최소 변경한다.

> **왜 집행 시점인가.** 빌드 시점 생성은 취소/TTL 만료 시 orphan adcreative를 남긴다(B-0 리뷰 ①). 프리뷰는
> Meta creative가 미리 있을 필요가 없다(후보 S3 이미지로 충분). 따라서 adcreative 생성을 승인 후로 미뤄
> 고아를 원천 차단하고, generator 의존은 빌드 시점에만 둬 executor의 도메인 경계도 지킨다.

## 4. 데이터 계약 변경 (blast radius 명시)

- **REPLACE_CREATIVE의 `target_object_ids` = 캠페인 id**(단일). 하위 광고 fan-out은 writer `replace_creative_tree`가 내부에서 한다(§3-9). evidence_metrics에 소재 필드(image_hash·headline·body·link_url) 적재.
- **`writer.replace_creative` 시그니처 정정 `campaign_id` → `ad_id`**(ad 단위 의미로 명확화, fan-out의 단위 호출). 동시 갱신 대상(확인됨):
  - `contracts/platform.py:70`(Port) · `adapters/meta/writer.py:123`(impl) · `execution/executor.py:392`(분기)
  - `tests/management/helpers.py:92`(mock) · `tests/management/test_meta_writer.py:65~78` · `tests/management/test_executor_gates.py:384·403`
- **신규 Writer 메서드 2종** — `create_ad_creative`(소재→creative_id) · `replace_creative_tree`(생성+fan-out 오케스트레이션). Port + impl + mock 추가.
- **마이그레이션 불요** — 제안은 영속되지 않고 request body로 집행된다(P3 §4-C). 하위호환 대상 없음.

## 5. 제안 엔드포인트

- `POST /campaigns/{id}/replace-creative-proposal` — `budget_proposal`(`management.py:2699`) 미러. proposal만 빌드해 반환(즉시 집행 안 함). 집행은 기존 `/approve`+`/execute` 재사용(미수정).
- Tier = TIER_3(기존 정책 불변). 사람이 프리뷰에서 승인.

## 6. 리뷰 반영 결정 (B-0 라운드)

- **① 고아 자산** — §3 집행 시점 생성으로 원천 차단. LIVE 정리정책: 부분 실패로 creative_id가 생긴 뒤 일부 광고만 교체된 경우, **생성된 creative_id를 결과 스냅샷·`audit_events`에 tag**한다. 삭제 가능하면 삭제, 아니면 **orphan 허용 + tag 추적**(LIVE 시 확정 — B-1은 mock이라 미발생).
- **② 계약 변경** — §4에 blast radius·무마이그레이션 명시.
- **③ 소유권/토큰 결속 (두 층)** —
  - **캠페인 소유권** — `_require_owned_campaign(db, org_id, campaign_id)`로 자기 캠페인만 교체.
  - **후보-org 누출 차단 (B-1에서 닫음)** — 확인된 활성 누출: generator `GET /generations/{id}`(`generator.py:289`)는 로그인 유저엔 org 스코프(불일치 404)지만 **내부 토큰 일치 또는 `use_mock`이면 org 검증을 우회**(`generator.py:303~306`)한다. management는 내부 토큰으로 호출하고 B-1 mock은 `use_mock=true`라 **임의 generation_id로 타 org 후보를 가져와 프리뷰 노출** 가능(기밀 누출, mock에서도 발생). → **수정:** generator GET이 **내부 호출에도 org 스코프**되게 한다. management가 `X-Org-Id`로 호출 org를 보내면, generator 내부 토큰 분기가 기존 `get_detail_for_org(generation_id, org_id)`로 스코프(타 org면 404). `GeneratorReadClient.get_candidate`에 `org_id` 인자 추가. **이 변경은 generator 도메인을 건드린다(크로스팀 CODEOWNERS) — generator 팀 리뷰 + mock seed 데이터의 org 연결 확인 필요.** 같은 수정으로 기존 `from_candidate` 누출도 닫힌다.
- **④ no-op** — 집행 시점 생성이라 creative_id는 항상 새값 → id 비교 no-op 무의미. **v1은 하드 no-op 게이트 없음.** LIVE 기준만 문서화: no-op = 후보 콘텐츠(이미지 s3_key + 카피)가 현재 광고 creative와 동일.
- **⑤ 프리뷰 정보** — `reader.get_creatives(campaign_id)`(`reader.py:465`)가 광고별 `ad_id·ad_name·image_url·thumbnail_url·headline·primary_text`(`CreativePreview`)를 반환(확인됨). 프리뷰 = 광고별 현재 썸네일/이름 + 새 후보 이미지.
- **⑥ 이미지 규격 검증** — 변환 단계(빌드 시점 §3-3)에서 검증. 실패·규격 불가 → proposal 생성 실패, 집행 없음.
- **⑦ LIVE 차단 기준** — 코드 게이트는 **`execution_mode`**(`writer._SENDING_MODES=(VALIDATE_ONLY, LIVE)` + `management_execution_mode` + `use_mock`), 앱 모드가 아니다(앱 개발모드는 LIVE를 코드가 허용해도 Meta가 거부하는 외부 사유). B-1은 mock(`use_mock` 또는 execution_mode≠live)에서 돈다. `create_ad_creative`는 `_is_sending_mode()`일 때만 Meta 호출, 아니면 합성 creative_id 반환.

## 7. 건드리는 파일

- `adapters/meta/writer.py` — `create_ad_creative` 신규, `replace_creative` 시그니처 정정.
- 변환 유틸 — PNG→JPEG(`png_to_jpeg`는 generator 소유 → `tools/`로 이동 또는 management 인라인) + 이미지 규격 검증.
- `api/routers/management.py` — `replace-creative-proposal` 엔드포인트(캠페인 소유권·org 스코프 핸드오프·규격검증·mock 업로드·광고 해상·proposal 빌드 오케스트레이션).
- `execution/executor.py` — REPLACE_CREATIVE 분기를 **`replace_creative_tree(campaign_id, ...)` 호출로 교체**. 기존 `replace_creative(target, selected_candidate_id)` **직접 호출은 제거**. target=캠페인, 소재 필드는 evidence_metrics에서.
- `contracts/platform.py` — Port 시그니처(`replace_creative`(ad_id), `create_ad_creative`, `replace_creative_tree`).
- `adapters/generator/client.py` — `get_candidate`에 `org_id` 인자 + `X-Org-Id` 헤더(§6-③).
- **generator(크로스팀)** — `api/routers/generator.py` GET `/generations/{id}` 내부 토큰 분기를 `X-Org-Id` 기반 `get_detail_for_org`로 스코프(§6-③).
- 프론트 — P3 P1 포팅 카드(`ProposalActions`)에 후보 picker + 선택 소재·영향 광고 프리뷰 섹션(후속, P1 의존).
- 테스트 — `helpers.py`(mock writer) + `test_meta_writer.py`·`test_executor_gates.py` 갱신, 신규 라우터/흐름 테스트.

## 8. 테스트 (mock)

- 후보 핸드오프 + 캠페인 소유권 검증(타 org 캠페인 거부). 후보-org 검증은 후속(범위 밖).
- 이미지 규격 검증 실패 → proposal 생성 실패(집행 없음).
- 빌드된 proposal에 image_hash·copy·광고 target 적재, Tier-3.
- 집행: executor가 create_ad_creative(합성 id) → 각 광고 fan-out replace, 멱등.
- 승인 게이트: 미승인 Tier-3 거부(기존 게이트 #4 회귀).
- LIVE 호출 없음.

## 9. Non-goals

- 경로 ① 자동선택 + 역링크(= B-2 후속).
- LIVE adcreative 생성·검증(Meta 앱 Live 모드 전환 후) + LIVE 멱등 dedup(§3-10).
- 신규 generation 무거운 비동기 풀체인(이미 존재하는 후보 우선).
- generator D1 응답에 project/org를 **싣는** 계약 확장(B-1은 `X-Org-Id` 요청 스코프로 충분 — 응답 스키마는 안 바꾼다).
