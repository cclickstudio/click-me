# B-0 Spike Findings — REPLACE_CREATIVE 소재 변환·등록 + ad 레벨 교체

> spec: `docs/superpowers/specs/2026-06-29-replace-creative-conversion-spike-design.md`
> 작성 누적 — 각 Q는 **확정(근거)** 또는 **추정(문서 근거 + B-1 재확인)** 으로 닫는다.

## 상태표

| Q | 주제 | 상태 | 근거 |
|---|---|---|---|
| Q0.1 | 변환 단계 사슬 | 🟡 추정 | writer.py:330,49,304; client.py:153; generator_service.py:433 |
| Q0.2 | 변환 책임 위치 | ✅ 확정 | CLAUDE.md 협업규칙; writer.py:330,49; instagram.py:1 |
| Q0.3 | 크로스도메인 핸드오프 | ⬜ | |
| Q0.4 | /adcreatives POST·validate_only | ⬜ | |
| Q0b.1 | ad fan-out 방식 | ✅ 확정 | writer.py:478~505 |
| Q0b.2 | ad creative 교체 방식 | ⬜ | |
| Q0b.3 | 영향 ad 조회 | ✅ 확정 | reader.py:465~492; writer.py:498~505 |

## Q0.1 변환 단계

**상태: 🟡 추정** — 단계 1~3은 코드 확정, 단계 4(adcreatives 독립 POST)·PNG 허용 여부는 B-1 라이브 재확인 필요.

### 단계 사슬

| # | 단계 | 있는 부품 | 없는 부품/갭 |
|---|---|---|---|
| 1 | S3 PNG 바이트 획득 | `download_bytes(cand.s3_key)` — management.py:1918 패턴 | — |
| 2 | PNG → JPEG 변환 | `generator_service.py:433 png_to_jpeg` (generator 도메인) | management 내 변환 유틸 없음 — B-1이 tools/ 이동 또는 인라인 구현 필요 |
| 3 | `/adimages` 업로드 → `image_hash` | `writer.upload_image` (writer.py:330~345) + `client.post_image` (client.py:153~164) **있음** | `client.post_image`가 content-type을 `"image/jpeg"`로 하드코딩 — PNG 바이트를 그대로 보내면 MIME 불일치. 변환 선행 필수(Q0.4 추정 근거) |
| 4 | `object_story_spec` 빌드 | `_build_link_creative(config, page_id, image_hash)` (writer.py:49~59) **있음** | — |
| 5 | `/act_{id}/adcreatives` POST → `creative_id` | **없음** | `create_link_ad`(writer.py:304~328)는 creative를 ad에 **인라인**으로 박을 뿐, standalone adcreatives POST 메서드 없음 — B-1이 만들 부품 |
| 6 | ad의 creative 교체 | `writer.replace_creative(campaign_id, creative_id, idem_key)` (writer.py:123~137) **있음** | 현재 executor(executor.py:388)가 `evidence_metrics["selected_candidate_id"]`(generator DB UUID)를 그대로 전달 → Meta creative_id가 아니라 LIVE 꼬리가 끊김. 단계 5 완료 후에야 유효 creative_id 전달 가능 |

### 핵심 갭 요약

1. **단계 5 없음** — `/act_{id}/adcreatives` POST를 독립 메서드로 만들어야 creative_id를 얻을 수 있다.
2. **PNG→JPEG 변환** — `client.post_image`는 JPEG content-type 하드코딩(client.py:162). 업로드 전 변환 필요. 변환 함수 `png_to_jpeg`(generator_service.py:433)는 generator 도메인 소유 → B-1이 `tools/`로 이동하거나 관리 도메인에 인라인 구현.
3. **executor 수정** — `REPLACE_CREATIVE` 분기(executor.py:388)가 UUID → Meta creative_id로 대체되도록 증거 메트릭 구조 변경 필요.

> 추정 근거: Meta Graph API 문서상 `/adimages`는 JPEG/PNG 모두 허용하나, 코드가 JPEG만 전송하므로 PNG-as-JPEG 동작이 통과하는지 Q0.4 라이브 probe로 재확인.

## Q0.2 변환 책임 위치

**상태: ✅ 확정** — **management writer 소유** 추천 잠금.

### 후보 비교

| 후보 | 근거 | 판정 |
|---|---|---|
| **management writer 소유** | `upload_image`(writer.py:330)·`_build_link_creative`(writer.py:49) 이미 보유. 모든 Meta Ads 쓰기가 writer 단일 경로(§4 불변, management CLAUDE.md §Invariants 1). adcreative는 Ads 자산이라 결이 같음. executor→writer 단일 경로가 이미 확립되어 있어 새 메서드를 여기에 추가하는 것이 자연스러움. | **채택** |
| **generator 소유** | generator는 **Instagram Content Publishing**(`instagram.py:1` 독스트링 — "Meta Graph API Content Publishing") 전용이고 Meta Ads adcreative를 만들지 않음. generator가 Ads 책임을 떠안으면 도메인 경계 흐림. CLAUDE.md 협업 규칙: "타 도메인 내부 직접 import 금지 → contracts/ 스키마로만 교환". | **기각** |

