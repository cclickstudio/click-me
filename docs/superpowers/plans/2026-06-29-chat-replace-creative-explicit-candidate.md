# B-1 — 챗 명시적 후보 소재 교체 (REPLACE_CREATIVE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 캠페인의 소재를 사용자가 고른 generator 후보로 교체하는 REPLACE_CREATIVE를, 승인 후 집행 시점에 adcreative를 만들어 캠페인 하위 광고에 fan-out 적용하는 백엔드를 mock으로 완성한다.

**Architecture:** 빌드 시점(라우터)은 캠페인 소유권 검증·후보 핸드오프·이미지 규격검증·이미지 업로드·proposal 빌드까지만 하고 adcreative는 만들지 않는다. 집행 시점(executor→writer `replace_creative_tree`)에 adcreative를 1회 생성하고 `_child_ids`로 하위 광고에 fan-out 교체한다(`activate_tree` 패턴). 변환을 승인 후로 미뤄 고아 adcreative를 원천 차단한다.

**Tech Stack:** Python(uv) · FastAPI · Pillow(PNG→JPEG) · Meta Graph API v23(mock에선 미호출) · pytest.

**참조:** spec `docs/superpowers/specs/2026-06-29-chat-replace-creative-explicit-candidate-design.md` · spike findings `docs/management/2026-06-29-replace-creative-conversion-spike-findings.md`.

**범위 메모:**
- 후보-org 누출은 **Task 0에서 닫는다**(generator GET을 `X-Org-Id`로 org 스코프 — 타 org 후보 404). 캠페인 소유권은 Task 5에서 강제.
- 프론트 챗 카드(후보 picker·프리뷰)는 P3 P1 포팅 카드 의존 → **후속**(본 plan은 백엔드 + mock 테스트).
- LIVE 없음. `create_ad_creative`/`replace_creative_tree`는 `_is_sending_mode()`일 때만 Meta 호출, 아니면 합성 결과.

---

## 파일 구조

- **Modify (generator, 크로스팀)** `backend/api/routers/generator.py` — GET `/generations/{id}` 내부 분기를 `X-Org-Id`로 org 스코프.
- **Modify** `backend/domain/management/adapters/generator/client.py` — `get_candidate`에 `org_id` 인자 + `X-Org-Id` 헤더.
- **Modify** `backend/domain/management/contracts/platform.py` — Port에 `create_ad_creative`·`replace_creative_tree` 추가, `replace_creative` 파라미터 `campaign_id`→`ad_id`.
- **Modify** `backend/domain/management/adapters/meta/writer.py` — 위 3개 구현.
- **Create** `backend/domain/management/adapters/meta/creative_image.py` — PNG→JPEG 변환 + 이미지 규격 검증(management 소유).
- **Modify** `backend/domain/management/execution/executor.py` — REPLACE_CREATIVE 분기를 `replace_creative_tree` 호출로 교체(target=campaign).
- **Modify** `backend/api/routers/management.py` — `POST /campaigns/{id}/replace-creative-proposal` 엔드포인트.
- **Modify** `backend/tests/management/helpers.py` — FakeWriter에 신규 메서드, `replace_creative` 파라미터명.
- **Modify** `backend/tests/management/test_meta_writer.py` · `test_executor_gates.py` — 시그니처/분기 갱신.
- **Create** `backend/tests/management/test_replace_creative_proposal.py` — 엔드포인트 테스트.

> 모든 백엔드 `.py` 수정 후 커밋 전 Ruff 제안 규칙(루트 CLAUDE.md) 적용. 각 태스크 커밋 메시지는 `add`/`edit`/`fix` 한국어 컨벤션.

---

## Task 0: 후보-org 누출 차단 (generator GET org 스코프 + client org_id)

generator GET을 내부 호출에도 org 스코프하고, management 클라이언트가 `org_id`를 전달한다. 기존 `from_candidate` 누출도 함께 닫는다. **generator 도메인 변경 — 크로스팀 CODEOWNERS, generator 팀 리뷰 필요.**

**Files:**
- Modify: `backend/api/routers/generator.py` (`get_generation`, line 289~311)
- Modify: `backend/domain/management/adapters/generator/client.py` (`get_candidate`·`_fetch`)
- Modify: `backend/api/routers/management.py` (`from_candidate`의 `get_candidate` 호출에 org_id)
- Test: `backend/tests/management/test_generator_client.py`

- [ ] **Step 1: 실패 테스트 작성** (`test_generator_client.py`에 추가 — 기존 transport 모킹 패턴 사용)

```python
async def test_get_candidate_sends_org_header():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["org"] = request.headers.get("X-Org-Id")
        return httpx.Response(200, json={
            "schema_version": "1", "status": "completed",
            "candidates": [{
                "candidate_id": "c1", "idx": 0, "copy": {"headline": "h", "body": "b"},
                "s3_key": "generated-ads/g1/0.png",
            }],
        })

    client = GeneratorReadClient(base_url="http://gen", transport=httpx.MockTransport(handler))
    await client.get_candidate("g1", "c1", org_id="org-9")
    assert captured["org"] == "org-9"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_generator_client.py -k org_header -v`
