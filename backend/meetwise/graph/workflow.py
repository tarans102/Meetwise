"""Assembles the LangGraph StateGraph for meeting processing.

Flow:
  preprocess -> metadata -> summarize -> segment -> decisions -> events
             -> extract_actions -> attribute -> verify
                                              |-- unsupported & attempts left --> extract_actions
                                              |-- otherwise --> persist -> END
"""

from __future__ import annotations

from meetwise.graph.nodes import PipelineNodes
from meetwise.graph.state import MeetingState

CHAIN = [
    "preprocess",
    "metadata",
    "summarize",
    "segment",
    "extract_decisions",
    "extract_events",
    "extract_actions",
    "attribute",
    "verify",
]


def build_graph(nodes: PipelineNodes):
    """Compile the workflow. Requires the `langgraph` package."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(MeetingState)
    for name in CHAIN + ["persist"]:
        graph.add_node(name, nodes.node(name, getattr(nodes, name)))

    graph.set_entry_point(CHAIN[0])
    for source, target in zip(CHAIN, CHAIN[1:]):
        graph.add_edge(source, target)
    graph.add_conditional_edges(
        "verify",
        nodes.route_after_verify,
        {"extract_actions": "extract_actions", "persist": "persist"},
    )
    graph.add_edge("persist", END)
    return graph.compile()
