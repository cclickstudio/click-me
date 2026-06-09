"""Ad Creator Agent — LangGraph 워크플로우 (7.8 목표)."""

from langgraph.graph import END, START, StateGraph

from agents.agent_ad_creator.nodes import generate_ad, run_debate, select_debate_personas, vote
from agents.agent_ad_creator.state import AdCreatorState

builder = StateGraph(AdCreatorState)

builder.add_node("select_debate_personas", select_debate_personas)
builder.add_node("run_debate", run_debate)
builder.add_node("vote", vote)
builder.add_node("generate_ad", generate_ad)

builder.add_edge(START, "select_debate_personas")
builder.add_edge("select_debate_personas", "run_debate")
builder.add_edge("run_debate", "vote")
builder.add_edge("vote", "generate_ad")
builder.add_edge("generate_ad", END)

creator_graph = builder.compile()