Expected: FAIL — `get_candidate()`가 `org_id` 인자를 안 받음(TypeError)

- [ ] **Step 3: client에 org_id 전달** (`adapters/generator/client.py`)

```python
    async def get_candidate(
        self, generation_id: str, candidate_id: str, org_id: str | None = None
    ) -> HandoffCandidate:
        data = await self._fetch(generation_id, org_id)
        # ... (이하 기존 본문 동일)
```

`_fetch`에 org_id 헤더 추가:

```python
    async def _fetch(self, generation_id: str, org_id: str | None = None) -> dict:
        url = f"{self._base_url}/api/generator/generations/{generation_id}"
        headers = dict(self._headers)
        if org_id:
            headers["X-Org-Id"] = str(org_id)
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=self._transport) as client:
            for _ in range(_RETRIES + 1):
                try:
                    resp = await client.get(url, headers=headers)
                # ... (이하 기존 본문 동일)
```

- [ ] **Step 4: generator GET을 org 스코프** (`generator.py` `get_generation`, line 289~311)

`x_org_id` 헤더를 받아 내부 분기에서 `get_detail(generation_id, org)`로 스코프(타 org면 None→404). `get_detail`은 이미 `org_id=None`이면 우회, 주면 검증한다(`generator_service.py:216`).

```python
@router.get("/generations/{generation_id}")
async def get_generation(
    generation_id: str,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """상세 — 로그인 유저는 자기 org만(불일치 404). 내부 호출도 X-Org-Id 있으면 org 스코프."""
    internal = settings.internal_service_token
    use_mock = getattr(settings, "use_mock", True)
    if user is not None:
        detail = await generator_service.get_detail(
            generation_id, await _require_user_org(user, db)
        )
    elif (internal and x_internal_token == internal) or use_mock:
        # 내부 호출도 X-Org-Id가 있으면 org 스코프(타 org 후보 누출 차단). 없으면 기존 우회.
        try:
            org = uuid.UUID(x_org_id) if x_org_id else None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="잘못된 X-Org-Id") from exc
        detail = await generator_service.get_detail(generation_id, org)
    else:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    if detail is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return detail
```

(generator.py 상단에 `import uuid`가 없으면 추가.)

- [ ] **Step 5: `from_candidate`도 org 전달** (`management.py:1897~1906`)

`org_id` 해석을 `get_candidate` 호출 앞으로 끌어올리고 전달:

```python
    org_id = await _require_org_id(user, db)
    client = build_generator_client(settings)
    try:
        cand = await client.get_candidate(body.generation_id, body.candidate_id, org_id=str(org_id))
    except InvalidGenerationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.detail) from exc
    except GeneratorUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

(아래쪽 기존 `org_id = await _require_org_id(user, db)` 중복 줄은 제거.)

- [ ] **Step 6: 통과 확인 + 회귀**

Run: `cd backend && uv run pytest tests/management/test_generator_client.py tests/management/test_management_router.py -v`
Expected: PASS (신규 org 헤더 + 기존 from_candidate 회귀)

> **mock seed 데이터 주의:** generator GET을 X-Org-Id로 스코프하면, 테스트/시드 generation이 호출 org와 연결돼 있어야 404가 안 난다. 기존 from_candidate 테스트가 쓰는 generation이 동일 org 소속인지 확인하고, 아니면 픽스처를 맞춘다.

- [ ] **Step 7: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/generator.py backend/domain/management/adapters/generator/client.py backend/api/routers/management.py backend/tests/management/test_generator_client.py
git commit -m "fix: generator GET 내부호출 org 스코프 — 타 org 후보 누출 차단(B-1 선결)"
```

---

## Task 1: Writer `create_ad_creative` (Port + impl + mock)

소재(image_hash+카피)로 독립 adcreative를 만들어 creative_id를 돌려준다. mock/dry는 합성 id.

**Files:**
- Modify: `backend/domain/management/contracts/platform.py`
- Modify: `backend/domain/management/adapters/meta/writer.py`
- Modify: `backend/tests/management/helpers.py`
- Test: `backend/tests/management/test_meta_writer.py`

- [ ] **Step 1: 실패 테스트 작성** (`test_meta_writer.py`에 추가)

