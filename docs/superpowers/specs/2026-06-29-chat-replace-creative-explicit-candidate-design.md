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
- **검증 = mock.** B-1의 코드 게이트는 **`execution_mode`/`use_mock`** — non-sending(mock)에서만 계약·흐름을 검증한다(§6-⑦). (참고: LIVE라도 Meta 앱이 개발모드면 adcreative 생성이 거부되지만(B-0 Q0.4), 그건 코드 게이트가 아니라 외부 사유다.)

### 후속으로 미루는 것 (명시)

- **B-2 — 경로 ① 자동선택 + generation↔campaign 역링크(Open 1).** 캠페인에 연결된 시안을 자동 제시하는 경로는
  역링크 데이터모델이 선결이라 **별도 plan으로 후속 진행**한다. 본 plan은 역링크에 의존하지 않는다.

## 3. 아키텍처 — 빌드 시점 / 집행 시점 분리 (핵심 결정)

변환 사슬을 두 시점으로 나눈다. **adcreative(고아 위험 객체)는 승인 후에만 만든다.**

### 빌드 시점 (라우터/서비스, 승인 전)

1. **캠페인 소유권 검증** — `_require_owned_campaign(db, org_id, campaign_id)`로 "자기 캠페인만 교체"(파괴적 행위 차단).
2. **후보 핸드오프 (org 스코프)** — `GeneratorReadClient.get_candidate(generation_id, candidate_id, org_id=org_id)`. **org_id를 전달**해 generator GET이 내부 호출에도 `get_detail(generation_id, org_id)`로 스코프 → 타 org 후보면 404(§6-③). 프론트 `candidate_id` 불신.
3. **이미지 규격 검증** — 최소 사이즈·비율·파일크기·색상모드·alpha·JPEG 품질 확인(§6-⑥). 실패 시 **proposal 생성 실패(422), 집행 없음.**
4. **이미지 업로드 (mock 합성 해시)** — PNG→JPEG 변환 후 `upload_image`. **B-1은 non-sending(mock)에서만 호출** — 이때 `MetaAdsWriter.upload_image`는 실 `/adimages`를 치지 않고 `None`을 반환한다(실 Meta 자산 미생성). **`image_hash`는 REPLACE의 핵심(이미지 교체)이라 엔드포인트가 항상 채운다** — upload가 `None`이면 합성(`mockhash_<candidate_id>`)으로 폴백. 따라서 executor는 `image_hash`를 **필수**로 검사한다(없으면 계약 위반). `_is_sending_mode()`(validate/live)면 엔드포인트가 **501로 차단**(§6-⑦) — LIVE 범위.
5. **영향 광고 해상·결속** — `reader.get_creatives(campaign/ads)`로 광고 목록을 얻어 **`affected_ad_ids`(+candidate 요약)를 evidence_metrics에 결속**한다. `compute_proposal_hash`가 evidence_metrics를 덮으므로(`schemas.py:318`, 제외=proposal_hash/status/action_tier) **프리뷰가 본 광고 = 집행 대상**이 hash로 묶인다. `target_object_ids`는 캠페인 id 단일(멱등 키 정체성용, §4).
6. **proposal 빌드** — `budget_proposal` 미러로 서버가 빌드·finalize(아래 §5). evidence_metrics에 image_hash·copy(headline/body)·link_url·generation_id·candidate_id·**affected_ad_ids**·affected_ad_count.
7. **프리뷰** — 후보 이미지 + 영향 광고별 현재 썸네일/이름(§6-⑤).

### 집행 시점 (executor → writer, 승인 후)

