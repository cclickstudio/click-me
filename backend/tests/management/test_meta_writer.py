"""🅱 MetaAdsWriter — idem_key 강제·모드 게이팅·DRY_RUN 응답 형태 검증.

LIVE 봉인은 writer가 아니라 executor.DEFAULT_ALLOWED_MODES + use_mock 이중 게이트가
담당한다 (계획 §게이팅). writer 차원 방어는 "자격증명 없으면 미전송".
"""

import httpx
import pytest

from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import ExecutionMode, ResultStatus


async def test_empty_idem_key_is_rejected():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        await writer.pause("camp-1", "")


async def test_live_mode_without_credentials_does_not_send():
    """LIVE 코드 경로는 존재하나, 자격증명(토큰) 없이는 네트워크로 나가지 않는다.

    실제 LIVE 봉인은 executor 허용 모드 + use_mock 이중 게이트의 몫 (§7 Won't).
    writer 단독 방어 = 토큰 없으면 합성 결과로 폴백.
    """
    writer = MetaAdsWriter(mode=ExecutionMode.LIVE)  # settings 없음 → 클라이언트 미구성
    result = await writer.pause("camp-1", "key-1")
    assert result.status is ResultStatus.SUCCESS
    assert result.platform_response_snapshot["meta_response"] is None
    assert result.platform_response_snapshot["mode"] == "live"


async def test_negative_krw_is_rejected():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="KRW"):
        await writer.adjust_budget("camp-1", -1, "key-1")


async def test_dry_run_snapshot_shape():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.adjust_budget("camp-1", 40_000, "key-1")

    assert result.status is ResultStatus.SUCCESS
    assert result.idempotency_key == "key-1"
    snapshot = result.platform_response_snapshot
    assert snapshot["dry_run"] is True
    assert snapshot["operation"] == "adjust_budget"
    assert snapshot["amount_krw"] == 40_000


async def test_mode_read_from_settings_object():
    class FakeSettings:
        management_execution_mode = "validate_only"

    writer = MetaAdsWriter(FakeSettings())
    result = await writer.pause("camp-1", "key-1")
    assert result.platform_response_snapshot["mode"] == "validate_only"


async def test_preview_needs_no_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    url = await writer.preview("camp-1")
    assert "camp-1" in url


async def test_replace_creative_carries_creative_id():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.replace_creative("camp-1", "cand-42", "key-1")

    assert result.status is ResultStatus.SUCCESS
    snapshot = result.platform_response_snapshot
    assert snapshot["operation"] == "replace_creative"
    assert snapshot["creative_id"] == "cand-42"


async def test_replace_creative_requires_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        await writer.replace_creative("camp-1", "cand-42", "")


# ── create_ad_creative (Task 1) ──────────────────────────────────────


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
            "act_1",
            image_hash="h",
            headline="t",
            body="b",
            link_url="https://x",
            idem_key="",
        )


async def test_create_ad_creative_deterministic_per_idem_key():
    # 멱등(리뷰 ④) — 같은 idem_key면 같은 creative id(집행 retry 시 중복 생성 방지).
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    a = await writer.create_ad_creative(
        "act_1",
        image_hash="h",
        headline="t",
        body="b",
        link_url="https://x",
        idem_key="key-AAAAAAAA",
    )
    b = await writer.create_ad_creative(
        "act_1",
        image_hash="h2",
        headline="t2",
        body="b2",
        link_url="https://y",
        idem_key="key-AAAAAAAA",
    )
    assert a == b  # 같은 idem_key면 입력이 달라도 같은 합성 id


class _RecordingClient:
    """validate_only 인자를 기록하는 stub(실 생성 방지 검증용, 리뷰 P1-1)."""

    def __init__(self):
        self.validate_flags: list[bool] = []

    async def post(self, path, data, validate_only=False):
        self.validate_flags.append(validate_only)
        return {"id": "real-creative-1"}


async def test_create_ad_creative_validate_only_passes_flag():
    # VALIDATE_ONLY 모드는 client.post에 validate_only=True를 넘겨 실 adcreative 생성을 막아야 한다.
    stub = _RecordingClient()
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=stub)
    await writer.create_ad_creative(
        "act_1",
        image_hash="h",
        headline="t",
        body="b",
        link_url="https://x",
        idem_key="key-1",
    )
    assert stub.validate_flags == [True]


# ── replace_creative ad_id 정정 + replace_creative_tree (Task 3) ──────


async def test_replace_creative_param_is_ad_id():
    # 시그니처 정정 회귀 — 받은 id가 그대로 대상이 된다(이제 ad_id 의미).
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.replace_creative("ad-1", "creative-9", "key-1")
    assert result.status is ResultStatus.SUCCESS
    # ⚠ legacy 키: _dispatch가 대상 id를 여전히 "campaign_id" 키로 스냅샷에 적재한다(리뷰 P3-1).
    assert result.platform_response_snapshot["campaign_id"] == "ad-1"  # = 대상 ad_id(legacy 키명)
    assert result.platform_response_snapshot["creative_id"] == "creative-9"