```python
async def test_create_ad_creative_returns_synthetic_id_in_dry_run():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    cid = await writer.create_ad_creative(
        "act_1",
        image_hash="hash-1",
        headline="제목",
        body="본문",
        link_url="https://clickme.co.kr",
        idem_key="key-123456",
    )
    assert isinstance(cid, str) and cid  # 합성이라도 비어있지 않은 id

async def test_create_ad_creative_requires_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        await writer.create_ad_creative(
            "act_1", image_hash="h", headline="t", body="b",
            link_url="https://x", idem_key="",
        )

async def test_create_ad_creative_deterministic_per_idem_key():
    # 멱등(리뷰 ④) — 같은 idem_key면 같은 creative id(집행 retry 시 중복 생성 방지).
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    a = await writer.create_ad_creative("act_1", image_hash="h", headline="t",
                                        body="b", link_url="https://x", idem_key="key-AAAAAAAA")
    b = await writer.create_ad_creative("act_1", image_hash="h2", headline="t2",
                                        body="b2", link_url="https://y", idem_key="key-AAAAAAAA")
    assert a == b  # 같은 idem_key면 입력이 달라도 같은 합성 id
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_meta_writer.py::test_create_ad_creative_returns_synthetic_id_in_dry_run -v`
Expected: FAIL — `AttributeError: 'MetaAdsWriter' object has no attribute 'create_ad_creative'`

- [ ] **Step 3: Port에 선언** (`platform.py`, `AdPlatformWriter` 내부, `replace_creative` 근처)

```python
    async def create_ad_creative(
        self,
        ad_account_id: str,
        *,
        image_hash: str | None,
        headline: str,
        body: str,
        link_url: str,
        idem_key: str,
    ) -> str: ...
```

- [ ] **Step 4: writer 구현** (`writer.py`, `replace_creative` 아래에 추가)

```python
    async def create_ad_creative(
        self,
        ad_account_id: str,
        *,
        image_hash: str | None,
        headline: str,
        body: str,
        link_url: str,
        idem_key: str,
    ) -> str:
        """소재(이미지+카피)로 독립 adcreative 생성 → creative_id. 승인 후 집행 시점에만 호출.

        mock/dry는 합성 id 반환(Meta 미호출). LIVE/validate는 /act_{id}/adcreatives POST.
        ⚠ LIVE는 Meta 앱 Live 모드 전제(B-0 Q0.4 — 개발모드면 code100/subcode1885183).
        """
        self._require_writable(idem_key)
        spec = {
            "page_id": self._page_id,
            "link_data": {
                "message": body or headline or "지금 확인하세요",
                "name": headline,
                "link": link_url,
                "call_to_action": {"type": "LEARN_MORE"},
                **({"image_hash": image_hash} if image_hash else {}),
            },
        }
        if self._mode not in _SENDING_MODES or self._client is None:
            return f"mockcreative_{idem_key[:12]}"
        account = normalize_ad_account(ad_account_id)
        resp = await self._client.post(
            f"{account}/adcreatives",
            {"name": f"clickme-creative-{idem_key[:8]}", "object_story_spec": json.dumps(spec)},
        )
        cid = resp.get("id") if isinstance(resp, dict) else None
        if not cid:
            raise ValueError("adcreative 생성 응답에 id 없음")
        return str(cid)
```

- [ ] **Step 5: FakeWriter에 추가** (`helpers.py`, `FakeWriter` 내부)

```python
    async def create_ad_creative(
        self, ad_account_id: str, *, image_hash, headline, body, link_url, idem_key: str
    ) -> str:
        if not idem_key:
            raise ValueError("idem_key 필수")
        self.calls.append(("create_ad_creative", ad_account_id, idem_key))
        return f"fakecreative_{idem_key[:8]}"
```

- [ ] **Step 6: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_meta_writer.py -k create_ad_creative -v`
Expected: PASS (2 tests)

- [ ] **Step 7: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/contracts/platform.py backend/domain/management/adapters/meta/writer.py backend/tests/management/helpers.py backend/tests/management/test_meta_writer.py
git commit -m "add: create_ad_creative — 소재로 독립 adcreative 생성(mock 합성)"
```

---

## Task 2: 이미지 변환·규격 검증 유틸

PNG→JPEG 변환과 Meta 업로드 전 규격 검증. 위반이면 예외 → 라우터가 422로 거부.

**Files:**
- Create: `backend/domain/management/adapters/meta/creative_image.py`
- Test: `backend/tests/management/test_creative_image.py`

- [ ] **Step 1: 실패 테스트 작성** (`test_creative_image.py` 신규)

```python
# 이미지 규격 검증·변환 유틸 테스트
import io

import pytest
from PIL import Image

from domain.management.adapters.meta.creative_image import (
    ImageSpecError,
    to_meta_jpeg,
    validate_image_spec,
)


def _png(w: int, h: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_validate_rejects_too_small():
    with pytest.raises(ImageSpecError, match="최소"):
        validate_image_spec(_png(100, 100))


def test_validate_rejects_extreme_ratio():
    with pytest.raises(ImageSpecError, match="비율"):
        validate_image_spec(_png(1080, 100))


def test_to_meta_jpeg_converts_rgba_to_rgb_jpeg():
    out = to_meta_jpeg(_png(1080, 1080, mode="RGBA"))
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.mode == "RGB"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_creative_image.py -v`
Expected: FAIL — `ModuleNotFoundError: ... creative_image`

