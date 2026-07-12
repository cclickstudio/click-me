"""★③ Composition Root — 어댑터를 포트에 꽂는 유일한 지점."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.management.contracts.approval_ledger import ApprovalStore
    from domain.management.contracts.platform import AdPlatformReader, AdPlatformWriter
    from domain.management.contracts.schemas import DiagnosisResult
    from domain.management.execution.audit_log import AuditSink
    from domain.management.execution.executor import IdempotencyStore


def build_reader(settings) -> AdPlatformReader:
    # management_reader_mock: 매니지먼트 reader만 mock 강제(알림 데모용) — 전역 use_mock과
    # 분리해 채팅(mock이면 에이전트 비활성, deep_agent_builder 참조)을 live로 유지한다.
    if getattr(settings, "use_mock", True) or getattr(settings, "management_reader_mock", False):
        # 지연 import — MockAdPlatform(🅰 소유)은 A-1 구현 전까지 빈 stub
        from domain.management.adapters.mock import MockAdPlatform  # noqa: PLC0415

        return MockAdPlatform()
    from domain.management.adapters.meta.reader import MetaAdsReader  # noqa: PLC0415

    return MetaAdsReader(settings)


def build_writer(settings) -> AdPlatformWriter:
    # mock/데모 writer = DemoBudgetWriter(DRY_RUN MetaAdsWriter) — 실전송 없이 계약만 검증하되,
    # adjust_budget 성공 시 demo_store 예산을 갱신해 "적용 → 새로고침 시 예산 이동"이 mock에서
    # 완결된다. (MockAdPlatform은 reader 전용이라 writer Port를 만족하지 못함 — 분기에서 제외.)
    from domain.management.adapters.meta.writer import MetaAdsWriter  # noqa: PLC0415

    if getattr(settings, "use_mock", True):
        from domain.management.adapters.demo_store import DemoBudgetWriter  # noqa: PLC0415
        from domain.management.contracts.enums import ExecutionMode  # noqa: PLC0415

        return DemoBudgetWriter(MetaAdsWriter(settings, mode=ExecutionMode.DRY_RUN))
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
    """집행 전(시뮬 예측) reader — simulation_aggregates를 raw SQL로 읽는 SimPredictionReader.

    실데이터가 있으면 실 예측, 없으면 None(연결 대기). 데모/단위 테스트는 MockPredictionReader를
    직접 주입해 사용(가짜 예측 합성은 테스트 전용 — 운영은 합성 금지).
    """
    from core.db import AsyncSessionLocal  # noqa: PLC0415
    from domain.management.comparison.prediction_adapters import (  # noqa: PLC0415
        SimPredictionReader,
    )

    return SimPredictionReader(AsyncSessionLocal)


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


_approval_store: ApprovalStore | None = None


def build_approval_store(settings) -> ApprovalStore:
    """승인 원장 — 발행부(라우터)와 executor가 같은 인스턴스를 봐야 하므로 싱글턴.

    use_mock이면 인메모리(단일 프로세스 전제 — 멀티워커면 /approve와 /execute가
    서로 다른 dict를 봐 위조로 오거부된다. 멀티워커는 use_mock=False=DB로), 아니면 DB.
    """
    global _approval_store  # noqa: PLW0603
    if _approval_store is None:
        if getattr(settings, "use_mock", True):
            from domain.management.execution.approval_stores import (  # noqa: PLC0415
                InMemoryApprovalStore,
            )

            _approval_store = InMemoryApprovalStore()
        else:
            from domain.management.execution.db_stores import DbApprovalStore  # noqa: PLC0415

            _approval_store = DbApprovalStore()
    return _approval_store


def build_checkpointer(settings):
    """어시스턴트 ReAct 그래프의 checkpointer — interrupt(HITL)·멀티턴 재개에 필요.

    앱 시작 시 init_pg_checkpointer가 성공했으면 Neon 영속(AsyncPostgresSaver) 싱글턴을,
    아니면 인메모리(MemorySaver)로 폴백한다. (영속 = 재시작 후에도 같은 thread로 재개)
    """
    from domain.management.assistant.checkpointer import get_pg_checkpointer  # noqa: PLC0415

    saver = get_pg_checkpointer()
    if saver is not None:
        return saver
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
    token = getattr(settings, "internal_service_token", None)
    return GeneratorReadClient(base_url=base, internal_token=token)


# ── 실행 모드·state version 정본 — 라우터 _resolved_execution_mode·executor 조립이 사용 ──────


def resolve_execution_mode(settings):
    """settings 기반 실행 모드 정본 — 라우터 _resolved_execution_mode가 이 함수에 위임.

    use_mock이면 무조건 MOCK(봉인). 실모드에서만 management_execution_mode를 따른다.
    DRY_RUN을 폴백으로 사용한다.
    """
    from domain.management.contracts.enums import ExecutionMode  # noqa: PLC0415

    if getattr(settings, "use_mock", True):
        return ExecutionMode.MOCK
    raw = getattr(settings, "management_execution_mode", "dry_run")
    try:
        return ExecutionMode(raw)
    except ValueError:
        return ExecutionMode.DRY_RUN


async def state_version_v1(_ad_account_id: str) -> str:
    """데모 고정 상태 버전 provider — 제안의 expected_state_version="state_v1"과 일치."""
    return "state_v1"
