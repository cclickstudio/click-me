# 오케스트레이터 — 의도분류 → 레지스트리 디스패치(결정론·단일 패스, 루프 없음)
"""1턴 = 1 처리. 최상위는 루프를 돌지 않는다(G5). 깊은 루프는 서브에이전트 안에만.

advise(폴백)는 등록 핸들러가 없으므로 (intent, None)을 돌려준다 — 호출자(chat 라우터)가
기존 CLIO 스트리밍으로 처리한다. 토큰 스트리밍 책임은 전송계층에 둔다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from api.assistant.contracts import Intent, ProjectRef, SubagentRequest, SubagentResult
from api.assistant.intent import classify_intent
from api.assistant.registry import SubagentRegistry

ProjectProvider = Callable[[], Awaitable[list[ProjectRef]]]


class Orchestrator:
    def __init__(self, registry: SubagentRegistry, classifier_llm=None) -> None:
        self.registry = registry
        self.classifier_llm = classifier_llm

    async def run_turn(
        self, req: SubagentRequest, *, project_provider: ProjectProvider | None = None
    ) -> tuple[Intent, SubagentResult | None]:
        # 개선 모드 컨텍스트가 있으면 의도분류 생략하고 generate로 직접 라우팅
        if req.improve_context and Intent.GENERATE in self.registry.intents:
            intent = Intent.GENERATE
        else:
            intent = await classify_intent(req, self.registry.intents, self.classifier_llm)
        handler = self.registry.get(intent)
        if handler is None:
            return intent, None  # advise/미등록 → 호출자가 폴백 처리

        # 생성은 저장 프로젝트가 필요 — 되묻기용 후보를 지연 조회해 주입
        if (
            intent == Intent.GENERATE
            and project_provider is not None
            and not req.project_id
            and not req.available_projects
        ):
            req.available_projects = await project_provider()

        result = await handler(req)
        return intent, result
