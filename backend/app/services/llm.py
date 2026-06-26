from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings


SYSTEM_PROMPT = """You are Issa Insight, a senior business analytics agent for Issa's internal team.
You turn natural-language business questions into safe Postgres SELECT queries and concise business diagnoses.

Rules:
- Use only tables and columns provided in the schema context.
- Join conversations to messages with contact_id when message-level timing or content is needed.
- conversation_opened_at is the preferred conversation start timestamp. Fall back to conversations.created_at when needed.
- Use channel_name or channel_source for channel breakdowns.
- Use dashboard_assignee_name or assignee_name for team member breakdowns.
- Use contact_status, lifecycle, current_step, blocked, is_handed_off, and is_qualified for funnel/status diagnostics.
- Use messages.direction to distinguish incoming vs outgoing response behavior.
- Never select raw message text or contact email/phone unless the user explicitly asks for a client/contact list.
- Generate only read-only SELECT/WITH SQL.
- Prefer clear business metrics over clever SQL.
- For direct questions, create one strong query.
- For investigations, decompose into 2-4 sub-queries that test likely drivers.
- Keep result sets compact. Add limits for tables/lists.
- Return JSON only. No markdown.
- Supported visualization values: line, bar, table, metric.
"""


PLAN_SCHEMA_HINT = """
Return this JSON shape:
{
  "mode": "direct" | "investigation",
  "title": "short answer title",
  "plan": [
    {
      "title": "step/query title",
      "rationale": "why this query matters",
      "visualization": "line" | "bar" | "table" | "metric",
      "sql": "SELECT ..."
    }
  ]
}
"""


INVESTIGATION_PLAYBOOKS = """
Investigation playbooks:

New client decline:
- weekly/monthly new conversations using conversation_opened_at
- unique contact starts
- channel_name/channel_source mix
- qualified rate using is_qualified
- AI eligibility/disabled rates using ai_eligible, ai_disabled
- assignee coverage using dashboard_assignee_name/assignee_name
- first-response pressure from incoming to outgoing messages

Team demand:
- active backlog by assignee
- incoming vs outgoing message volume
- unanswered incoming messages over 24 hours
- blocked, handed-off, and AI-disabled rates
- current_step/lifecycle bottlenecks

Client risk/churn:
- stale latest message or updated_at
- high incoming count with low outgoing count
- blocked or emergency conversations
- unassigned conversations
- current_step or lifecycle stuck states
- AI disabled / no reply needed flags

Unusual patterns:
- current month-to-date vs previous month-to-date
- last 30 days vs prior 30 days by channel/source
- sudden changes in qualified rate
- sudden changes in response gaps
- operational friction: blocked, handed off, AI disabled
"""


def has_llm() -> bool:
    return bool(get_settings().openai_api_key)


def create_plan(question: str, schema_context: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    history_context = _history_context(history or [])
    prompt = f"""
Question:
{question}

Recent conversation context:
{history_context}

Schema context:
{schema_context}

{INVESTIGATION_PLAYBOOKS}

{PLAN_SCHEMA_HINT}
"""
    return _json_response(prompt)


def repair_sql(question: str, schema_context: str, bad_sql: str, error: str) -> str:
    prompt = f"""
The SQL below failed. Rewrite only this SQL so it answers the user's question and fits the schema.

Question:
{question}

Schema context:
{schema_context}

Failed SQL:
{bad_sql}

Database error:
{error}

Return this JSON shape only:
{{"sql": "SELECT ..."}}
"""
    return str(_json_response(prompt).get("sql", "")).strip()


def synthesize_answer(question: str, plan: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    compact_results = [
        {
            "title": item["title"],
            "row_count": len(item.get("rows", [])),
            "sample_rows": item.get("rows", [])[:12],
        }
        for item in results
    ]
    prompt = f"""
Question:
{question}

Plan:
{json.dumps(plan, default=str)}

Query results:
{json.dumps(compact_results, default=str)}

Write a concise business diagnosis in 2-4 sentences. Be specific about what moved, where the signal is concentrated, and what the team should inspect next. If data is thin or inconclusive, say so plainly.

Return this JSON shape only:
{{
  "diagnosis": "...",
  "confidence": "High" | "Medium" | "Low",
  "caveats": ["..."],
  "recommended_actions": ["..."]
}}
"""
    response = _json_response(prompt)
    return {
        "diagnosis": str(response.get("diagnosis", "")).strip(),
        "confidence": str(response.get("confidence", "Medium")).strip() or "Medium",
        "caveats": _string_list(response.get("caveats")),
        "recommended_actions": _string_list(response.get("recommended_actions")),
    }


def _json_response(prompt: str) -> dict[str, Any]:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        text={"format": {"type": "json_object"}},
    )
    raw = getattr(response, "output_text", "") or ""
    if not raw:
        raw = _extract_text(response.model_dump())
    return json.loads(raw)


def _extract_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _history_context(history: list[dict[str, Any]]) -> str:
    if not history:
        return "No prior context."
    compact = []
    for item in history[-4:]:
        compact.append(
            {
                "question": item.get("question"),
                "title": item.get("title"),
                "diagnosis": item.get("diagnosis"),
            }
        )
    return json.dumps(compact, default=str)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:5]