### 추천 근거 (3가지)

1. **도메인 경계** — CLAUDE.md: "타 도메인 내부 직접 import 금지". generator가 Ads writer를 import하거나 Ads API를 호출하면 경계 위반.
2. **기존 자산 재사용** — `upload_image`(POST /adimages, writer.py:330)·`_build_link_creative`(object_story_spec 빌드, writer.py:49)가 이미 management writer에 있음. 추가할 메서드는 두 부품을 연결하는 `/adcreatives` POST 하나뿐.
3. **executor 단일 경로 §4 불변** — management CLAUDE.md Invariant 1: "All spend goes through executor.py — agents/services must never call a Writer directly". executor가 writer를 호출하는 구조가 이미 확립. 여기에 `create_ad_creative` 메서드를 추가하면 기존 구조 그대로 따름.

## Q0.3 크로스도메인 핸드오프

## Q0.4 /adcreatives POST·validate_only

## Q0b.1 ad fan-out 방식

**상태: ✅ 확정** — `activate_tree`의 `_child_ids` 패턴이 REPLACE_CREATIVE fan-out에 그대로 재사용 가능.

### 확인 내용

`activate_tree`(writer.py:478~496)는 다음 패턴으로 하위 ad에 쓰기를 fan-out한다.

```python
# writer.py:491~495
for prefix, path in (("adset", f"{campaign_id}/adsets"), ("ad", f"{campaign_id}/ads")):
    for i, child_id in enumerate(await self._child_ids(path)):
        result = await self.activate(child_id, f"{idem_key}-{prefix}-{i}")
        if result.status is not ResultStatus.SUCCESS:
            return _tag_campaign(result, campaign_id)
```

`_child_ids(path)`(writer.py:498~505)는 `GET /{path}?fields=id&limit=200` 로 id 목록을 반환한다.

```python
# writer.py:498~505
async def _child_ids(self, path: str) -> list[str]:
    try:
        payload = await self._client.get(path, {"fields": "id", "limit": 200})
    except (httpx.HTTPError, MetaApiError):
        logger.warning("자식 id 조회 실패: %s", path)
        return []
    return [str(row["id"]) for row in payload.get("data", []) if row.get("id")]
```

**결정:** REPLACE_CREATIVE fan-out은 동일 패턴 — `_child_ids(f"{campaign_id}/ads")`로 하위 ad id 목록을 얻고, 각 ad에 `POST /{ad_id} {creative:{creative_id}}`를 보낸다. executor 또는 service 레이어가 `_child_ids` 기반 순회를 담당하고, writer에는 ad 단위 `replace_creative(ad_id, creative_id, idem_key)` 메서드를 추가한다(현재 writer의 `replace_creative`는 campaign_id를 받아 campaign 노드에 직접 POST함 — ad 단위 시그니처로 정정 필요).

**대안(특정 ad만 선택 교체):** v1 범위 밖. 전체 fan-out으로 단순화.

## Q0b.2 ad creative 교체 방식

## Q0b.3 영향 ad 조회

**상태: ✅ 확정** — 두 가지 경로 확인됨.

### 확인 내용

1. **프리뷰용 ad 목록** — `reader.get_creatives(campaign_id)`(reader.py:465~492)가 `GET /{campaign_id}/ads?fields=name,creative{...}&limit=6`로 광고 목록과 크리에이티브를 반환한다. 이미 퍼블릭 메서드로 존재.

2. **id 카운트 전용** — `_child_ids(f"{campaign_id}/ads")`(writer.py:498~505)가 ad id 목록을 반환하므로 `len()` 으로 개수를 얻을 수 있다. 단, `_child_ids`는 private 메서드라 외부에서 직접 호출하려면 노출이 필요하다.

**결정:**
- 프리뷰 "영향받는 광고 목록" → `reader.get_creatives` 재사용(이미 있음).
- 프리뷰 "개수만" → B-1이 `_child_ids` 기반 공개 카운트 메서드를 writer 또는 reader에 추가하거나, `get_creatives` 결과 len()으로 충분하면 별도 추가 불필요.
- reader에 ad 단위 퍼블릭 목록 메서드(`GET /{campaign_id}/ads`) 는 `get_creatives` 외에 없음 — 별도 `list_ads` 메서드는 현재 없음(확인: reader.py 전체에 `list_ads` 없음).

## 결론 — B-1 경로 ① go/no-go

## B-1이 만들 Port/메서드 제안 (추천, 잠금은 B-1)