- [ ] **Step 3: 구현** (`creative_image.py` 신규)

```python
# Meta 광고 소재 업로드 전 규격 검증 + PNG→JPEG 변환 유틸
from __future__ import annotations

import io

from PIL import Image

# Meta 권장 기준(보수적 v1) — 정사각/세로 피드 최소.
_MIN_SIDE = 600
_MIN_RATIO, _MAX_RATIO = 0.5, 1.91  # 세로 1:2 ~ 가로 1.91:1
_MAX_BYTES = 30 * 1024 * 1024  # 30MB
_JPEG_QUALITY = 90


class ImageSpecError(ValueError):
    """이미지가 Meta 업로드 규격에 맞지 않음 — 라우터가 422로 변환."""


def validate_image_spec(image_bytes: bytes) -> None:
    if len(image_bytes) > _MAX_BYTES:
        raise ImageSpecError(f"파일 크기 초과(최대 {_MAX_BYTES // (1024 * 1024)}MB)")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()  # 손상 검사
        img = Image.open(io.BytesIO(image_bytes))  # verify 후 재오픈 필요
    except Exception as exc:  # noqa: BLE001 — 손상/비이미지
        raise ImageSpecError("이미지를 열 수 없음(손상/비이미지)") from exc
    w, h = img.size
    if min(w, h) < _MIN_SIDE:
        raise ImageSpecError(f"최소 한 변 {_MIN_SIDE}px 필요(현재 {w}x{h})")
    ratio = w / h if h else 0
    if not (_MIN_RATIO <= ratio <= _MAX_RATIO):
        raise ImageSpecError(f"가로세로 비율 범위 밖({_MIN_RATIO}~{_MAX_RATIO}, 현재 {ratio:.2f})")


def to_meta_jpeg(image_bytes: bytes) -> bytes:
    """RGBA/팔레트/투명 alpha를 흰 배경 RGB로 합성 후 JPEG 인코딩(Meta는 JPEG 권장)."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY)
    return out.getvalue()
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_creative_image.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/adapters/meta/creative_image.py backend/tests/management/test_creative_image.py
git commit -m "add: 소재 이미지 규격 검증 + PNG→JPEG 변환 유틸"
```

---

## Task 3: Writer `replace_creative_tree` + `replace_creative` ad_id 정정

집행 시점 오케스트레이션 — adcreative 1회 생성 후 캠페인 하위 광고로 fan-out 교체(`activate_tree` 패턴).

**Files:**
- Modify: `backend/domain/management/contracts/platform.py`
- Modify: `backend/domain/management/adapters/meta/writer.py`
- Modify: `backend/tests/management/helpers.py`
- Test: `backend/tests/management/test_meta_writer.py`

- [ ] **Step 1: 실패 테스트 작성** (`test_meta_writer.py`)

```python
async def test_replace_creative_param_is_ad_id():
    # 시그니처 정정 회귀 — 받은 id가 그대로 대상이 된다(이제 ad_id 의미).
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.replace_creative("ad-1", "creative-9", "key-1")
    assert result.status is ResultStatus.SUCCESS
    assert result.platform_response_snapshot["campaign_id"] == "ad-1"  # _dispatch 라벨 키(대상 id)
    assert result.platform_response_snapshot["creative_id"] == "creative-9"

async def test_replace_creative_tree_dry_run_creates_one_creative():
    # mock(DRY_RUN)은 자식 조회 불가 → tree orchestration(creative 1회 생성 + 캠페인 결과)까지만 검증.
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.replace_creative_tree(
        "camp-1",
        ad_account_id="act_1",
        image_hash="h",
        headline="제목",
        body="본문",
        link_url="https://clickme.co.kr",
        idem_key="key-abcdef",
    )
    assert result.status is ResultStatus.SUCCESS
    snap = result.platform_response_snapshot
    assert snap["operation"] == "replace_creative"
    assert snap["creative_id"].startswith("mockcreative_")  # 1회 생성된 합성 creative


class _StubClient:
    """fan-out 검증용 — 실 Meta 대신 자식 ad 2개를 돌려주고 POST 경로를 기록."""

    def __init__(self):
        self.posts: list[str] = []

    async def get(self, path, params=None):
        return {"data": [{"id": "ad-1"}, {"id": "ad-2"}]}

    async def post(self, path, data, validate_only=False):
        self.posts.append(path)
        return {"id": "obj-1"}


async def test_replace_creative_tree_fans_out_to_each_ad():
    # fan-out 계약 — sending mode + stub client에서 하위 ad마다 creative 교체 POST(LIVE 미호출).
    stub = _StubClient()
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=stub)
    result = await writer.replace_creative_tree(
        "camp-1",
        ad_account_id="act_1",
        image_hash="h",
        headline="제목",
        body="본문",
        link_url="https://clickme.co.kr",
        idem_key="key-1",
    )
    assert result.status is ResultStatus.SUCCESS
    # adcreatives 생성 1회 + 하위 ad-1·ad-2 각각 교체 POST.
    assert "ad-1" in stub.posts and "ad-2" in stub.posts
    assert any("adcreatives" in p for p in stub.posts)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_meta_writer.py -k "replace_creative_tree or param_is_ad_id" -v`
