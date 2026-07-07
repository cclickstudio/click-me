# PDF 다운로드 엔드포인트 스모크 — 라우터→render_report_pdf(Windows subprocess)→PDF Response 검증
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import debate as debate_router
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    Persona,
    PersonaReaction,
    RubricScore,
)
from domain.simulation.tools.aggregation.aggregator import BasicAggregator
from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.kpi import build_topic
from domain.simulation.tools.debate.report import build_report, build_report_view

_AD = AdInterpretation(
    ad_id="ad-1", detected_message="제로슈거 신제품", detected_industry="beverage"
)


def _result() -> dict:
    personas, reactions = [], []
    for i in range(6):
        pid = f"P{i}"
        personas.append(
            Persona(
                persona_id=pid,
                age=25 + (i % 3) * 10,
                gender="male" if i % 2 == 0 else "female",
                region="Seoul",
                ocean={"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            )
        )
        reactions.append(
            PersonaReaction(
                persona_id=pid,
                aisas=Aisas(attention=True, interest=i % 2 == 0, action=i % 3 == 0),
                purchase_intent=(i % 5) + 1,
                trust=4,
                brand_recognized=i % 2 == 0,
                rejected=i % 4 == 0,
                emotion_tag="curiosity",
            )
        )
    analysis = analyze_reactions(reactions, _AD)
    aggregate = BasicAggregator().aggregate(reactions)
    topic = build_topic(analysis, aggregate, _AD)
    report = build_report(
        analysis,
        aggregate,
        topic,
        None,
        [RubricScore(dimension="cta_clarity", score=41, evidence={})],
    )
    view = build_report_view(
        run_id="run-1",
        simulation_id="sim-1",
        debate_id=None,
        report=report,
        objective_fit=None,
        ad_analysis=_AD,
        ad=None,
        topic=topic,
        debate=None,
        aggregate=aggregate,
        analysis=analysis,
        personas=personas,
        reactions=reactions,
        generated_at="2026-07-07T00:00:00Z",
    )
    return {"run_id": "run-1", "report_view": view.model_dump(mode="json")}


def test_report_pdf_endpoint_returns_pdf(monkeypatch) -> None:
    """GET /{run_id}/report.pdf → 실제 PDF 바이트를 attachment로 응답.

    Windows에서는 render_report_pdf가 별도 Proactor 프로세스(subprocess)로 렌더한다 —
    이 테스트가 그 HTTP 경로(to_thread→subprocess→Response)를 그대로 통과시킨다.
    """
    monkeypatch.setattr(debate_router._service, "get_result", lambda rid: _result())

    app = FastAPI()
    app.include_router(debate_router.router, prefix="/api/debate")
    client = TestClient(app)

    resp = client.get("/api/debate/run-1/report.pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 1500
