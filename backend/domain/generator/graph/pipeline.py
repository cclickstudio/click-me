"""광고 생성 LangGraph 파이프라인 — 생성모드 (계획서 9장).

사용자 입력 → 상품 분석 → 광고 전략 생성 → 템플릿 선택
→ 광고 후보 3종 생성 → 품질 검증 → 생성 이유 설명
(사용자 선택·S3 저장·결과 반환은 service 레이어에서 처리)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from domain.generator.graph.nodes.candidate_gen import generate_candidates
from domain.generator.graph.nodes.explain import explain_candidates
from domain.generator.graph.nodes.product_analysis import analyze_product
from domain.generator.graph.nodes.qa import run_qa
from domain.generator.graph.nodes.strategy import generate_strategies
from domain.generator.graph.nodes.template_select import select_templates
from domain.generator.graph.state import GenerationState


def build_generation_graph() -> CompiledStateGraph:
    graph = StateGraph(GenerationState)
    graph.add_node("analyze_product", analyze_product)
    graph.add_node("generate_strategies", generate_strategies)
    graph.add_node("select_templates", select_templates)
    graph.add_node("generate_candidates", generate_candidates)
    graph.add_node("run_qa", run_qa)
    graph.add_node("explain", explain_candidates)

    graph.set_entry_point("analyze_product")
    graph.add_edge("analyze_product", "generate_strategies")
    graph.add_edge("generate_strategies", "select_templates")
    graph.add_edge("select_templates", "generate_candidates")
    graph.add_edge("generate_candidates", "run_qa")
    graph.add_edge("run_qa", "explain")
    graph.add_edge("explain", END)
    return graph.compile()


generation_graph = build_generation_graph()
