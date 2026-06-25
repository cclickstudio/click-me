# 챗/임베딩 설정 키의 선언 기본값 검증 — hermetic(.env/env 무관, model_fields 검사).
from core.config import Settings

_F = Settings.model_fields


def test_embedding_settings_defaults():
    assert _F["embedding_provider"].default == "bge_m3"
    assert _F["embedding_dim"].default == 1024
    assert _F["embedding_model"].default == "bge-m3"


def test_chat_orchestrator_settings_defaults():
    assert _F["chat_orchestrator_provider"].default == "anthropic"
    assert _F["chat_orchestrator_model"].default == "claude-sonnet-4-6"
