# B-0 Spike Findings — REPLACE_CREATIVE 소재 변환·등록 + ad 레벨 교체

> spec: `docs/superpowers/specs/2026-06-29-replace-creative-conversion-spike-design.md`
> 작성 누적 — 각 Q는 **확정(근거)** 또는 **추정(문서 근거 + B-1 재확인)** 으로 닫는다.

## 상태표

| Q | 주제 | 상태 | 근거 |
|---|---|---|---|
| Q0.1 | 변환 단계 사슬 | 🟡 추정 | writer.py:330,49,304; client.py:153; generator_service.py:433 |
| Q0.2 | 변환 책임 위치 | ✅ 확정 | CLAUDE.md 협업규칙; writer.py:330,49; instagram.py:1 |
| Q0.3 | 크로스도메인 핸드오프 | ✅ 확정 | management.py:1897~2004; adapters/generator/client.py:46~101 |
| Q0.4 | /adcreatives POST·validate_only | 🟡 부분 | 라이브 probe: 앱 **개발 모드**라 거부(code100/subcode1885183) — Live 전환 선결 |
| Q0b.1 | ad fan-out 방식 | ✅ 확정 | writer.py:478~505 |
| Q0b.2 | ad creative 교체 방식 | ✅ 확정 | 라이브 probe: `POST /{ad_id}{creative:{creative_id}}`+validate_only → `success:true` |
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

**상태: ✅ 확정** — **(a) HTTP contract** 추천 잠금. 기존 `from_candidate` 패턴과 동일.

### 3안 비교

| 옵션 | 설명 | 판정 |
|---|---|---|
| **(a) HTTP contract** | management가 `GeneratorReadClient`(adapters/generator/client.py:46~101)로 generator의 `GET /api/generator/generations/{id}` 를 호출해 `HandoffCandidate.s3_key + copy`를 얻음 | **채택** |
| **(b) S3 키 직접 전달** | 챗/카드가 `candidate_id`와 함께 `s3_key`를 페이로드에 실어 보냄. management가 S3에서 직접 download. | 보류 — 챗 payload 구조 변경 필요. 현재 REPLACE_CREATIVE 제안의 `evidence_metrics["selected_candidate_id"]`(executor.py:388)가 이미 있어, 여기에 s3_key를 추가 적재하면 가능. 그러나 챗 에이전트가 S3 키를 알아야 하는 결합이 생김. |
| **(c) contracts 스키마** | 공유 `contracts/` 스키마로 직접 교환 | 기각 — `contracts/` 변경은 양측 합의 + 별도 PR 필요(management CLAUDE.md §Shared). 가장 무거운 경로. |

### 기존 선례 — `from_candidate` (management.py:1897~2004)

`management.py:1897`의 `from_candidate` 엔드포인트가 이미 (a) 패턴을 확립함:

```python
# management.py:1904~1907
client = build_generator_client(settings)
cand = await client.get_candidate(body.generation_id, body.candidate_id)
# → HandoffCandidate(s3_key=..., copy=HandoffCopy(headline=..., body=..., cta=...))
image_bytes = await download_bytes(cand.s3_key)  # management.py:1918
```

`GeneratorReadClient`(adapters/generator/client.py)는 management 소유 어댑터로, generator 내부 타입을 import하지 않고 HTTP+스키마 검증으로만 `HandoffCandidate`를 파싱한다. 계약 버전(`schema_version`, client.py:63)도 검증한다.

### REPLACE_CREATIVE에 적용

REPLACE_CREATIVE 요청이 `generation_id + candidate_id`를 `evidence_metrics`에 담으면, executor → writer 호출 전에 동일 `GeneratorReadClient.get_candidate()`로 `s3_key + copy`를 얻을 수 있다. `from_simulation`(management.py:2073)은 raw SQL 패턴(임시)을 쓰지만 코멘트에 "추후 시뮬 read 계약으로 교체"가 명시돼 있어, generator 방향은 이미 (a)로 정착된 것으로 볼 수 있다.

### 보안 정합

`GeneratorReadClient`는 내부 토큰(`X-Internal-Token`) 헤더를 지원한다(client.py:59). Open 4(보안 토큰 결속)와 충돌 없이 정합.

## Q0.4 /adcreatives POST·validate_only

**상태: 🟡 부분** — payload는 형태 거부 안 됨(앱모드 게이트까지 도달). 그러나 **앱이 개발(Development) 모드라 adcreative 생성 자체가 차단**됨 → **새 환경 블로커**. validate_only 존중 여부는 이 게이트에 먼저 막혀 미확인.

### 라이브 probe 결과 (validate_only, scratchpad·비커밋)

- **토큰 권한 (GET /me/permissions, 200):** `ads_management`·`ads_read`·`pages_manage_ads`·`business_management` 등 광고 쓰기 권한 **전부 보유**. 권한 부족은 아님.
- **`POST /act_882448327559337/adcreatives` (execution_options=['validate_only'], 400):**
  - `code=100, error_subcode=1885183`
  - `error_user_title`: "광고 크리에이티브 게시물이 개발 모드인 앱에서 만들어졌습니다"
  - `error_user_msg`: "…이 광고를 만들려면 공개(Live) 모드여야 합니다"
  - → 객체 미생성(id 미반환, cleanup 불요).

### 해석

1. **payload 형태는 유효 추정** — `object_story_spec`(`_build_link_creative` 형태)이 malformed로 거부되지 않고 **앱-모드 검사 단계까지 도달**했다. 즉 페이로드 구조 문제는 아님.
2. **환경 블로커(코드 아님):** adcreative 생성은 **Meta 앱을 Live/공개 모드로 전환**해야 가능하다(개발 모드 차단). B-1의 코드 작업과 무관한 **운영/앱설정 선결조건**이다.
3. **validate_only 미확인:** 앱-모드 게이트에 먼저 막혀 `/adcreatives`가 validate_only를 존중하는지 확인 못함 — 앱 Live 전환 후 재확인 항목.
4. **Q0.1 PNG→JPEG도 미확인:** `/adimages` 업로드는 별도 probe 안 함(adcreatives가 앞서 막힘). PNG-as-JPEG 통과 여부는 여전히 추정.

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

