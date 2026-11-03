"""LangGraph wiring for the chat agent.

plan -> retrieve -> grade --(no evidence)--> finalize
                          --(evidence)----> answer -> verify --(problems, retries left)--> answer
                                                             --(otherwise)-------------> finalize -> END
"""

from __future__ import annotations

from meetwise.chat.nodes import ChatNodes
from meetwise.chat.state import ChatState


def build_chat_graph(nodes: ChatNodes):
    """Compile the chat workflow. Requires the `langgraph` package."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(ChatState)
    for name in ["plan", "retrieve", "grade", "answer", "verify", "finalize"]:
        graph.add_node(name, getattr(nodes, name))
    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade", nodes.route_after_grade, {"answer": "answer", "finalize": "finalize"}
    )
    graph.add_edge("answer", "verify")
    graph.add_conditional_edges(
        "verify", nodes.route_after_verify, {"answer": "answer", "finalize": "finalize"}
    )
    graph.add_edge("finalize", END)
    return graph.compile()