8. **오케스트레이션 = writer `replace_creative_tree(campaign_id, ad_ids=…, ...)`**. executor의 REPLACE_CREATIVE 분기는 evidence_metrics의 결속된 `affected_ad_ids`를 넘겨 이 메서드 1개를 호출(executor 변경 최소).
9. writer 내부: **adcreative 1회 생성**(`create_ad_creative` → creative_id, **승인된 건만** → 고아 없음) → **결속된 `ad_ids`(빌드 시점 값)** 각각에 **ad 단위 `replace_creative(ad_id, creative_id)`** fan-out. **집행 시점 `_child_ids` 재조회 안 함** → 재해상에 의한 프리뷰↔집행 divergence가 없다. **단 이는 실세계 라이브 드리프트(승인 전후 Meta 광고 추가/삭제/이동) 차단이 아니다** — 그 경우 stale ad를 바꾸거나 새 ad를 놓칠 수 있어, **LIVE는 집행 시점 재검증(ad의 campaign/org 소속·현재 child set/version 비교, mismatch면 실패)을 추가**한다(§9). fan-out이 ad_ids를 직접 도므로 dry/mock도 fan-out 실행 → 검증 가능. 부분 실패 시 `succeeded_ad_ids`/`failed_ad_id`를 결과에 남기고 재시도는 같은 creative_id 재적용(멱등)으로 안전.
10. **멱등** — `create_ad_creative`는 같은 idem_key면 같은 creative_id를 돌려준다(mock: `mockcreative_{sha256(idem_key)[:16]}` — full-key digest로 충돌 회피, 리뷰 P1-b). 집행 retry(timeout/rate)나 멱등 재생 시 creative가 중복 생성되지 않는다. LIVE 멱등(Meta adcreatives create는 native idem 없음 → 이름 기반 dedup 또는 사전 조회)은 후속(§9).

> executor를 per-target 루프로 바꾸려면 "creative 1회 생성"을 루프 밖으로 빼는 배선이 필요해 변경이 커진다. 기존 `activate_tree`가 이미 "한 번 처리 후 자식 fan-out"을 writer 안에서 하므로, 동일 패턴으로 writer에 위임해 executor를 최소 변경한다.

> **왜 집행 시점인가.** 빌드 시점 생성은 취소/TTL 만료 시 orphan adcreative를 남긴다(B-0 리뷰 ①). 프리뷰는
> Meta creative가 미리 있을 필요가 없다(후보 S3 이미지로 충분). 따라서 adcreative 생성을 승인 후로 미뤄
> 고아를 원천 차단하고, generator 의존은 빌드 시점에만 둬 executor의 도메인 경계도 지킨다.

## 4. 데이터 계약 변경 (blast radius 명시)

- **REPLACE_CREATIVE의 `target_object_ids` = 캠페인 id**(단일, 멱등 키 정체성용). 교체될 **광고 목록은 evidence_metrics의 `affected_ad_ids`로 결속**(proposal_hash가 덮음). fan-out은 writer `replace_creative_tree(campaign_id, ad_ids=…)`가 그 결속 목록을 돈다(§3-9). evidence_metrics에 소재 필드(image_hash·headline·body·link_url)·affected_ad_ids·candidate 요약 적재.
- **`writer.replace_creative` 시그니처 정정 `campaign_id` → `ad_id`**(ad 단위 의미로 명확화, fan-out의 단위 호출). 동시 갱신 대상(확인됨):
  - `contracts/platform.py:70`(Port) · `adapters/meta/writer.py:123`(impl) · `execution/executor.py:392`(분기)
  - `tests/management/helpers.py:92`(mock) · `tests/management/test_meta_writer.py:65~78` · `tests/management/test_executor_gates.py:384·403`
- **신규 Writer 메서드 2종** — `create_ad_creative`(소재→creative_id) · `replace_creative_tree`(생성+fan-out 오케스트레이션). Port + impl + mock 추가.
- **마이그레이션 불요** — 제안은 영속되지 않고 request body로 집행된다(P3 §4-C). 하위호환 대상 없음.

## 5. 제안 엔드포인트

- `POST /campaigns/{id}/replace-creative-proposal` — `budget_proposal`(`management.py:2699`) 미러. proposal만 빌드해 반환(즉시 집행 안 함). 집행은 기존 `/approve`+`/execute` 재사용(미수정).
- Tier = TIER_3(기존 정책 불변). 사람이 프리뷰에서 승인.

## 6. 리뷰 반영 결정

> 번호 ①~⑩은 **리뷰 항목 id**(추가된 순서)이지 우선순위·읽는 순서가 아니다. ⑥⑦은 초기(B-0) 항목이라 나중에 추가된 ⑧⑨⑩ 뒤에 온다. 본문 교차참조(§3 등)는 이 id로 가리킨다.