**상태: ✅ 확정** — 기존 ad의 creative 교체는 `POST /{ad_id} {creative:{creative_id}}` 가 맞다. "새 ad 생성/비활성" 대안 불필요.

### 라이브 probe 결과 (validate_only, 실변경 0)

- **대상:** 계정 내 기존 ad `120250726096510729`(status=ACTIVE), 현재 creative `1594694062659930`.
- **요청:** `POST /{ad_id}` `data={creative: {"creative_id": 1594694062659930}, execution_options:['validate_only']}` — **자기 creative_id를 그대로** 써서 validate_only(실변경 0).
- **응답 (200):** `{"success": true}`.

### 해석

1. **메커니즘 확정:** ad의 creative는 `POST /{ad_id}`에 `creative={creative_id}`로 **교체 가능**(요청 형태·권한 validate_only로 통과). 별도 새 ad 생성 패턴 불필요.
2. **fan-out 결속:** Q0b.1의 `_child_ids(f"{campaign_id}/ads")`로 얻은 각 ad_id에 이 호출을 보내면 캠페인 단위 교체가 성립.
3. **단, 갈아끼울 `creative_id`는 Q0.4(adcreative 생성)가 풀려야 실값이 생긴다** — Q0b.2는 "교체 메커니즘"을 확정했을 뿐, 새 creative 발급은 Q0.4(앱 Live 모드) 선결.

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

**판정: 코드 GO (조건부) — 단, LIVE 종단 검증은 앱 Live 모드 전환 후.**

### 확정된 것 (코드 사슬 전부 규명)

- **변환 책임 = management writer**(Q0.2 확정). 부품 `upload_image`·`_build_link_creative` 이미 보유, 추가할 건 `/adcreatives` POST 하나.
- **핸드오프 = HTTP contract**(Q0.3 확정). 기존 `GeneratorReadClient`/`from_candidate` 패턴 그대로 — 신규 데이터모델 불요.
- **ad fan-out = `_child_ids`**(Q0b.1 확정), **영향 ad 조회 = `get_creatives`**(Q0b.3 확정).
- **ad creative 교체 메커니즘 = `POST /{ad_id}{creative:{creative_id}}` (Q0b.2 라이브 확정).** 별도 ad 재생성 불요.

### 새로 드러난 블로커 (정적 분석으로는 못 잡았음)

- **[환경 블로커] Meta 앱이 개발(Development) 모드 → `/adcreatives` 생성 차단**(Q0.4, subcode 1885183). B-1 코드와 무관한 **운영/앱설정 선결** — 앱을 Live/공개 모드로 전환(필요 시 앱 심사)해야 새 creative 발급이 LIVE에서 동작한다.
  - 그 전까지 B-1은 **mock/validate로 ad-replace 단계까지 빌드·테스트 가능**하나, create-adcreative 단계의 LIVE 검증은 불가.
  - `/adcreatives`의 validate_only 존중 여부도 앱 Live 전환 후 재확인.

### 남은 선결 (범위 밖, 별도)

- **Open 1 — generation↔campaign 역링크**: 경로 ①(연결된 시안 자동 선택)의 데이터 선결. 본 spike 범위 밖(별도 처리). 없으면 경로 ① 보류하고 ②③(명시적 후보/업로드)부터 가능.

### 한 줄 요약

코드 사슬은 전부 규명·ad교체는 라이브 확정 → **B-1 착수 가능**. 단 **LIVE 풀체인은 (1) 앱 Live 모드 전환 (2) 역링크(경로 ① 한정)** 두 선결에 막힌다.

## B-1이 만들 Port/메서드 제안 (추천, 잠금은 B-1)

```python
# AdPlatformWriter 추가/정정 후보 (시그니처 잠금은 B-1)

async def create_ad_creative(
    self, config: CampaignConfig, *, image_hash: str | None, idem_key: str
) -> str:
    """object_story_spec 빌드(_build_link_creative 재사용) → POST /act_{id}/adcreatives → creative_id 반환.
    ⚠ 앱 Live 모드 전제(Q0.4). 개발 모드면 code100/subcode1885183."""

async def replace_creative(self, ad_id: str, creative_id: str, idem_key: str) -> ActionResult:
    """현재 시그니처(campaign_id) → ad_id 단위로 정정. POST /{ad_id}{creative:{creative_id}} (Q0b.2 확정).
    캠페인 단위 fan-out은 executor/service가 _child_ids(f'{campaign_id}/ads')로 순회(Q0b.1)."""
```

부수 작업(코드):
- **PNG→JPEG**: `png_to_jpeg`(generator_service.py:433, generator 소유)를 `tools/`로 이동 또는 management 인라인 — `client.post_image`가 JPEG 하드코딩(client.py:162)이라 업로드 전 변환 필수.
- **executor REPLACE_CREATIVE 분기(executor.py:388)**: `selected_candidate_id`(UUID) → `GeneratorReadClient.get_candidate()`로 s3_key+copy 해석 → upload_image → create_ad_creative → 얻은 creative_id로 fan-out replace.
- **영향 ad 개수**: 프리뷰용으로 `get_creatives` 결과 len() 재사용(별도 메서드 불요).

운영 선결(코드 아님): **Meta 앱 Live 모드 전환**(+필요 시 앱 심사) — Q0.4 블로커 해제 전제.
