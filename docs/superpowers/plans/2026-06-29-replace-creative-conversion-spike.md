# B-0 Spike (REPLACE_CREATIVE 소재 변환·등록) 조사 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **이 plan은 조사 spike다 — 프로덕션 코드 0.** 표준 TDD(실패 테스트→구현→통과)를 따르지 않는다. 각 태스크의 "검증 등가물"은 **답을 구체적 근거(`파일:라인` 또는 Meta 문서 URL)와 함께 findings 문서에 기록 + 결정/추천 잠금**이다. probe는 **던지는 코드**(scratchpad, 커밋 안 함)뿐이고, 커밋되는 산출물은 **findings 문서 하나**다.

**Goal:** "generator 후보(S3 PNG + 카피) → Meta adcreative(creative_id) → 캠페인 하위 ad의 creative 교체" 사슬이 LIVE에서 성립하는지·어떻게 성립하는지 확정하고, B-1 경로 ① go/no-go를 판정한다.

**Architecture:** 하이브리드 조사 — Q0.1~0.3·Q0b.1·0b.3은 Meta 문서 + 기존 `writer.py`/`reader.py`/`client.py` 코드로 정적 추론, Q0.4·Q0b.2만 `validate_only` 라이브 probe로 확정(자격증명 없으면 "추정 — B-1 재확인" 표기). 모든 답은 findings 문서에 근거와 함께 적재.

**Tech Stack:** Python(uv) · Meta Graph API v23 · 기존 `MetaClient`(`adapters/meta/client.py`) · httpx.

**참조 spec:** `docs/superpowers/specs/2026-06-29-replace-creative-conversion-spike-design.md`
**상위 plan:** `docs/superpowers/plans/2026-06-29-p3-chat-campaign-creative-targeting-bid.md`(P3 B-0)

---

## 파일 구조 (무엇을 만들고 만지나)

- **Create (커밋됨, 유일 산출물):** `docs/management/2026-06-29-replace-creative-conversion-spike-findings.md` — 결정 문서. 모든 태스크가 여기에 누적 기록.
- **Read-only (조사 대상, 수정 금지):**
  - `backend/domain/management/adapters/meta/writer.py` (`upload_image`·`_build_link_creative`·`replace_creative`·`activate_tree`·`_child_ids`)
  - `backend/domain/management/adapters/meta/client.py` (`post`·`post_image`·`get`)
  - `backend/domain/management/adapters/meta/reader.py` (`list_campaigns`·`get_campaign_targeting`)
  - `backend/domain/management/contracts/platform.py` (`AdPlatformReader`·`AdPlatformWriter` Port)
  - `backend/domain/generator/service/generator_service.py` (`select_candidate`·후보 `s3_key`·`png_to_jpeg`)
  - `backend/domain/generator/contracts/schemas.py` (후보·입력 스키마)
- **Create (던질 probe, 커밋 안 함):** `<scratchpad>/probe_adcreatives.py` · `<scratchpad>/probe_ad_creative_update.py`
  - scratchpad = `C:/Users/804-0/AppData/Local/Temp/claude/C--Users-804-0-click-me/9ff19f9f-9e56-4e77-8f75-7ea2a9573f7b/scratchpad`

---

## Task 0: findings 문서 골격 생성

**Files:**
- Create: `docs/management/2026-06-29-replace-creative-conversion-spike-findings.md`

- [ ] **Step 1: findings 골격 작성**

아래 내용 그대로 파일 생성(상태표 + Q별 빈 섹션).

```markdown
# B-0 Spike Findings — REPLACE_CREATIVE 소재 변환·등록 + ad 레벨 교체

> spec: `docs/superpowers/specs/2026-06-29-replace-creative-conversion-spike-design.md`
> 작성 누적 — 각 Q는 **확정(근거)** 또는 **추정(문서 근거 + B-1 재확인)** 으로 닫는다.

## 상태표

| Q | 주제 | 상태 | 근거 |
|---|---|---|---|
| Q0.1 | 변환 단계 사슬 | ⬜ | |
| Q0.2 | 변환 책임 위치 | ⬜ | |
| Q0.3 | 크로스도메인 핸드오프 | ⬜ | |
| Q0.4 | /adcreatives POST·validate_only | ⬜ | |
| Q0b.1 | ad fan-out 방식 | ⬜ | |
| Q0b.2 | ad creative 교체 방식 | ⬜ | |
| Q0b.3 | 영향 ad 조회 | ⬜ | |

## Q0.1 변환 단계

## Q0.2 변환 책임 위치

## Q0.3 크로스도메인 핸드오프

## Q0.4 /adcreatives POST·validate_only

## Q0b.1 ad fan-out 방식

## Q0b.2 ad creative 교체 방식

## Q0b.3 영향 ad 조회

## 결론 — B-1 경로 ① go/no-go

## B-1이 만들 Port/메서드 제안 (추천, 잠금은 B-1)
```

