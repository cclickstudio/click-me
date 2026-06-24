# 챗/임베딩 설정 키가 기본값과 함께 존재하는지 검증(hermetic).
from core.config import settings


def test_embedding_settings_defaults():
    assert settings.embedding_provider == "bge_m3"
    assert settings.embedding_dim == 1024
    assert settings.embedding_model == "bge-m3"


def test_chat_orchestrator_settings_defaults():
    assert settings.chat_orchestrator_provider == "anthropic"
    assert settings.chat_orchestrator_model == "claude-sonnet-4-6"
