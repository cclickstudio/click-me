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

1. **소유권 검증** — 프론트가 넘긴 `candidate_id`를 불신한다. 서버가 `generation`이 **로그인 org/tenant 소유**인지 검증한 뒤에만 진행(아래 §6-③).
2. **후보 핸드오프** — `GeneratorReadClient.get_candidate(generation_id, candidate_id)` → `HandoffCandidate(s3_key, copy)`. 기존 `from_candidate`(`management.py:1897`) 패턴 재사용.
3. **이미지 규격 검증** — 최소 사이즈·비율·파일크기·색상모드·alpha·JPEG 품질 확인(§6-⑥). 실패 시 **proposal 생성 실패(422), 집행 없음.**
4. **이미지 업로드** — PNG→JPEG 변환 후 `upload_image`(adimages) → `image_hash`. (업로드 자산은 해시 dedupe라 고아 위험 낮음. `from_candidate`도 빌드 시점에 image_hash까지 만든다.)
5. **영향 광고 해상** — `_child_ids(campaign 하위 ads)`로 광고 id 목록을 얻어 proposal의 `target_object_ids`에 적재.
6. **proposal 빌드** — `budget_proposal` 미러로 서버가 빌드·finalize(아래 §5). evidence_metrics에 image_hash·copy·generation_id·candidate_id·영향 광고 수.
7. **프리뷰** — 후보 이미지 + 영향 광고별 현재 썸네일/이름(§6-⑤).

### 집행 시점 (executor → writer, 승인 후)

8. **adcreative 생성** — `create_ad_creative(image_hash, copy)` → `creative_id`. **승인된 건에 대해서만** 생성 → 취소/만료 건은 아무것도 안 만들어져 **고아 없음**.
9. **fan-out 교체** — executor의 per-target 루프가 각 광고에 `replace_creative(ad_id, creative_id)`. `target_object_ids`가 광고 id라 기존 루프·멱등이 그대로 처리.

> **왜 집행 시점인가.** 빌드 시점 생성은 취소/TTL 만료 시 orphan adcreative를 남긴다(B-0 리뷰 ①). 프리뷰는
> Meta creative가 미리 있을 필요가 없다(후보 S3 이미지로 충분). 따라서 adcreative 생성을 승인 후로 미뤄
> 고아를 원천 차단하고, generator 의존은 빌드 시점에만 둬 executor의 도메인 경계도 지킨다.

## 4. 데이터 계약 변경 (blast radius 명시)

- **REPLACE_CREATIVE의 `target_object_ids` = 광고(ad) id 목록**(기존: 캠페인 id). 빌드 시점 §3-5에서 해상.
- **`writer.replace_creative` 시그니처 정정 `campaign_id` → `ad_id`.** 동시 갱신 대상(확인됨):
  - `contracts/platform.py:70`(Port) · `adapters/meta/writer.py:123`(impl) · `execution/executor.py:392`(분기)
  - `tests/management/helpers.py:92`(mock) · `tests/management/test_meta_writer.py:65~78` · `tests/management/test_executor_gates.py:384·403`
- **마이그레이션 불요** — 제안은 영속되지 않고 request body로 집행된다(P3 §4-C). 하위호환 대상 없음.
- **`create_ad_creative`는 신규 Writer 메서드**(Port + impl + mock 추가).

## 5. 제안 엔드포인트

- `POST /campaigns/{id}/replace-creative-proposal` — `budget_proposal`(`management.py:2699`) 미러. proposal만 빌드해 반환(즉시 집행 안 함). 집행은 기존 `/approve`+`/execute` 재사용(미수정).
- Tier = TIER_3(기존 정책 불변). 사람이 프리뷰에서 승인.

## 6. 리뷰 반영 결정 (B-0 라운드)