- **① 고아 자산** — §3 집행 시점 생성으로 원천 차단. LIVE 정리정책: 부분 실패로 creative_id가 생긴 뒤 일부 광고만 교체된 경우, **생성된 creative_id를 결과 스냅샷·`audit_events`에 tag**한다. 삭제 가능하면 삭제, 아니면 **orphan 허용 + tag 추적**(LIVE 시 확정 — B-1은 mock이라 미발생).
- **② 계약 변경** — §4에 blast radius·무마이그레이션 명시.
- **③ 소유권/토큰 결속 (두 층)** —
  - **캠페인 소유권** — `_require_owned_campaign(db, org_id, campaign_id)`로 자기 캠페인만 교체.
  - **후보-org 누출 차단 (B-1에서 닫음)** — 확인된 활성 누출: generator `GET /generations/{id}`(`generator.py:289`)는 로그인 유저엔 org 스코프(불일치 404)지만 **내부 토큰 일치 또는 `use_mock`이면 org 검증을 우회**(`generator.py:303~306`)한다. management는 내부 토큰으로 호출하고 B-1 mock은 `use_mock=true`라 **임의 generation_id로 타 org 후보를 가져와 프리뷰 노출** 가능(기밀 누출, mock에서도 발생). → **수정:** generator GET이 **내부 호출에도 org 스코프**되게 한다. management가 `X-Org-Id`로 호출 org를 보내면, generator GET이 기존 `get_detail(generation_id, org_id)`(`generator_service.py:216` — org_id 주면 검증·None이면 우회)로 스코프(타 org면 None→404). `GeneratorReadClient.get_candidate`에 `org_id` 인자 추가. **이 변경은 generator 도메인을 건드린다(크로스팀 CODEOWNERS) — generator 팀 리뷰 + mock seed 데이터의 org 연결 확인 필요.** 같은 수정으로 기존 `from_candidate` 누출도 닫힌다. **경로별 정책(라운드3 확정):** internal 토큰 경로는 X-Org-Id 필수(없으면 400), 유저 세션·use_mock 무인증 브라우징은 헤더 없이 허용(§8·⑩·§9).