async def test_replace_creative_tree_dry_run_creates_one_creative():
    # DRY_RUN — adcreative 1회 합성 생성 + 결속 ad_ids fan-out(dry는 각 ad 합성 성공).
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.replace_creative_tree(
        "camp-1",
        ad_ids=["ad-1", "ad-2"],
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
    assert snap["ad_count"] == 2


class _StubClient:
    """fan-out 검증용 — POST 경로만 기록(실 Meta 미호출). ad_ids는 인자로 결속되므로 get 불필요."""

    def __init__(self):
        self.posts: list[str] = []

    async def post(self, path, data, validate_only=False):
        self.posts.append(path)
        return {"id": "obj-1"}


async def test_replace_creative_tree_fans_out_over_bound_ad_ids():
    # fan-out 계약(리뷰 ①③) — 결속된 ad_ids 각각에 creative 교체 POST(_child_ids 재조회 없음).
    stub = _StubClient()
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=stub)
    result = await writer.replace_creative_tree(
        "camp-1",
        ad_ids=["ad-1", "ad-2"],
        ad_account_id="act_1",
        image_hash="h",
        headline="제목",
        body="본문",
        link_url="https://clickme.co.kr",
        idem_key="key-1",
    )
    assert result.status is ResultStatus.SUCCESS
    # adcreatives 생성 1회 + 결속된 ad-1·ad-2 각각 교체 POST.
    assert "ad-1" in stub.posts and "ad-2" in stub.posts
    assert any("adcreatives" in p for p in stub.posts)
    assert result.platform_response_snapshot["ad_count"] == 2


async def test_replace_creative_tree_partial_failure_records_progress():
    # 부분 교체(리뷰 P1-c) — 중간 ad 실패 시 succeeded/failed를 결과에 남긴다.
    class _FailSecond:
        def __init__(self):
            self.posts: list[str] = []

        async def post(self, path, data, validate_only=False):
            self.posts.append(path)
            if path == "ad-2":
                raise httpx.HTTPError("boom")  # _dispatch가 PLATFORM_ERROR로 변환
            return {"id": "obj"}

    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=_FailSecond())
    result = await writer.replace_creative_tree(
        "camp-1",
        ad_ids=["ad-1", "ad-2", "ad-3"],
        ad_account_id="act_1",
        image_hash="h",
        headline="t",
        body="b",
        link_url="https://x",
        idem_key="k",
    )
    assert result.status is ResultStatus.FAILED
    snap = result.platform_response_snapshot
    assert snap["succeeded_ad_ids"] == ["ad-1"]
    assert snap["failed_ad_id"] == "ad-2"


async def test_replace_creative_tree_empty_ad_ids_makes_no_creative():
    # 빈 ad_ids는 creative 생성 前에 거부(리뷰 P1-2) — 고아 adcreative 방지.
    stub = _StubClient()
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=stub)
    with pytest.raises(ValueError, match="ad_ids"):
        await writer.replace_creative_tree(
            "camp-1",
            ad_ids=[],
            ad_account_id="act_1",
            image_hash="h",
            headline="t",
            body="b",
            link_url="https://x",
            idem_key="k",
        )
    assert stub.posts == []  # adcreatives POST조차 없음


async def test_replace_creative_tree_rejects_string_ad_ids():
    # 문자열 ad_ids(리뷰 P1-1) — 글자 단위 순회 방지. creative도 안 만든다.
    stub = _StubClient()
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=stub)
    with pytest.raises(ValueError, match="ad_ids"):
        await writer.replace_creative_tree(
            "camp-1",
            ad_ids="ad-1",
            ad_account_id="act_1",
            image_hash="h",
            headline="t",
            body="b",
            link_url="https://x",
            idem_key="k",
        )
    assert stub.posts == []


async def test_replace_creative_tree_validate_only_synthetic_is_not_success():
    # codex 리뷰 #6 — validate_only에서 creative가 미영속(합성 id)이면 fan-out을 실제 검증할 수
    # 없으므로 success로 보고하지 않는다(false-green 방지). client 없음 → create가 합성 id 반환.
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=None)
    result = await writer.replace_creative_tree(
        "camp-1",
        ad_ids=["ad-1", "ad-2"],
        ad_account_id="act_1",
        image_hash="h",
        headline="t",
        body="b",
        link_url="https://x",
        idem_key="k",
    )
    assert result.status is ResultStatus.FAILED
    assert result.platform_response_snapshot.get("validate_note")
