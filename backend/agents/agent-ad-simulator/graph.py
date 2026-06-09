"""Ad Simulator Agent — LangGraph 워크플로우."""

from langgraph.graph import END, START, StateGraph

from agents.agent_ad_simulator.nodes import (
    build_distribution,
    generate_personas,
    run_deliberation,
    run_exposure,
    score_with_ssr,
)
from agents.agent_ad_simulator.state import SimulatorState

builder = StateGraph(SimulatorState)

builder.add_node("generate_personas", generate_personas)
builder.add_node("run_exposure", run_exposure)
builder.add_node("run_deliberation", run_deliberation)
builder.add_node("score_with_ssr", score_with_ssr)
builder.add_node("build_distribution", build_distribution)

builder.add_edge(START, "generate_personas")
builder.add_edge("generate_personas", "run_exposure")
builder.add_edge("run_exposure", "run_deliberation")
builder.add_edge("run_deliberation", "score_with_ssr")
builder.add_edge("score_with_ssr", "build_distribution")
builder.add_edge("build_distribution", END)

simulator_graph = builder.compile()
