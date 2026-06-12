"""파이프라인 그래프 토폴로지 테스트 (LLM 호출 없음)."""

from domain.generator.graph.pipeline import generation_graph

EXPECTED_ORDER = [
    "analyze_product",
    "generate_strategies",
    "select_templates",
    "generate_candidates",
    "run_qa",
    "explain",
]


def test_pipeline_has_all_nodes():
    nodes = set(generation_graph.get_graph().nodes)
    assert set(EXPECTED_ORDER) <= nodes


def test_pipeline_edges_are_sequential():
    edges = {(e.source, e.target) for e in generation_graph.get_graph().edges}
    for src, dst in zip(EXPECTED_ORDER, EXPECTED_ORDER[1:], strict=False):
        assert (src, dst) in edges, f"{src} → {dst} 엣지 누락"
