# /campaigns/{id}/replace-creative-proposal 엔드포인트 테스트(mock)
import io
import uuid
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from api.routers import management
from core.auth import get_current_user
from core.db import get_db
from domain.management.adapters.generator.client import (
    GeneratorReadClient,
    HandoffCandidate,
    InvalidGenerationError,
)
from domain.management.contracts.schemas import CreativePreview

_URL_TMPL = "/api/management/campaigns/{cid}/replace-creative-proposal"
_OWNED = "camp-owned"
_OTHER = "camp-other"
_EMPTY = "camp-empty"


def _png(w=1080, h=1080) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


_PNG_BYTES = _png()


def _cand(headline="제목", body="본문") -> HandoffCandidate:
    return HandoffCandidate.model_validate(
        {
            "candidate_id": "c1",
            "idx": 0,
            "strategy": {},
            "template_id": "t",
            "copy": {"headline": headline, "body": body, "cta": "사기"},
            "s3_key": "generated-ads/g1/0.png",
        }
    )


class _FakeReader:
    def __init__(self, creatives):
        self._creatives = creatives

    async def get_creatives(self, campaign_id):
        return self._creatives


class _FakeWriter:
    async def upload_image(self, config, image_bytes, filename, idem_key):
        return None  # mock — 합성 해시로 폴백


class _Recorder:
    last_org_id = None


def _setup(
    monkeypatch,
    *,
    candidate=None,
    creatives=None,
    sending=False,
):
    rec = _Recorder()
    cand = candidate if candidate is not None else _cand()

    async def fake_get_candidate(self, gen_id, cand_id, org_id=None):
        rec.last_org_id = org_id
        if gen_id == "other-org-gen":
            raise InvalidGenerationError(404, "candidate가 해당 generation에 없음")
        return cand

    async def fake_download(key):
        return _PNG_BYTES

    async def fake_owned(db, org_id, campaign_id):
        if campaign_id == _OTHER:
            raise HTTPException(403, "다른 조직의 캠페인입니다.")
        return None

    async def fake_ad_account(db, org_id):
        return "act_demo"

    async def fake_require_writer(db, org_id):
        return _FakeWriter()

    async def fake_require_reader(db, org_id):
        crs = (
            creatives
            if creatives is not None
            else [
                CreativePreview(ad_id="ad-1", ad_name="A"),
                CreativePreview(ad_id="ad-2", ad_name="B"),
            ]
        )
        return _FakeReader(crs)

    monkeypatch.setattr(GeneratorReadClient, "get_candidate", fake_get_candidate)
    monkeypatch.setattr(management, "download_bytes", fake_download)
    monkeypatch.setattr(management, "_require_owned_campaign", fake_owned)
    monkeypatch.setattr(management, "_require_ad_account", fake_ad_account)
    monkeypatch.setattr(management, "_require_writer", fake_require_writer)
    monkeypatch.setattr(management, "_require_reader", fake_require_reader)
    monkeypatch.setattr(management, "_is_sending_mode", lambda: sending)

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())

    class _FakeDB:
        async def scalar(self, stmt, *a, **k):
            if "organization_members" in str(stmt):
                return uuid.uuid4()
            return None

    app.dependency_overrides[get_db] = lambda: _FakeDB()
    return TestClient(app), rec


def _body(**over):
    base = {"generation_id": "g1", "candidate_id": "c1", "link_url": "https://clickme.co.kr"}
    base.update(over)
    return base


def test_replace_creative_proposal_builds_tier3_with_creative_fields(monkeypatch):
    client, rec = _setup(monkeypatch)
    resp = client.post(_URL_TMPL.format(cid=_OWNED), json=_body())
    assert resp.status_code == 200, resp.text
    proposal = resp.json()["proposal"]
    assert proposal["action_type"] == "REPLACE_CREATIVE"
    assert proposal["action_tier"] == 3
    em = proposal["evidence_metrics"]
    assert em["headline"] and em["body"] and em["link_url"]
    assert em["generation_id"] == "g1" and em["candidate_id"] == "c1"
    preview = resp.json()["preview"]
    assert em["affected_ad_ids"]
    assert em["affected_ad_count"] == len(em["affected_ad_ids"]) == len(preview["affected_ads"])
    # org 전달 검증(리뷰 P2-a) — 라우터가 get_candidate(org_id=…)로 호출 org를 넘겼는지.
    assert rec.last_org_id is not None and rec.last_org_id != ""


def test_replace_creative_proposal_rejects_unowned_campaign(monkeypatch):
    client, _ = _setup(monkeypatch)
    resp = client.post(_URL_TMPL.format(cid=_OTHER), json=_body())
    assert resp.status_code in (403, 404)


def test_replace_creative_proposal_rejects_other_org_candidate(monkeypatch):
    # 후보-org 누출 차단(리뷰 ②) — 타 org generation은 generator org 스코프로 404.
    client, _ = _setup(monkeypatch)
    resp = client.post(_URL_TMPL.format(cid=_OWNED), json=_body(generation_id="other-org-gen"))
    assert resp.status_code == 404


def test_replace_creative_proposal_rejects_empty_candidate_copy(monkeypatch):
    # 후보 copy(body) 빈값이면 승인 후 집행 실패하므로 빌드 단계에서 422 거부(리뷰 P1-4).
    client, _ = _setup(monkeypatch, candidate=_cand(body=""))
    resp = client.post(_URL_TMPL.format(cid=_OWNED), json=_body())
    assert resp.status_code == 422


def test_replace_creative_proposal_409_when_no_ads(monkeypatch):
    # 캠페인에 ad가 없으면 교체 대상 없음 → 409.
    client, _ = _setup(monkeypatch, creatives=[])
    resp = client.post(_URL_TMPL.format(cid=_EMPTY), json=_body())
    assert resp.status_code == 409


def test_replace_creative_proposal_501_in_sending_mode(monkeypatch):
    # sending mode(validate/live)면 501 차단(B-1 mock 범위).
    client, _ = _setup(monkeypatch, sending=True)
    resp = client.post(_URL_TMPL.format(cid=_OWNED), json=_body())
    assert resp.status_code == 501


def test_replace_creative_proposal_preserves_existing_link_when_omitted(monkeypatch):
    # link_url 미전송 → 기존 광고의 도착지를 보존한다(소재만 교체, 도착지 유지).
    client, _ = _setup(
        monkeypatch,
        creatives=[
            CreativePreview(ad_id="ad-1", ad_name="A", link_url="https://shop.example.co.kr/keep"),
            CreativePreview(ad_id="ad-2", ad_name="B", link_url="https://shop.example.co.kr/keep"),
        ],
    )
    resp = client.post(
        _URL_TMPL.format(cid=_OWNED), json={"generation_id": "g1", "candidate_id": "c1"}
    )
    assert resp.status_code == 200, resp.text
    em = resp.json()["proposal"]["evidence_metrics"]
    assert em["link_url"] == "https://shop.example.co.kr/keep"


def test_replace_creative_proposal_422_when_no_link_and_omitted(monkeypatch):
    # 기존 링크도 없고 요청에도 없으면 도착지 결정 불가 → 422.
    client, _ = _setup(
        monkeypatch,
        creatives=[CreativePreview(ad_id="ad-1", ad_name="A")],
    )
    resp = client.post(
        _URL_TMPL.format(cid=_OWNED), json={"generation_id": "g1", "candidate_id": "c1"}
    )
    assert resp.status_code == 422