- [ ] **Step 2: 커밋**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 spike findings 골격"
```

---

## Task 1: Q0.1 변환 단계 사슬 (정적)

**Files:**
- Read: `backend/domain/management/adapters/meta/writer.py` (`upload_image` 330-345 · `_build_link_creative` 49-59 · `create_link_ad` 304-328)
- Read: `backend/domain/management/adapters/meta/client.py` (`post_image` 154 근처 · `post`)
- Read: `backend/domain/generator/service/generator_service.py` (`png_to_jpeg` 433 · 후보 `s3_key`)
- Modify: findings `## Q0.1`

- [ ] **Step 1: 부품 사슬 확인**

다음을 코드로 확인해 findings에 적는다 — 각 단계가 "있음/없음"과 위치.
1. 후보 이미지 형식: generator 후보는 **PNG**(`candidate_gen.py` upload `content_type="image/png"`). Meta `/adimages`는 PNG 허용 여부 확인(문서). 불가 시 `png_to_jpeg`(`generator_service.py:433`) 재사용 가능.
2. `/adimages` 업로드 → `image_hash`: `writer.upload_image`(330) + `client.post_image`(154) **있음**.
3. object_story_spec 빌드: `_build_link_creative`(49) **있음**(link_data: message/name/link/CTA/image_hash).
4. **`/act_{id}/adcreatives` POST → creative_id: writer에 독립 메서드 없음(=B-1이 만들 부품).** `create_link_ad`는 creative를 ad에 인라인으로만 박음(304).

- [ ] **Step 2: Q0.1 사슬 확정 기록**

findings `## Q0.1`에 단계 사슬을 표로 적고(단계·있는 부품·없는 부품), 상태표 Q0.1을 **확정** 또는 (PNG 허용이 문서로만 확인되면) **추정**으로. 근거에 `writer.py:330`·`_build_link_creative` 등 라인 명기.

- [ ] **Step 3: 커밋**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 Q0.1 변환 단계 사슬 확정"
```

---

## Task 2: Q0b.1·Q0b.3 ad fan-out + 영향 ad 조회 (정적)

**Files:**
- Read: `backend/domain/management/adapters/meta/writer.py` (`activate_tree` 478-496 · `_child_ids` 498-505)
- Read: `backend/domain/management/adapters/meta/reader.py` (`list_campaigns` 634 · `get_campaign_targeting` 784)
- Modify: findings `## Q0b.1`·`## Q0b.3`

- [ ] **Step 1: fan-out 패턴 확인**

`activate_tree`가 `_child_ids(f"{campaign_id}/ads")`로 하위 ad id를 펼쳐 순회함을 확인(478-505). REPLACE도 같은 패턴(campaign → 하위 ad 펼쳐 각 ad.creative 갱신)이 타당한지 findings에 결정 + 대안(특정 ad만 선택)은 v1 범위 밖임을 명기.

- [ ] **Step 2: 영향 ad 조회 경로 확인**

프리뷰 "영향받는 광고 목록/개수"를 얻는 호출 확정 — `_child_ids`(id만) vs reader에 ad 리스트 메서드가 있는지. 현재 reader엔 ad 단위 공개 메서드가 없음을 확인하고(있으면 라인 명기), 없으면 "B-1이 `_child_ids` 기반 카운트 노출 필요"로 기록.

- [ ] **Step 3: Q0b.1·0b.3 기록 + 상태표 갱신**

findings에 결정·근거(`writer.py:498` 등) 적고 상태표 갱신.

- [ ] **Step 4: 커밋**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 Q0b.1·0b.3 ad fan-out·영향 ad 조회 확정"
```

---

## Task 3: Q0.2 변환 책임 위치 (정적·결정)

**Files:**
- Read: `CLAUDE.md`(협업 규칙·도메인 경계) · `backend/domain/management/CLAUDE.md`(파일 소유권)
- Read: `backend/domain/management/adapters/meta/writer.py`(보유 부품) · `backend/domain/generator/adapters/instagram.py`(generator 게시 자산)
- Modify: findings `## Q0.2`

- [ ] **Step 1: 후보지 비교**

두 후보를 적고 근거로 판정한다.
- **management writer 소유** — 이미 `upload_image`·`_build_link_creative` 보유, 모든 Meta Ads 쓰기가 writer 단일 경로(§4 불변). adcreative도 Ads 자산이라 결이 같음.
- **generator 소유** — generator는 IG Content Publishing 전용이고 Meta Ads adcreative를 안 만듦. Ads로 끌어오면 generator가 Ads 책임을 떠안아 경계 흐려짐.

