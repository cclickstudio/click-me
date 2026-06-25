# chat_provider Literal 검증 — 잘못된 값은 설정 로드에서 거부(조용한 Gemini fallback 방지).
import pytest
from pydantic import ValidationError

from core.config import Settings


@pytest.mark.parametrize("value", ["gemini", "openai", "anthropic"])
def test_valid_chat_provider_accepted(value):
    assert Settings(chat_provider=value).chat_provider == value


@pytest.mark.parametrize("value", ["Anthropic", "OpenAI", "claude", "anthropic ", "", "gpt"])
def test_invalid_chat_provider_rejected_at_load(value):
    # 오타·대소문자·공백·미지원 값은 ValidationError로 시끄럽게 실패해야 한다.
    with pytest.raises(ValidationError):
        Settings(chat_provider=value)