- **④ no-op** — 집행 시점 생성이라 creative_id는 항상 새값 → id 비교 no-op 무의미. **v1은 하드 no-op 게이트 없음.** 대신 **프리뷰가 현재/신규 소재를 나란히** 보여줘(§6-⑤) 사용자가 동일 여부를 눈으로 판단한다(v1은 자동 판정 안 함). LIVE 자동 판정 기준만 문서화: no-op = 후보 콘텐츠(이미지 s3_key + 카피)가 현재 광고 creative와 동일.
- **⑤ 프리뷰 정보** — `reader.get_creatives(campaign_id)`(`reader.py:465`)가 광고별 `ad_id·ad_name·image_url·thumbnail_url·headline·primary_text`(`CreativePreview`)를 반환(확인됨). 프리뷰 = 광고별 현재 썸네일/이름 + 새 후보 이미지.
- **⑧ 프리뷰=집행 결속 (재해상 divergence 차단, B-1 라운드 ①④)** — 빌드 시점 `affected_ad_ids`(+candidate 요약)를 evidence_metrics에 넣어 proposal_hash로 덮는다(`schemas.py:318` 확인). executor는 **결속된 ad_ids로 fan-out**(집행 시점 재조회 안 함) → 사용자가 프리뷰에서 본 광고와 실제 교체 대상이 일치하고, 감사/재검이 hash로 가능하다. **이는 "재해상 divergence" 차단이지 실세계 라이브 드리프트 차단이 아니다** — 라이브 드리프트(승인 전후 광고 증감/이동) 집행 시점 재검증은 LIVE 후속(§9).
- **⑨ affected_ad_ids 타입 방어 (B-1 라운드 P2-a)** — executor가 `affected_ad_ids`를 순회하기 전 **list/tuple이고 모든 원소가 비어있지 않은 문자열**인지 검증(문자열이 오면 글자 단위 fan-out 방지). 빌드 시 **중복 제거(순서 보존)**.
- **⑩ 라운드3 안전 보강** — (P1-1) `create_ad_creative`는 VALIDATE_ONLY에서 `execution_options=['validate_only']`로 실생성 차단. (P1-2) `replace_creative_tree`는 creative 생성 **전에** ad_ids(비어있지 않은 str 리스트)를 검증 — 빈 리스트로 고아 adcreative 방지. (P1-3) `GeneratorReadClient.get_candidate`는 **org_id 필수**(management 무스코프 조회 금지; 라우터 mock-lenient는 dev 한정·§9). (P1-4) 후보 copy(headline/body) 빈값이면 빌드 단계 **422 거부**(executor와 동일 규칙 — 승인 후 집행 실패 방지). (P2-1) 재시도 시 creative 재생성은 mock 결정적 digest라 안전, LIVE는 idem_key→creative_id 저장/조회 후속(§9). (P2-4) dry/mock 분기를 먼저 반환해 Meta 설정 없이 동작. (P3-2) 이미지 차원·픽셀 상한(`_MAX_SIDE`·`_MAX_PIXELS`)으로 압축폭탄 차단.
- **⑪ 라운드4 정밀 보강** — (P1-1) ad_ids 검증에 `isinstance(list/tuple)`를 명시 — 문자열은 글자 단위 순회로 통과하므로 writer·FakeWriter·executor 모두 타입 체크(+writer string-거부 테스트). (P1-2) VALIDATE_ONLY에서 create가 실 id 없이 합성 id를 주면 그 id로 fan-out Meta 검증을 하면 "없는 creative"로 깨지므로 **fan-out 검증을 생략**하고 합성 성공 반환(실 생성은 LIVE 앱 모드 후). (P2-callsite) `get_candidate` org_id 필수화는 전체 call-site를 깨므로 Task 0에 `rg "get_candidate\("` audit 단계. (P2-image) `Image.MAX_IMAGE_PIXELS` 전역 변경 제거(사이드이펙트) — `validate_image_spec`의 헤더 직접 검사만 유지. (P2-jpeg) `to_meta_jpeg`가 디코드 전 `validate_image_spec`를 스스로 호출(public util 우회 방지). (P2-dedup) `affected_ad_ids`와 `preview.affected_ads`를 **같은 deduped 목록**에서 생성(개수 일치 보장). (P3) 공유 digest 헬퍼를 **public `synthetic_creative_id`**로 두고 테스트가 private import 안 하게.
- **⑥ 이미지 규격 검증** — 변환 단계(빌드 시점 §3-3)에서 검증. 실패·규격 불가 → proposal 생성 실패, 집행 없음.
- **⑦ LIVE 차단 기준** — 코드 게이트는 **`execution_mode`**(`writer._SENDING_MODES=(VALIDATE_ONLY, LIVE)` + `management_execution_mode` + `use_mock`), 앱 모드가 아니다(앱 개발모드는 LIVE를 코드가 허용해도 Meta가 거부하는 외부 사유). B-1은 mock(`use_mock` 또는 execution_mode≠live)에서 돈다. `create_ad_creative`는 `_is_sending_mode()`일 때만 Meta 호출, 아니면 합성 creative_id 반환.

## 7. 건드리는 파일

- `adapters/meta/writer.py` — `create_ad_creative`·`replace_creative_tree` 신규, `replace_creative` 시그니처 정정(`campaign_id`→`ad_id`), 모듈 헬퍼 `_synthetic_creative_id`.
- 변환 유틸 — PNG→JPEG(`png_to_jpeg`는 generator 소유 → `tools/`로 이동 또는 management 인라인) + 이미지 규격 검증.
- `api/routers/management.py` — `replace-creative-proposal` 엔드포인트(캠페인 소유권·org 스코프 핸드오프·규격검증·mock 업로드·광고 해상·proposal 빌드 오케스트레이션).
- `execution/executor.py` — REPLACE_CREATIVE 분기를 **`replace_creative_tree(campaign_id, ...)` 호출로 교체**. 기존 `replace_creative(target, selected_candidate_id)` **직접 호출은 제거**. target=캠페인, 소재 필드는 evidence_metrics에서.
- `contracts/platform.py` — Port 시그니처(`replace_creative`(ad_id), `create_ad_creative`, `replace_creative_tree`).
- `adapters/generator/client.py` — `get_candidate`에 `org_id` 인자 + `X-Org-Id` 헤더(§6-③).
- **generator(크로스팀)** — `api/routers/generator.py` GET `/generations/{id}` 내부 토큰 분기를 `X-Org-Id` 기반 `get_detail(generation_id, org_id)`로 스코프(§6-③).
- 프론트 — P3 P1 포팅 카드(`ProposalActions`)에 후보 picker + 선택 소재·영향 광고 프리뷰 섹션(후속, P1 의존).
- 테스트 — `helpers.py`(mock writer) + `test_meta_writer.py`·`test_executor_gates.py` 갱신, 신규 라우터/흐름 테스트.