- **① 고아 자산** — §3 집행 시점 생성으로 원천 차단. LIVE 정리정책: 부분 실패로 creative_id가 생긴 뒤 일부 광고만 교체된 경우, **생성된 creative_id를 결과 스냅샷·`audit_events`에 tag**한다. 삭제 가능하면 삭제, 아니면 **orphan 허용 + tag 추적**(LIVE 시 확정 — B-1은 mock이라 미발생).
- **② 계약 변경** — §4에 blast radius·무마이그레이션 명시.
- **③ 소유권/토큰 결속** — 빌드 시점에 `generation`의 org/tenant 소유를 서버 검증(프론트 candidate_id 불신). `GeneratorReadClient`는 내부 토큰(`X-Internal-Token`) 지원(B-0 Q0.3). **주의:** 기존 `from_candidate`도 동일 소유권 검증이 빠져 있다(`management.py:1906`은 org 스코프 없이 get_candidate) — 공용 검증 헬퍼로 묶으면 함께 보강(별도 합의).
- **④ no-op** — 집행 시점 생성이라 creative_id는 항상 새값 → id 비교 no-op 무의미. **v1은 하드 no-op 게이트 없음.** LIVE 기준만 문서화: no-op = 후보 콘텐츠(이미지 s3_key + 카피)가 현재 광고 creative와 동일.
- **⑤ 프리뷰 정보** — `reader.get_creatives(campaign_id)`(`reader.py:465`)가 광고별 `ad_id·ad_name·image_url·thumbnail_url·headline·primary_text`(`CreativePreview`)를 반환(확인됨). 프리뷰 = 광고별 현재 썸네일/이름 + 새 후보 이미지.
- **⑥ 이미지 규격 검증** — 변환 단계(빌드 시점 §3-3)에서 검증. 실패·규격 불가 → proposal 생성 실패, 집행 없음.
- **⑦ LIVE 차단 기준** — 코드 게이트는 **`execution_mode`**(`writer._SENDING_MODES=(VALIDATE_ONLY, LIVE)` + `management_execution_mode` + `use_mock`), 앱 모드가 아니다(앱 개발모드는 LIVE를 코드가 허용해도 Meta가 거부하는 외부 사유). B-1은 mock(`use_mock` 또는 execution_mode≠live)에서 돈다. `create_ad_creative`는 `_is_sending_mode()`일 때만 Meta 호출, 아니면 합성 creative_id 반환.

## 7. 건드리는 파일

- `adapters/meta/writer.py` — `create_ad_creative` 신규, `replace_creative` 시그니처 정정.
- 변환 유틸 — PNG→JPEG(`png_to_jpeg`는 generator 소유 → `tools/`로 이동 또는 management 인라인) + 이미지 규격 검증.
- `api/routers/management.py` — `replace-creative-proposal` 엔드포인트(소유권 검증·핸드오프·규격검증·업로드·광고 해상·proposal 빌드 오케스트레이션).
- `execution/executor.py` — REPLACE_CREATIVE 분기: 집행 시점 `create_ad_creative` → fan-out replace. creative_id는 evidence_metrics의 image_hash·copy로부터 생성, target은 광고 id.
- `contracts/platform.py` — Port 시그니처(`replace_creative`, `create_ad_creative`).
- 프론트 — P3 P1 포팅 카드(`ProposalActions`)에 후보 picker + 선택 소재·영향 광고 프리뷰 섹션.
- 테스트 — `helpers.py`(mock writer) + `test_meta_writer.py`·`test_executor_gates.py` 갱신, 신규 라우터/흐름 테스트.

## 8. 테스트 (mock)

- 후보 핸드오프 + 소유권 검증(타 org 후보 거부).
- 이미지 규격 검증 실패 → proposal 생성 실패(집행 없음).
- 빌드된 proposal에 image_hash·copy·광고 target 적재, Tier-3.
- 집행: executor가 create_ad_creative(합성 id) → 각 광고 fan-out replace, 멱등.
- 승인 게이트: 미승인 Tier-3 거부(기존 게이트 #4 회귀).
- LIVE 호출 없음.

## 9. Non-goals

- 경로 ① 자동선택 + 역링크(= B-2 후속).
- LIVE adcreative 생성·검증(Meta 앱 Live 모드 전환 후).
- 신규 generation 무거운 비동기 풀체인(이미 존재하는 후보 우선).
- 기존 `from_candidate` 소유권 갭의 단독 리팩토링(공용 헬퍼로 묶이면 함께, 아니면 별도).