Expected: FAIL — `replace_creative_tree` 없음

- [ ] **Step 3: `replace_creative` 시그니처 정정** (`writer.py:123` 및 `platform.py:70`)

writer.py — 파라미터명만 `campaign_id`→`ad_id`로 바꾸고 독스트링 갱신(본문 로직 동일, `_dispatch`에 `ad_id` 전달):

```python
    async def replace_creative(self, ad_id: str, creative_id: str, idem_key: str) -> ActionResult:
        """광고(ad) 단위 creative 교체 — POST /{ad_id}{creative:{creative_id}} (B-0 Q0b.2 확정).

        호출 주체는 executor 단일 경로 또는 replace_creative_tree(캠페인 fan-out).
        """
        self._require_writable(idem_key)
        return await self._dispatch(
            "replace_creative",
            ad_id,
            idem_key,
            {"creative": {"creative_id": creative_id}},
            creative_id=creative_id,
        )
```

platform.py — Port 파라미터명 정정:

```python
    async def replace_creative(
        self, ad_id: str, creative_id: str, idem_key: str
    ) -> ActionResult: ...
```

- [ ] **Step 4: `replace_creative_tree` 구현** (`writer.py`, `replace_creative` 아래; Port에도 선언)

platform.py Port 추가:

```python
    async def replace_creative_tree(
        self,
        campaign_id: str,
        *,
        ad_account_id: str,
        image_hash: str | None,
        headline: str,
        body: str,
        link_url: str,
        idem_key: str,
    ) -> ActionResult: ...
```

writer.py 구현:

```python
    async def replace_creative_tree(
        self,
        campaign_id: str,
        *,
        ad_account_id: str,
        image_hash: str | None,
        headline: str,
        body: str,
        link_url: str,
        idem_key: str,
    ) -> ActionResult:
        """adcreative 1회 생성 → 캠페인 하위 광고에 fan-out 교체 (activate_tree 패턴).

        고아 방지 — 승인 후 집행 시점에만 호출되므로 취소/만료 건은 creative를 만들지 않는다.
        DRY_RUN/mock은 자식 조회 불가 → creative 1회 생성(합성)·캠페인 단위 결과만.
        """
        self._require_writable(idem_key)
        creative_id = await self.create_ad_creative(
            ad_account_id,
            image_hash=image_hash,
            headline=headline,
            body=body,
            link_url=link_url,
            idem_key=f"{idem_key}-creative",
        )
        if self._mode not in _SENDING_MODES or self._client is None:
            return self._result(
                "replace_creative", campaign_id, idem_key, dry_run=True, creative_id=creative_id
            )
        ad_ids = await self._child_ids(f"{campaign_id}/ads")
        for i, ad_id in enumerate(ad_ids):
            r = await self.replace_creative(ad_id, creative_id, f"{idem_key}-ad-{i}")
            if r.status is not ResultStatus.SUCCESS:
                return r
        return self._result(
            "replace_creative",
            campaign_id,
            idem_key,
            dry_run=False,
            creative_id=creative_id,
            ad_count=len(ad_ids),
        )
```

- [ ] **Step 5: FakeWriter 갱신** (`helpers.py`)

`replace_creative` 파라미터명 `campaign_id`→`ad_id`(본문 동일) + `replace_creative_tree` 추가:

```python
    async def replace_creative(self, ad_id: str, creative_id: str, idem_key: str) -> ActionResult:
        return self._respond("REPLACE_CREATIVE", ad_id, idem_key)

    async def replace_creative_tree(
        self, campaign_id: str, *, ad_account_id, image_hash, headline, body, link_url, idem_key: str
    ) -> ActionResult:
        await self.create_ad_creative(
            ad_account_id, image_hash=image_hash, headline=headline,
            body=body, link_url=link_url, idem_key=f"{idem_key}-creative",
        )
        return self._respond("REPLACE_CREATIVE", campaign_id, idem_key)
```

- [ ] **Step 6: 통과 확인 + 기존 회귀**

Run: `cd backend && uv run pytest tests/management/test_meta_writer.py -v`
Expected: PASS (신규 + 기존 `test_replace_creative_carries_creative_id`는 `ad-1` 의미로 그대로 통과 — 값 검증은 동일)