- [ ] **Step 2: 추천 잠금**

findings `## Q0.2`에 **추천안(기본: management writer 소유)** 과 근거(도메인 경계 + 기존 자산 재사용 + executor 단일 경로 §4) 기록. 상태표 **확정**.

- [ ] **Step 3: 커밋**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 Q0.2 변환 책임 위치 추천 잠금"
```

---

## Task 4: Q0.3 크로스도메인 핸드오프 (정적·결정)

**Files:**
- Read: `CLAUDE.md`("타 도메인 내부 직접 import 금지 → contracts 스키마로만 교환")
- Read: `backend/domain/generator/service/generator_service.py`(`select_candidate` 388 · 후보 `s3_key`·`image_url` 노출 280-282)
- Read: `backend/api/routers/management.py`(generator-소스 제안 패턴 1903·2073 — 기존 핸드오프 본보기)
- Modify: findings `## Q0.3`

- [ ] **Step 1: 핸드오프 옵션 비교**

management가 후보 **S3 키 + 카피**를 받는 3안을 적고 근거 판정.
- **(a) HTTP contract** — generator 라우터에서 후보 메타(S3 키·카피) 조회. 기존 generator-소스 제안(`management.py:1903`)이 이미 쓰는 결.
- **(b) S3 키 직접 전달** — 챗/카드가 canonical 후보 id→S3 키를 실어 보냄. management가 S3에서 직접 download(공용 storage tool).
- **(c) contracts 스키마** — 공유 스키마로 교환.

- [ ] **Step 2: 추천 잠금**

findings에 **추천안 + 근거**(기존 `management.py:1903`/`2073` 패턴 일치 여부, 도메인 경계 준수, §보안 토큰 결속(Open 4)와의 정합) 기록. 상태표 **확정**.

- [ ] **Step 3: 커밋**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 Q0.3 크로스도메인 핸드오프 추천 잠금"
```

---

## Task 5: Q0.4·Q0b.2 라이브 게이트 (validate_only probe 또는 추정)

**Files:**
- Create(커밋 안 함): `<scratchpad>/probe_adcreatives.py` · `<scratchpad>/probe_ad_creative_update.py`
- Read: `backend/domain/management/adapters/meta/client.py`(`post(path, data, validate_only=)`)
- Modify: findings `## Q0.4`·`## Q0b.2`

- [ ] **Step 1: 자격증명·문서 선확인**

`backend/.env`에 `META_ACCESS_TOKEN`·`META_AD_ACCOUNT_ID`(또는 settings 대응 키)와 `ads_management` 권한이 있는지 확인. **없으면 Step 2~3 건너뛰고 Step 4(추정 표기)로.** 먼저 Meta 문서로 `/adcreatives`·ad 업데이트의 `validate_only`(`execution_options`) 지원 여부를 정적 확인해 findings 초안에 적는다.

- [ ] **Step 2: probe 스크립트 작성 (자격증명 있을 때만)**

`<scratchpad>/probe_adcreatives.py` — adcreative 생성을 **validate_only로** 시도하고, 혹시 실객체가 생기면 즉시 삭제(안전).

```python
# Meta /adcreatives가 validate_only로 우리 object_story_spec을 받는지 확인하는 일회용 probe.
import asyncio, json, os
import httpx

TOKEN = os.environ["META_ACCESS_TOKEN"]
ACCOUNT = os.environ["META_AD_ACCOUNT_ID"]  # act_XXXX
PAGE_ID = os.environ["META_PAGE_ID"]
BASE = "https://graph.facebook.com/v23.0"

creative = {
    "object_story_spec": {
        "page_id": PAGE_ID,
        "link_data": {
            "message": "probe",
            "name": "probe headline",
            "link": "https://clickme.co.kr",
            "call_to_action": {"type": "LEARN_MORE"},
        },
    }
}

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        # 1) validate_only 시도
        r = await c.post(
            f"{BASE}/{ACCOUNT}/adcreatives",
            data={
                "name": "probe-creative",
                "object_story_spec": json.dumps(creative["object_story_spec"]),
                "execution_options": json.dumps(["validate_only"]),
                "access_token": TOKEN,
            },
        )
        print("validate_only status:", r.status_code)
        print(r.text)
        body = r.json()
        # 2) 혹시 실 id가 반환되면(=validate_only 미지원) 즉시 삭제
        cid = body.get("id")
        if cid:
            d = await c.delete(f"{BASE}/{cid}", params={"access_token": TOKEN})
            print("cleanup deleted:", cid, d.status_code)

asyncio.run(main())
```

