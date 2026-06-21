# 챗봇 에이전트 — LLM으로 의도 판단·필드 추출·응답 생성
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.config import settings

logger = logging.getLogger("clickme")

_REQUIRED = ("product_name", "product_description", "target_audience")

_SYSTEM_TMPL = """\
당신은 광고 생성 도우미입니다. 사용자와 대화를 통해 광고 생성에 필요한 정보를 수집합니다.

## 광고 생성 필수 정보
1. product_name — 상품/서비스 이름
2. product_description — 상품 설명, 특징, 강조할 점
3. target_audience — 타겟 고객층

## 선택 정보
- campaign_objective — 목표 (예: "conversion", "awareness", "traffic")
- tone_and_manner — 광고 분위기·톤 (예: "활기차고 젊은", "고급스럽고 차분한")
- brand_color — 브랜드 색상 (예: "파란 계열", "빨간색", "#FF0000")

## 현재 수집된 정보
{partial_request}

## 아직 필요한 필수 정보
{missing}

## 행동 지침
- 사용자 메시지에서 위 필드에 해당하는 정보를 추출한다.
- 미수집 필수 정보가 있으면 한 가지씩만 물어본다.
- 필수 3개가 모두 수집되면, 수집된 내용을 한 줄로 요약하고 생성 확인을 요청한다.
- 사용자가 생성을 확정("네", "이대로", "만들어줘", "시작해줘", "좋아요" 등)하면 ready_to_generate를 true로 설정한다.
- 광고/마케팅 관련 일반 질문에는 1~2문장으로만 답변한다.

## 응답 길이 규칙 (엄수)
- response는 **최대 2문장**, **60자 이내**로 작성한다.
- 자기소개·역할 설명·부연 설명 없음. 질문이나 확인 한 가지만.

## 응답 형식 — 반드시 유효한 JSON만 출력, 다른 텍스트 없음
{{
  "extracted": {{
    "product_name": null,
    "product_description": null,
    "target_audience": null,
    "campaign_objective": null,
    "tone_and_manner": null,
    "brand_color": null
  }},
  "ready_to_generate": false,
  "response": "사용자에게 보낼 한국어 답변 (2문장 이내, 60자 이내, 마침표로 종료)"
}}

## 주의사항
- extracted: 이번 메시지에서 새로 파악된 값만 채운다. 없으면 null.
- ready_to_generate: 필수 3개가 모두 있고 사용자가 명시적으로 생성을 확정했을 때만 true.
"""


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.generator_chat_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
        max_tokens=200,
    )


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출 — 마크다운 코드블록 제거 포함."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


async def run_agent(messages: list[dict], partial_request: dict) -> dict:
    """대화 이력 + partial_request → LLM 판단 결과 반환.

    반환: {extracted, ready_to_generate, response}
    """
    missing = [f for f in _REQUIRED if not (partial_request.get(f) or "").strip()]

    system_content = _SYSTEM_TMPL.format(
        partial_request=(
            json.dumps(partial_request, ensure_ascii=False, indent=2) if partial_request else "없음"
        ),
        missing=", ".join(missing) if missing else "없음 (모두 수집됨)",
    )

    lc_messages: list = [SystemMessage(content=system_content)]
    for msg in messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        else:
            lc_messages.append(AIMessage(content=msg["content"]))

    llm = _build_llm()
    ai_msg = await llm.ainvoke(lc_messages)
    raw = ai_msg.content if isinstance(ai_msg.content, str) else ""

    try:
        return _parse_json(raw)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("챗봇 에이전트 JSON 파싱 실패: %s", raw[:200])
        return {
            "extracted": {},
            "ready_to_generate": False,
            "response": raw or "죄송해요, 다시 말씀해 주세요.",
        }
