# ChatRequest.attachments(s3_key) 멀티모달 계약 — append-only, 기본 빈 리스트
from core.schemas import Attachment, ChatRequest


def test_attachment_defaults_to_image_kind():
    a = Attachment(s3_key="uploads/p.png")
    assert a.s3_key == "uploads/p.png"
    assert a.kind == "image"


def test_chat_request_attachments_default_empty():
    req = ChatRequest(session_id="s1", messages=[])
    assert req.attachments == []


def test_chat_request_accepts_attachments():
    req = ChatRequest(
        session_id="s1",
        messages=[],
        attachments=[{"s3_key": "uploads/p.png", "kind": "image"}],
    )
    assert req.attachments[0].s3_key == "uploads/p.png"
    assert req.attachments[0].kind == "image"
