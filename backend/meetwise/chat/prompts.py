"""Prompts for the chat agent. Each user prompt starts with a 'TASK:' line."""

from __future__ import annotations

CHAT_SYSTEM = (
    "You are MeetWise's assistant. You answer questions about the user's meetings, commitments and "
    "decisions using only the sources you are given. You never invent meeting details, dates, owners "
    "or task statuses. If the sources do not answer the question, say so plainly. "
    "Respond with exactly one JSON object and nothing else."
)


def plan_prompt(question: str, today: str, scope_text: str, history: str) -> str:
    return f"""TASK: chat_plan
Today: {today}
Search scope: {scope_text}
Recent conversation:
{history or 'none'}

Question: {question}

Return JSON:
{{"search_query": "concise search query. Rewrite follow-ups such as 'what about him?' using the conversation.",
"date_from": "YYYY-MM-DD or null",
"date_to": "YYYY-MM-DD or null",
"participants": ["names the question filters on, or empty"],
"content_types": ["subset of transcript, summary, action_item, decision, unresolved_issue, event; empty means all"],
"include_tasks": true if the question concerns tasks, commitments, owners, deadlines, status or blockers,
"task_scope": "mine (the user's own), team, dependencies, or all"}}
Resolve relative dates such as 'last month' against today's date. Use null when no date range is implied."""


def answer_prompt(
    question: str, today: str, history: str, sources_block: str, feedback: str | None
) -> str:
    retry = (
        f"\nYour previous draft failed these checks. Fix them: {feedback}\n"
        if feedback
        else ""
    )
    return f"""TASK: chat_answer
Today: {today}
Recent conversation:
{history or 'none'}

Question: {question}

Sources:
{sources_block}
{retry}
Rules:
- Use only the sources above. Cite each factual claim inline with its label, for example [S2].
- Cite only labels that appear above.
- If you draw a conclusion the sources do not state outright, set evidence_status to "inferred" and say so in the answer.
- For task status and deadlines, state what the sources record, with the meeting date. If a later source changed it, say so.
- If the sources do not answer the question, set evidence_status to "insufficient" and describe what is missing.
- Be concise: under 150 words. Use a short list only for three or more items.

Return JSON: {{"answer": "...", "used_sources": ["S1"], "evidence_status": "confirmed|inferred|insufficient", "missing": "what is missing, or null"}}"""