`<scratchpad>/probe_ad_creative_update.py` — 기존 ad의 creative를 다른 creative_id로 교체할 수 있는지 validate_only로 확인.

```python
# 기존 ad의 creative 교체가 POST /{ad_id}{creative:{creative_id}}로 되는지 validate_only 확인.
import asyncio, json, os
import httpx

TOKEN = os.environ["META_ACCESS_TOKEN"]
AD_ID = os.environ["PROBE_AD_ID"]            # 교체 대상(테스트용 PAUSED ad)
CREATIVE_ID = os.environ["PROBE_CREATIVE_ID"]  # 갈아끼울 기존 creative id
BASE = "https://graph.facebook.com/v23.0"

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{BASE}/{AD_ID}",
            data={
                "creative": json.dumps({"creative_id": CREATIVE_ID}),
                "execution_options": json.dumps(["validate_only"]),
                "access_token": TOKEN,
            },
        )
        print("ad update status:", r.status_code)
        print(r.text)

asyncio.run(main())
```

- [ ] **Step 3: probe 실행·결과 기록 (자격증명 있을 때만)**

Run: `cd backend && uv run python <scratchpad>/probe_adcreatives.py` / `... probe_ad_creative_update.py`
관찰: HTTP 상태·에러코드·`validate_only` 존중 여부·필요 권한. **실객체가 생겼다면 cleanup 로그 확인.** 결과를 findings에 그대로 인용(토큰·기밀 제외).

- [ ] **Step 4: Q0.4·Q0b.2 기록**

findings `## Q0.4`·`## Q0b.2`에 결과를 적는다 — probe 돌렸으면 **확정(응답 인용)**, 못 돌렸으면 **추정(Meta 문서 URL 근거 + "B-1 구현 시 validate_only 재확인")**. 상태표 갱신.

- [ ] **Step 5: 커밋 (findings만 — probe는 커밋 안 함)**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 Q0.4·Q0b.2 라이브 게이트 결과"
```

---

## Task 6: 결론 — go/no-go + Port 제안

**Files:**
- Modify: findings `## 결론` · `## B-1이 만들 Port/메서드 제안` · 상태표

- [ ] **Step 1: 상태표 마감 확인**

7개 Q가 전부 ✅(확정) 또는 🟡(추정+재확인) 인지 확인. ⬜가 남으면 해당 Task로 돌아간다.

- [ ] **Step 2: go/no-go 판정 기록**

findings `## 결론`에 B-1 경로 ① 착수 가능 여부를 적는다 — 막는 게 있으면 무엇이 선결인지(예: validate_only 미지원 시 실객체 생성·삭제 전략 필요). 역링크(Open 1)는 범위 밖이나 "별도 선결"로 한 줄 링크.

- [ ] **Step 3: B-1 Port/메서드 제안 기록 (추천, 잠금은 B-1)**

`## B-1이 만들 Port/메서드 제안`에 시그니처 후보를 *제안*으로 적는다(계약 잠금은 B-1). 예:

```python
# AdPlatformWriter 추가 후보 (B-1에서 확정)
async def create_ad_creative(self, config, *, image_hash: str | None, idem_key: str) -> str: ...
#   object_story_spec 빌드 → /act_{id}/adcreatives POST → creative_id 반환
async def replace_creative(self, ad_id: str, creative_id: str, idem_key: str) -> ActionResult: ...
#   campaign_id → ad_id 단위로 시그니처 정정(fan-out은 executor/서비스가 _child_ids로)
```

- [ ] **Step 4: 커밋**

```bash
git add docs/management/2026-06-29-replace-creative-conversion-spike-findings.md
git commit -m "add: B-0 결론 go/no-go + B-1 Port 제안"
```

---

## Self-Review 메모 (작성자 확인 완료)

- **Spec 커버리지:** spec §3의 7개 Q ↔ Task 1(Q0.1)·Task 2(Q0b.1·0b.3)·Task 3(Q0.2)·Task 4(Q0.3)·Task 5(Q0.4·Q0b.2)·Task 6(종료). spec §5 종료기준 4항 ↔ Task 6 Step 1~3. 누락 없음.
- **No-placeholder:** probe 코드·findings 골격·Port 제안 모두 실제 내용 기재. "적절히 처리" 류 없음.
- **타입 일관:** findings 섹션 헤더(Q0.1…)·상태표 키가 전 태스크에서 동일. probe 환경변수명(`META_ACCESS_TOKEN`·`META_AD_ACCOUNT_ID`·`META_PAGE_ID`) 일관.
- **경계 준수:** 모든 read-only 대상은 수정 금지, 유일 커밋 산출물은 findings, probe는 scratchpad·비커밋.
