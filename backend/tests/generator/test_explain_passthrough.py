# explain 노드 — 선계산 패스스루 / 개수 불일치 방어 검증 (LLM 스텁)
"""candidate_gen이 이미지 생성과 병렬로 미리 만든 설명을 explain 노드가
LLM 재호출 없이 그대로 통과시키는지, 폴백 경로의 rationale 개수 정렬이 유지되는지 확인한다.
"""

from types import SimpleNamespace

from domain.generator.contracts.enums import TemplateType
from domain.generator.graph.nodes import explain


def _fake_batch_llm(rationales: list[str]) -> SimpleNamespace:
    async def _ainvoke(_messages):
        return SimpleNamespace(rationales=rationales)

    return SimpleNamespace(ainvoke=_ainvoke)


async def test_precomputed_explanations_pass_through_without_llm(monkeypatch):
    # 선계산 결과가 있으면 LLM을 부르지 않아야 한다 — 호출되면 즉시 실패하도록 스텁.
    def _boom(*_a, **_k):
        raise AssertionError("선계산이 있으면 explain LLM을 호출하면 안 된다")

    monkeypatch.setattr(explain, "_batch_llm", SimpleNamespace(ainvoke=_boom))

    pre = [
        {
            "applied_target": "t",
            "applied_strategy": "s",
            "applied_template": "tpl",
            "rationale": "r",
        }
    ]
    state = {"explanations": pre, "request": {}, "candidates": [], "qa_results": []}
    out = await explain.explain_candidates(state, {})
    assert out["explanations"] is pre


async def test_fallback_computes_when_no_precomputed(monkeypatch):
    monkeypatch.setattr(explain, "_batch_llm", _fake_batch_llm(["이유A", "이유B"]))
    state = {
        "request": {"product_name": "텀블러", "target_audience": "20대 직장인"},
        "candidates": [
            {
                "template_id": TemplateType.A.value,
                "strategy": {"strategy_description": "혜택 강조", "rationale": "r1"},
                "copy": {"headline": "h1"},
            },
            {
                "template_id": TemplateType.B.value,
                "strategy": {"strategy_description": "긴급성", "rationale": "r2"},
                "copy": {"headline": "h2"},
            },
        ],
        "qa_results": [{"overall_passed": True}, {"overall_passed": False}],
    }
    out = await explain.explain_candidates(state, {})
    assert [e["rationale"] for e in out["explanations"]] == ["이유A", "이유B"]


async def test_generate_explanations_aligns_when_llm_returns_fewer(monkeypatch):
    # LLM이 후보 수보다 적은 rationale을 반환해도 후보 수만큼 반환되어야 한다(개수 방어).
    monkeypatch.setattr(explain, "_batch_llm", _fake_batch_llm(["이유1"]))
    rows = [
        {
            "template": TemplateType.A,
            "strategy_description": "혜택",
            "rationale": "r1",
            "headline": "h1",
            "qa_passed": True,
        },
        {
            "template": TemplateType.B,
            "strategy_description": "긴급",
            "rationale": "r2",
            "headline": "h2",
            "qa_passed": False,
        },
    ]
    out = await explain.generate_explanations("제품", "20대", rows)
    assert len(out) == 2
    assert out[0]["rationale"] == "이유1"
    assert out[1]["rationale"]  # 부족분은 전략 설명/기본 문구로 채움
