# 도메인 에이전트 레지스트리 — domain 문자열 → DomainAgent
from __future__ import annotations

from api.orchestration.contracts import DomainAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, DomainAgent] = {}

    def register(self, agent: DomainAgent) -> None:
        if agent.domain in self._agents:  # 중복 등록은 조용히 덮지 말고 명시적 실패
            raise ValueError(f"중복 도메인 등록: {agent.domain}")
        self._agents[agent.domain] = agent

    def get(self, domain: str) -> DomainAgent | None:
        return self._agents.get(domain)
