"""★③ Composition Root — 어댑터를 포트에 꽂는 유일한 지점."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.management.contracts.platform import AdPlatformReader, AdPlatformWriter
    from domain.management.contracts.schemas import DiagnosisResult
    from domain.management.execution.audit_log import AuditSink
    from domain.management.execution.executor import IdempotencyStore


def build_reader(settings) -> AdPlatformReader:
    if getattr(settings, "use_mock", True):
        # 지연 import — MockAdPlatform(🅰 소유)은 A-1 구현 전까지 빈 stub
        from domain.management.adapters.mock import MockAdPlatform  # noqa: PLC0415

        return MockAdPlatform()
    from domain.management.adapters.meta.reader import MetaAdsReader  # noqa: PLC0415

    return MetaAdsReader(settings)


def build_writer(settings) -> AdPlatformWriter:
    # mock/데모 writer = DRY_RUN MetaAdsWriter (실제 쓰기 없이 계약만 검증).
    # MockAdPlatform은 reader 전용이라 writer Port를 만족하지 못함 — 분기에서 제외.
    from domain.management.adapters.meta.writer import MetaAdsWriter  # noqa: PLC0415

    if getattr(settings, "use_mock", True):
        from domain.management.contracts.enums import ExecutionMode  # noqa: PLC0415

        return MetaAdsWriter(settings, mode=ExecutionMode.DRY_RUN)
    return MetaAdsWriter(settings)


def build_diagnosis_agent(settings):
    """진단 LLM ReAct 러너 — ``async (prior, reader) -> DiagnosisResult``.

    use_mock(데모) 또는 키 없음이면 결정론 폴백(prior 그대로) — 게이트 #9(키 없이 재현) 유지.
    실모드 + 키면 INCONCLUSIVE 진단을 LLM이 메타 신호 tool로 재판정한다(P6 고정값 주입).
    """
    api_key = getattr(settings, "openai_api_key", None)
    if getattr(settings, "use_mock", True) or not api_key:

        async def _passthrough(prior: DiagnosisResult, _reader) -> DiagnosisResult:
            return prior

        return _passthrough

    model = getattr(settings, "management_diagnosis_model", "gpt-4o-mini")
    temperature = getattr(settings, "management_diagnosis_temperature", 0.0)

    async def _run(prior: DiagnosisResult, reader) -> DiagnosisResult:
        from domain.management.agents.diagnosis_llm import run_llm_diagnosis  # noqa: PLC0415

        return await run_llm_diagnosis(
            prior, reader, model=model, temperature=temperature, api_key=api_key
        )

    return _run


def build_organic_reader(settings):
    """🅰 오가닉 인사이트 reader (OrganicInsightsReader) — use_mock 분기."""
    if getattr(settings, "use_mock", True):
        from domain.management.adapters.mock import MockOrganicReader  # noqa: PLC0415

        return MockOrganicReader()
    from domain.management.adapters.meta.organic_reader import MetaOrganicReader  # noqa: PLC0415

    return MetaOrganicReader(settings)


def build_comparison_service(settings):
    """🅰 오가닉↔광고 비교 서비스 — organic reader + ad reader 합성."""
    from domain.management.comparison.service.comparison_service import (  # noqa: PLC0415
        ComparisonService,
    )

    return ComparisonService(build_organic_reader(settings), build_reader(settings))


def build_prediction_reader(settings):
    """집행 전(시뮬 예측) reader — 시뮬 디커플링 슬롯의 교체 지점.

    지금은 MockPredictionReader. 시뮬 KPI 안정화 후 이 줄만 SimPredictionReader로 바꾸면
    compare 화면·API 변경 없이 실 예측이 들어온다.
    """
    from domain.management.comparison.prediction_adapters import (  # noqa: PLC0415
        MockPredictionReader,
    )

    return MockPredictionReader()


def build_idempotency_store(settings) -> IdempotencyStore:
    """멱등 저장소 — use_mock이면 인메모리, 아니면 DB(idempotency_keys)."""
    if getattr(settings, "use_mock", True):
        from domain.management.execution.executor import (  # noqa: PLC0415
            InMemoryIdempotencyStore,
        )

        return InMemoryIdempotencyStore()
    from domain.management.execution.db_stores import DbIdempotencyStore  # noqa: PLC0415

    return DbIdempotencyStore()


def build_audit_sink(settings) -> AuditSink:
    """감사 sink — use_mock이면 인메모리, 아니면 DB(audit_events)."""
    if getattr(settings, "use_mock", True):
        from domain.management.execution.audit_log import InMemoryAuditLog  # noqa: PLC0415

        return InMemoryAuditLog()
    from domain.management.execution.db_stores import DbAuditSink  # noqa: PLC0415

    return DbAuditSink()


def build_checkpointer(settings):
    """어시스턴트 ReAct 그래프의 checkpointer — interrupt(HITL) 재개에 필요.

    1차는 인메모리(MemorySaver). Neon 영속(AsyncPostgresSaver)은 후속 — 이 분기만 바꾸면
    interrupt로 멈춘 그래프가 프로세스 재시작 후에도 재개된다.
    """
    from langgraph.checkpoint.memory import MemorySaver  # noqa: PLC0415

    return MemorySaver()


def build_escalation_store(settings):
    """에스컬레이션 사다리 저장소. 현재는 인메모리(데모·use_mock).

    DB 영속(remediation_escalations 테이블·마이그레이션 008)은 준비돼 있으며, DbEscalationStore
    구현 시 use_mock=False 분기를 여기 추가한다(후속). 그 전까지는 인메모리로 데모가 성립한다.
    """
    from domain.management.escalation import InMemoryEscalationStore  # noqa: PLC0415

    return InMemoryEscalationStore()


def build_generator_client(settings):
    """generator D1 계약 HTTP 클라이언트 — base_url은 internal_api_base_url."""
    from domain.management.adapters.generator.client import GeneratorReadClient  # noqa: PLC0415

    base = getattr(settings, "internal_api_base_url", "http://localhost:8000")
    return GeneratorReadClient(base_url=base)
