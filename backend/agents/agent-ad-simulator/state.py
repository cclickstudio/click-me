"""Ad Simulator Agent — LangGraph 상태 정의."""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class OceanProfile(TypedDict):
    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float


class Persona(TypedDict):
    id: str
    ocean: OceanProfile
    demographics: dict       # age, gender, income, region 등
    psychographics: dict     # 가치관, 라이프스타일


class PersonaResponse(TypedDict):
    persona_id: str
    exposure_reaction: str   # Exposure Agent 결과
    deliberation: str        # Deliberation Agent 결과
    purchase_intent_score: float  # SSR Scorer 결과 (0.0 ~ 1.0)


class SimulatorState(TypedDict):
    ad_id: str
    ad_content: dict         # Ad Understanding Agent 분석 결과
    personas: list[Persona]
    responses: Annotated[list[PersonaResponse], lambda a, b: a + b]
    distribution: dict       # 최종 구매의향 분포
    messages: Annotated[list, add_messages]
