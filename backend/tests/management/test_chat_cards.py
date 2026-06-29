# 카드 계약 모델·레지스트리·순수성(AST import-0) 검증
import ast
import pathlib

import pytest

from domain.management.assistant.chat_cards import (
    Card,
    CardKind,
    CardPayload,
    CardStatus,
    TurnEnvelope,
    TurnOrigin,
    is_registered,
    validate_card,
)


def test_envelope_defaults_origin_user():
    env = TurnEnvelope(turn_id="t1", conclusion="요약")
    assert env.origin == TurnOrigin.USER
    assert env.trigger is None
    assert env.read_state is None
    assert env.cards == []


def test_card_default_status_ok():
    card = Card(kind=CardKind.EVIDENCE, payload=CardPayload(type="rag_citations", version=1))
    assert card.status == CardStatus.OK


def test_registry_known_types_registered():
    assert is_registered(CardKind.RESULT, "action_proposal", 1)
    assert is_registered(CardKind.REVIEW, "policy_check", 1)
    assert is_registered(CardKind.ACTIONBAR, "actions", 1)
    assert is_registered(CardKind.EVIDENCE, "rag_citations", 1)


def test_registry_rejects_unknown_type_and_version():
    assert not is_registered(CardKind.RESULT, "kpi_distribution", 1)  # B 단계, 미등록
    assert not is_registered(CardKind.RESULT, "action_proposal", 2)  # 미등록 버전


def test_validate_card_raises_on_unregistered():
    bad = Card(kind=CardKind.RESULT, payload=CardPayload(type="nope", version=1))
    with pytest.raises(ValueError, match="unregistered card"):
        validate_card(bad)


def _scan_offenders(source: str, filename: str = "<string>") -> list[tuple[str, str]]:
    """source 코드에서 management 내부 import 위반을 반환하는 순수 헬퍼."""
    allowed = "domain.management.assistant.chat_cards"
    offenders: list[tuple[str, str]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("domain.management") and not a.name.startswith(allowed):
                    offenders.append((filename, a.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level >= 2:
                # 패키지 밖(.. 이상)으로 나가는 상대 import 금지 — from ..contracts 등 차단
                offenders.append((filename, f"relative level={node.level} module={node.module}"))
            elif node.level == 1:
                continue  # 자기 패키지 내부(.models/.registry/.) 허용
            elif node.level == 0 and node.module == "domain":
                # `from domain import management` 형태 차단
                for alias in node.names:
                    if alias.name == "management":
                        offenders.append((filename, "from domain import management"))
            elif (
                node.module
                and node.module.startswith("domain.management")
                and not node.module.startswith(allowed)
            ):
                offenders.append((filename, node.module))
    return offenders


def test_chat_cards_is_pure_no_management_imports():
    # AST 정적 검사 — chat_cards는 자기 패키지(.models/.registry, level==1)만 상대 import.
    # level>=2 상대 import(.. 이상)와 chat_cards 외 절대 management import는 금지.
    import domain.management.assistant.chat_cards as pkg

    pkg_dir = pathlib.Path(pkg.__file__).parent
    offenders: list[tuple[str, str]] = []
    for py in sorted(pkg_dir.glob("*.py")):
        offenders.extend(_scan_offenders(py.read_text(encoding="utf-8"), py.name))
    assert offenders == [], f"chat_cards must not import management internals: {offenders}"


def test_scan_offenders_catches_from_domain_import_management():
    # `from domain import management` 형태가 사각지대 없이 탐지되는지 확인하는 단위 테스트.
    source = "from domain import management"
    offenders = _scan_offenders(source, "fake.py")
    assert offenders == [("fake.py", "from domain import management")]