- [ ] **Step 7: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/contracts/platform.py backend/domain/management/adapters/meta/writer.py backend/tests/management/helpers.py backend/tests/management/test_meta_writer.py
git commit -m "add: replace_creative_tree(집행시점 변환+fan-out) + replace_creative ad_id 정정"
```

---

## Task 4: executor REPLACE_CREATIVE 분기 교체

`selected_candidate_id` 직접 전달 → `replace_creative_tree`(evidence_metrics의 소재 필드) 호출로 교체.

**Files:**
- Modify: `backend/domain/management/execution/executor.py` (`_dispatch`, line 387~392)
- Test: `backend/tests/management/test_executor_gates.py` (line 384~410 갱신)

- [ ] **Step 1: 실패 테스트 작성/갱신** (`test_executor_gates.py`)

기존 `test_replace_creative_dispatches_to_writer`를 소재 필드 기반으로 갱신하고, 누락 검증 테스트를 교체한다.

```python
async def test_replace_creative_calls_tree_with_creative_fields():
    writer = FakeWriter()
    executor = _build_executor(writer)  # 기존 헬퍼
    proposal = make_proposal(
        action_type="REPLACE_CREATIVE",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("camp-1",),
        evidence_metrics={
            "image_hash": "h",
            "headline": "제목",
            "body": "본문",
            "link_url": "https://clickme.co.kr",
            "generation_id": "g1",
            "candidate_id": "c1",
        },
    )
    action = approved_for(proposal, approver_id="user-1")  # 사람 승인(AUTO 아님)
    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.SUCCESS
    assert ("create_ad_creative", proposal.ad_account_id, ANY) in [
        (c[0], c[1], c[2]) for c in writer.calls
    ] or any(c[0] == "create_ad_creative" for c in writer.calls)

async def test_replace_creative_missing_fields_fails():
    writer = FakeWriter()
    executor = _build_executor(writer)
    proposal = make_proposal(
        action_type="REPLACE_CREATIVE",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("camp-1",),
        evidence_metrics={"headline": "제목"},  # body/link_url 누락
    )
    action = approved_for(proposal, approver_id="user-1")
    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.FAILED

async def test_replace_creative_idempotent_replay():
    # 멱등(리뷰 ④-ⓑ) — 같은 승인/idem 재실행은 결과 재생, writer 재호출 없음.
    writer = FakeWriter()
    executor = _build_executor(writer)
    proposal = make_proposal(
        action_type="REPLACE_CREATIVE",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("camp-1",),
        evidence_metrics={
            "image_hash": "h", "headline": "제목", "body": "본문",
            "link_url": "https://clickme.co.kr",
        },
    )
    action = approved_for(proposal, approver_id="user-1")
    first = await executor.execute(action, proposal)
    calls_after_first = list(writer.calls)
    second = await executor.execute(action, proposal)
    assert second.result_id == first.result_id  # 재생된 동일 결과
    assert writer.calls == calls_after_first  # writer 재호출 없음(중복 side effect 없음)
```

> 기존 테스트의 헬퍼명(`make_proposal`/`approved_for`/`_build_executor`)이 다르면 파일 내 실제 헬퍼에 맞춘다 — `test_executor_gates.py` 상단 헬퍼를 그대로 사용.

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_executor_gates.py -k replace_creative -v`
Expected: FAIL — 현재 분기가 `selected_candidate_id`를 읽어 `replace_creative(target, ...)` 호출(필드 누락 무시)

- [ ] **Step 3: executor 분기 교체** (`executor.py` `_dispatch`, 기존 REPLACE_CREATIVE 블록 대체)

```python
        if proposal.action_type == "REPLACE_CREATIVE":
            em = proposal.evidence_metrics
            image_hash = em.get("image_hash")
            headline = em.get("headline")
            body = em.get("body")
            link_url = em.get("link_url")
            # 빌드 단계가 항상 채우는 소재 필드 — 없으면 계약 위반(_validate 통과분 방어).
            # image_hash 필수: REPLACE는 "후보 이미지로 교체"가 핵심이라 텍스트-only는 불허.
            if not image_hash or not headline or not body or not link_url:
                raise ValueError(
                    "REPLACE_CREATIVE 제안에 소재 필드(image_hash/headline/body/link_url) 없음"
                )
            return await self._writer.replace_creative_tree(
                target,  # 캠페인 id — writer가 하위 ad로 fan-out
                ad_account_id=proposal.ad_account_id,
                image_hash=str(image_hash),
                headline=str(headline),
                body=str(body),
                link_url=str(link_url),
                idem_key=idem_key,
            )
```

기존 주석(executor.py:42)의 "selected_candidate_id 참조"도 소재 필드 기반으로 한 줄 갱신.

- [ ] **Step 4: 통과 확인 + 전체 게이트 회귀**

