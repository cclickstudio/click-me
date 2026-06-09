"""Ad Management Agent — LangGraph 워크플로우."""

from langgraph.graph import END, START, StateGraph

from agents.agent_ad_management.nodes import dispatch_to_platforms, record_result, validate_ad
from agents.agent_ad_management.state import ManagementState

builder = StateGraph(ManagementState)

builder.add_node("validate_ad", validate_ad)
builder.add_node("dispatch_to_platforms", dispatch_to_platforms)
builder.add_node("record_result", record_result)

builder.add_edge(START, "validate_ad")
builder.add_edge("validate_ad", "dispatch_to_platforms")
builder.add_edge("dispatch_to_platforms", "record_result")
builder.add_edge("record_result", END)

management_graph = builder.compile()