## 8. 테스트 (mock)

- **캠페인 소유권** — 타 org 캠페인 교체 요청 거부(403/404).
- **후보-org 누출 차단(§6-②, 두 층)** — ⓐ `GeneratorReadClient.get_candidate`가 `X-Org-Id`를 보낸다(라우터 테스트로 org 전달 캡처·단언). ⓑ **generator 라우터 경로별 테스트**: **internal token** 경로 → X-Org-Id 필수(없으면 400), 잘못된 org → 404, 올바른 org → 200. **유저 경로**(세션 org)·**use_mock 무인증 브라우징** → X-Org-Id 없이 200(기존 프론트/mock 안 깨짐, 리뷰 P2-c). 누출면(무스코프)은 internal 경로에서만 닫고 mock 우회 자체는 후속 점검(§9).
- 이미지 규격 검증 실패 → proposal 생성 실패(집행 없음).
- 빌드된 proposal: `target_object_ids`=캠페인 단일, evidence_metrics에 image_hash·copy·link_url·generation/candidate·**affected_ad_ids**·affected_ad_count, Tier-3.
- sending mode면 엔드포인트 501 차단(§6-⑦).
- **fan-out (결속 ad_ids)** — `replace_creative_tree`가 결속된 ad_ids를 직접 돌므로 **dry/mock에서도 fan-out이 실제로 실행**된다 → 각 ad에 `replace_creative` 호출됨을 검증(stub client 또는 FakeWriter 기록). executor 테스트는 `replace_creative_tree`에 결속 ad_ids가 전달되는지까지.
- **집행 멱등(두 축)** — ⓐ `create_ad_creative`가 같은 idem_key면 같은 creative_id 반환. ⓑ 같은 승인/idem으로 재실행 시 executor 멱등 재생으로 **중복 side effect 없이 같은 결과 스냅샷**(writer 재호출 없음).
- **image_hash 필수** — REPLACE 제안에 image_hash 누락 시 executor가 거부(텍스트-only creative 불허).
- 승인 게이트: 미승인 Tier-3 거부(기존 게이트 #4 회귀).
- LIVE 호출 없음.

## 9. Non-goals

- 경로 ① 자동선택 + 역링크(= B-2 후속).
- LIVE adcreative 생성·검증(Meta 앱 Live 모드 전환 후) + LIVE 멱등 dedup(§3-10).
- **LIVE 집행 시점 ad 재검증(후속)** — 결속된 `affected_ad_ids`가 집행 시점에도 같은 campaign/org 소속이며 존재하는지 재확인(라이브 드리프트: 빌드~집행 사이 Meta 광고 추가/삭제/이전). B-1 mock은 결속 ad_ids를 그대로 fan-out하고 LIVE에서 이 재검증을 추가한다.
- **`use_mock` 내부경로 우회 점검(후속, 보안)** — generator GET이 `use_mock`이면 internal token 없이도 내부 경로가 열린다(B-1은 X-Org-Id 필수화로 org 누출은 막음). `use_mock` 우회 자체가 테스트/dev 전용인지 별도 점검(B-1 범위 밖).
- **승인 전 side effect 제거(후속, P2-b)** — B-1은 이미지 업로드(adimages→image_hash)를 빌드 시점에 하되 mock(501 sending 차단)이라 실 자산이 안 생긴다. **LIVE를 열면 "외부 side effect는 승인 후에만" 원칙을 위해 업로드도 executor(집행 시점, create_ad_creative와 함께)로 이동**한다. 그 경우 evidence_metrics는 image_hash 대신 s3_key를 결속.
- 신규 generation 무거운 비동기 풀체인(이미 존재하는 후보 우선).
- generator D1 응답에 project/org를 **싣는** 계약 확장(B-1은 `X-Org-Id` 요청 스코프로 충분 — 응답 스키마는 안 바꾼다).