Run: `cd backend && uv run pytest tests/management/test_executor_gates.py -v`
Expected: PASS (신규 2 + 기존 게이트 회귀)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/execution/executor.py backend/tests/management/test_executor_gates.py
git commit -m "edit: executor REPLACE_CREATIVE를 replace_creative_tree(소재 필드)로 교체"
```

---

## Task 5: `replace-creative-proposal` 엔드포인트

빌드 시점 — 캠페인 소유권 검증·후보 핸드오프·이미지 규격검증·업로드·proposal 빌드·프리뷰 영향 광고.

**Files:**
- Modify: `backend/api/routers/management.py`
- Test: `backend/tests/management/test_replace_creative_proposal.py` (신규)

- [ ] **Step 1: 실패 테스트 작성** (`test_replace_creative_proposal.py` 신규)

`from_candidate` 테스트(있으면 `test_management_router.py`)의 인증·DB·generator client 픽스처 패턴을 그대로 따른다. 핵심 단언만.

```python
# /campaigns/{id}/replace-creative-proposal 엔드포인트 테스트(mock)
import pytest

pytestmark = pytest.mark.asyncio


async def test_replace_creative_proposal_builds_tier3_with_creative_fields(client, owned_campaign, fake_generator):
    resp = await client.post(
        f"/api/management/campaigns/{owned_campaign}/replace-creative-proposal",
        json={"generation_id": "g1", "candidate_id": "c1", "link_url": "https://clickme.co.kr"},
    )
    assert resp.status_code == 200
    proposal = resp.json()["proposal"]
    assert proposal["action_type"] == "REPLACE_CREATIVE"
    assert proposal["action_tier"] == 3
    em = proposal["evidence_metrics"]
    assert em["headline"] and em["body"] and em["link_url"]
    assert em["generation_id"] == "g1" and em["candidate_id"] == "c1"


async def test_replace_creative_proposal_rejects_unowned_campaign(client, other_org_campaign):
    resp = await client.post(
        f"/api/management/campaigns/{other_org_campaign}/replace-creative-proposal",
        json={"generation_id": "g1", "candidate_id": "c1", "link_url": "https://clickme.co.kr"},
    )
    assert resp.status_code in (403, 404)

async def test_replace_creative_proposal_rejects_other_org_candidate(client, owned_campaign, fake_generator):
    # 후보-org 누출 차단(리뷰 ②) — 타 org generation은 generator org 스코프로 404.
    # fake_generator는 호출 org와 다른 generation_id면 InvalidGenerationError(404)를 던지게 구성.
    resp = await client.post(
        f"/api/management/campaigns/{owned_campaign}/replace-creative-proposal",
        json={"generation_id": "other-org-gen", "candidate_id": "c1", "link_url": "https://clickme.co.kr"},
    )
    assert resp.status_code == 404
```

> 픽스처(`client`·`owned_campaign`·`other_org_campaign`·`fake_generator`)는 기존 `test_management_router.py`/`conftest.py`의 동일 패턴을 재사용한다. 없으면 `from_candidate` 테스트가 쓰는 픽스처를 참고해 맞춘다.

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_replace_creative_proposal.py -v`
Expected: FAIL — 404(라우트 없음)

- [ ] **Step 3: 요청 모델 + 엔드포인트 구현** (`management.py`, `from_candidate` 근처에 추가)

```python
class ReplaceCreativeRequest(BaseModel):
    generation_id: str
    candidate_id: str
    link_url: HttpUrl


@router.post("/campaigns/{campaign_id}/replace-creative-proposal")
async def replace_creative_proposal(
    campaign_id: str,
    body: ReplaceCreativeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """generator 후보 → REPLACE_CREATIVE 제안. adcreative 생성은 집행 시점(executor)에서.

    소유권: 자기 캠페인만 교체(파괴적 행위 차단) + 후보-org는 Task 0의 X-Org-Id 스코프로 닫힘(타 org면 404).
    """
    org_id = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_id, campaign_id)  # 캠페인 소유권(필수)

    # B-1은 mock 계약 고정 — sending mode(validate/live)면 실 /adimages 호출이 되므로 차단(리뷰 ③).
    # _is_sending_mode()는 기존 모듈 헬퍼(management.py:204) — use_mock·management_execution_mode 기준.
    if _is_sending_mode():
        raise HTTPException(status_code=501, detail="REPLACE_CREATIVE LIVE는 미지원(B-1 mock 범위).")

    client = build_generator_client(settings)
    try:
        # org 전달 — generator가 내부 호출도 org 스코프(타 org 후보 누출 차단, 리뷰 ②).
        cand = await client.get_candidate(body.generation_id, body.candidate_id, org_id=str(org_id))
    except InvalidGenerationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.detail) from exc
    except GeneratorUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        image_bytes = await download_bytes(cand.s3_key)
    except Exception as exc:  # noqa: BLE001 — S3 유실/손상은 입력 문제로 거부
        raise HTTPException(status_code=422, detail="후보 이미지를 읽을 수 없습니다.") from exc

    try:
        validate_image_spec(image_bytes)  # 규격 위반이면 집행 없이 거부(리뷰 ⑥)
        jpeg = to_meta_jpeg(image_bytes)
    except ImageSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    ad_account = await _require_ad_account(db, org_id)
    writer = await _require_writer(db, org_id)
    # non-sending(mock)에서 MetaAdsWriter.upload_image는 실 /adimages 미호출(None 반환 가능).
    # image_hash는 REPLACE 핵심(이미지 교체)이라 항상 채운다 — mock이면 합성 해시로 폴백(executor가 필수 검사).
    image_hash = await _upload_creative_or_502(
        writer, _asset_config(name=cand.candidate_id), jpeg, "candidate.jpg"
    ) or f"mockhash_{cand.candidate_id}"

    reader = await _require_reader(db, org_id)
    affected = await reader.get_creatives(campaign_id)  # 프리뷰: 영향 광고(현재 썸네일/이름)

    now = datetime.now(UTC)
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=str(org_id),
            ad_account_id=ad_account,
            target_object_ids=(campaign_id,),  # 캠페인 — writer가 하위 ad로 fan-out
            action_type="REPLACE_CREATIVE",
            action_tier=ActionTier.TIER_3,
            evidence_metrics={
                "image_hash": image_hash,
                "headline": cand.copy.headline,
                "body": cand.copy.body,
                "link_url": str(body.link_url),
                "generation_id": body.generation_id,
                "candidate_id": cand.candidate_id,
                "affected_ad_count": len(affected),
            },
            metrics_as_of=now,
            hypothesis="후보 기반 소재 교체",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=0,
            budget_after_krw=0,
            max_total_spend_krw=0,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )
    return {
        "proposal": proposal.model_dump(mode="json"),
        "preview": {
            "candidate": {"headline": cand.copy.headline, "body": cand.copy.body, "s3_key": cand.s3_key},
            "affected_ads": [a.model_dump(mode="json") for a in affected],
        },
    }
```

import 추가(파일 상단 기존 import 그룹에): `from domain.management.adapters.meta.creative_image import ImageSpecError, to_meta_jpeg, validate_image_spec`.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_replace_creative_proposal.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_replace_creative_proposal.py
git commit -m "add: replace-creative-proposal 엔드포인트(캠페인 소유권·규격검증·집행시점 변환)"
```

---

## Task 6: 통합 회귀 + Ruff 전체

전체 management 테스트와 Ruff로 회귀 확인.

**Files:** (없음 — 검증만)

- [ ] **Step 1: 전체 management 테스트**

Run: `cd backend && uv run pytest tests/management/ -v`
Expected: 전부 PASS(시그니처 변경 회귀 포함)

- [ ] **Step 2: Ruff 전체**

Run: `cd backend && uv run ruff format . && uv run ruff check .`
Expected: 클린(또는 --fix 후 클린)

- [ ] **Step 3: 변경 있으면 커밋**

```bash
git add -A backend/
git commit -m "fix: B-1 회귀·lint 정리"
```

---

## Self-Review (작성자 확인 완료)

- **Spec 커버리지:** spec §3 빌드/집행 분리 → Task 5(빌드)·Task 3·4(집행). §4 계약변경(replace_creative ad_id·신규 메서드) → Task 1·3. §6① 고아차단(집행시점) → Task 3·4. §6② 후보-org 누출 차단(generator org 스코프) → **Task 0**. §6③ 캠페인 소유권 → Task 5(`_require_owned_campaign`). §6④ no-op 하드게이트 없음 → 미구현(의도적). §6⑤ 프리뷰 → Task 5(`get_creatives`). §6⑥ 규격검증 → Task 2·5. §6⑦ LIVE 게이트=execution_mode → Task 1·3(`_is_sending_mode`) + Task 5(sending mode 501 차단). §3-10 멱등 결정성 → Task 1(determinism 테스트). §8 mock 테스트 → 각 태스크.
- **No-placeholder:** 모든 코드 스텝에 실제 코드. 픽스처는 기존 패턴 재사용을 명시(추정 금지·실제 헬퍼에 맞추라 지시). Task 0의 mock seed org 연결은 Step 6 주의로 명시.
- **타입 일관:** `create_ad_creative`(ad_account_id, *, image_hash, headline, body, link_url, idem_key)→str / `replace_creative`(ad_id, creative_id, idem_key) / `replace_creative_tree`(campaign_id, *, ad_account_id, image_hash, headline, body, link_url, idem_key) / `get_candidate`(generation_id, candidate_id, org_id=None) — Task 0·1·3·4·5·helpers 전반 동일.
- **범위:** 프론트 카드·LIVE adcreative·LIVE 멱등 dedup은 후속으로 명시(YAGNI). 후보-org 누출은 Task 0에서 닫음(크로스팀 generator 변경 — 리뷰 필요).
- **실행 순서:** Task 0(generator 선결) → 1 → 2 → 3 → 4 → 5 → 6.
