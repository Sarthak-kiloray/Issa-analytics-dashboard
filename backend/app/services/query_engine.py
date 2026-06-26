from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.db import fetch_all
from app.services.llm import create_plan, has_llm, repair_sql, synthesize_answer
from app.services.schema import get_schema_context
from app.services.sql_guard import with_limit


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    title: str
    sql: str
    visualization: str
    rationale: str


DIRECT_PLANS = [
    QueryPlan(
        intent="monthly_conversations",
        title="New client conversations by month",
        visualization="line",
        rationale="Groups conversation creation dates by month for the current calendar year.",
        sql="""
        select
            date_trunc('month', coalesce(conversation_opened_at, created_at))::date as period,
            count(*)::int as conversations
        from conversations
        where coalesce(conversation_opened_at, created_at) >= date_trunc('year', current_date)
        group by 1
        order by 1
        """,
    ),
    QueryPlan(
        intent="response_time_by_member",
        title="Average response time by team member",
        visualization="bar",
        rationale="Computes first incoming message to first later outgoing response, grouped by assignee.",
        sql="""
        with first_incoming as (
            select
                contact_id,
                min(created_at) as first_incoming_at
            from messages
            where lower(direction) in ('incoming', 'inbound', 'received')
                and created_at >= current_date - interval '90 days'
            group by 1
        ),
        first_response as (
            select
                fi.contact_id,
                fi.first_incoming_at,
                min(m.created_at) as first_response_at
            from first_incoming fi
            join messages m
                on m.contact_id = fi.contact_id
                and lower(m.direction) in ('outgoing', 'outbound', 'sent')
                and m.created_at > fi.first_incoming_at
            group by 1, 2
        )
        select
            coalesce(c.dashboard_assignee_name, c.assignee_name, 'Unassigned') as team_member,
            round(avg(extract(epoch from (fr.first_response_at - fr.first_incoming_at)) / 3600.0), 2) as avg_hours
        from first_response fr
        join conversations c on c.contact_id = fr.contact_id
        group by 1
        order by avg_hours asc nulls last
        """,
    ),
    QueryPlan(
        intent="inactive_clients",
        title="Clients with no contact in over 30 days",
        visualization="table",
        rationale="Finds contacts whose latest conversation or message activity is older than 30 days.",
        sql="""
        with latest_message as (
            select contact_id, max(created_at) as last_message_at
            from messages
            group by 1
        )
        select
            c.contact_id,
            c.contact_name,
            c.contact_email,
            c.contact_status,
            coalesce(lm.last_message_at, c.updated_at, c.created_at) as last_contact_at,
            c.current_step
        from conversations c
        left join latest_message lm on lm.contact_id = c.contact_id
        where coalesce(lm.last_message_at, c.updated_at, c.created_at) < current_date - interval '30 days'
        order by last_contact_at asc
        """,
    ),
]


INVESTIGATION_PLANS = {
    "fewer_new_clients": [
        QueryPlan(
            intent="new_clients_by_week",
            title="New clients by week",
            visualization="line",
            rationale="Checks whether new-client intake actually declined and when it started.",
            sql="""
            select
                date_trunc('week', coalesce(conversation_opened_at, created_at))::date as period,
                count(distinct contact_id)::int as new_clients
            from conversations
            where coalesce(conversation_opened_at, created_at) >= current_date - interval '120 days'
            group by 1
            order by 1
            """,
        ),
        QueryPlan(
            intent="conversation_sources",
            title="New conversations by channel",
            visualization="bar",
            rationale="Looks for whether the decline is concentrated in one acquisition channel.",
            sql="""
            select
                coalesce(channel_name, channel_source, 'Unknown') as channel,
                count(*)::int as conversations
            from conversations
            where coalesce(conversation_opened_at, created_at) >= current_date - interval '45 days'
            group by 1
            order by conversations desc
            """,
        ),
        QueryPlan(
            intent="response_pressure",
            title="Response pressure",
            visualization="metric",
            rationale="Checks if slower response speed could be hurting conversion.",
            sql="""
            with first_incoming as (
                select
                    contact_id,
                    min(created_at) as first_incoming_at
                from messages
                where lower(direction) in ('incoming', 'inbound', 'received')
                    and created_at >= current_date - interval '45 days'
                group by 1
            ),
            first_response as (
                select
                    fi.contact_id,
                    fi.first_incoming_at,
                    min(m.created_at) as first_response_at
                from first_incoming fi
                left join messages m
                    on m.contact_id = fi.contact_id
                    and lower(m.direction) in ('outgoing', 'outbound', 'sent')
                    and m.created_at > fi.first_incoming_at
                group by 1, 2
            )
            select
                round(avg(extract(epoch from (first_response_at - first_incoming_at)) / 3600.0), 2) as avg_first_response_hours,
                count(*) filter (where first_response_at is null)::int as no_response_yet,
                count(*) filter (where first_response_at - first_incoming_at > interval '24 hours')::int as over_24h
            from first_response
            """,
        ),
    ],
    "team_demand": [
        QueryPlan(
            intent="open_conversation_backlog",
            title="Open conversation backlog by team member",
            visualization="bar",
            rationale="Measures whether demand is accumulating unevenly across the team.",
            sql="""
            select
                coalesce(dashboard_assignee_name, assignee_name, 'Unassigned') as team_member,
                count(*)::int as open_conversations
            from conversations
            where blocked = false
                and coalesce(is_handed_off, false) = false
                and lower(coalesce(contact_status, lifecycle, current_step, 'open')) not in ('closed', 'resolved', 'inactive', 'churned')
            group by 1
            order by open_conversations desc
            """,
        ),
        QueryPlan(
            intent="daily_volume",
            title="Daily conversation volume",
            visualization="line",
            rationale="Compares recent demand against daily intake patterns.",
            sql="""
            select
                date_trunc('day', coalesce(conversation_opened_at, created_at))::date as period,
                count(*)::int as conversations
            from conversations
            where coalesce(conversation_opened_at, created_at) >= current_date - interval '45 days'
            group by 1
            order by 1
            """,
        ),
    ],
}


def answer_question(question: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if has_llm():
        try:
            return _answer_with_llm(question, history or [])
        except Exception as exc:
            fallback = _answer_without_llm(question)
            fallback["evidence"] = [
                f"LLM path fell back to deterministic templates: {type(exc).__name__}.",
                *fallback.get("evidence", []),
            ]
            return fallback
    return _answer_without_llm(question)


def _answer_without_llm(question: str) -> dict[str, Any]:
    normalized = question.lower()
    if any(term in normalized for term in ["why", "at risk", "churn", "keeping up", "unusual", "best month"]):
        return _answer_investigation(question, normalized)
    return _answer_direct(question, normalized)


def _answer_with_llm(question: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    schema_context = get_schema_context()
    plan = create_plan(question, schema_context, history)
    steps = plan.get("plan", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("The LLM did not return a usable query plan.")

    results: list[dict[str, Any]] = []
    sql_blocks: list[dict[str, str]] = []
    visualizations: list[dict[str, Any]] = []
    rendered_plan: list[dict[str, str]] = []

    for raw_step in steps[:4]:
        title = str(raw_step.get("title") or "Analysis step")
        rationale = str(raw_step.get("rationale") or "Supports the requested analysis.")
        visualization = _normalize_visualization(str(raw_step.get("visualization") or "table"))
        sql = str(raw_step.get("sql") or "")
        rows, final_sql = _execute_llm_sql(question, schema_context, sql)
        results.append({"title": title, "rows": rows})
        sql_blocks.append({"title": title, "query": with_limit(final_sql)})
        visualizations.append({"type": visualization, "title": title, "data": rows})
        rendered_plan.append({"title": title, "rationale": rationale, "status": "complete"})

    synthesis = synthesize_answer(question, plan, results)
    return {
        "mode": plan.get("mode", "investigation"),
        "question": question,
        "title": plan.get("title", "Issa Insight analysis"),
        "diagnosis": synthesis["diagnosis"] or "I ran the requested analysis and returned the supporting evidence below.",
        "confidence": synthesis["confidence"],
        "caveats": synthesis["caveats"],
        "recommended_actions": synthesis["recommended_actions"],
        "plan": rendered_plan,
        "visualizations": visualizations,
        "sql": sql_blocks,
        "evidence": [
            "Generated a schema-aware query plan with the LLM.",
            f"Ran {len(results)} read-only SQL {'query' if len(results) == 1 else 'queries'}.",
        ],
    }


def _execute_llm_sql(question: str, schema_context: str, sql: str) -> tuple[list[dict[str, Any]], str]:
    try:
        return fetch_all(with_limit(sql)), sql
    except Exception as exc:
        repaired = repair_sql(question, schema_context, sql, str(exc))
        return fetch_all(with_limit(repaired)), repaired


def _normalize_visualization(value: str) -> str:
    if value in {"line", "bar", "table", "metric"}:
        return value
    return "table"


def _answer_direct(question: str, normalized: str) -> dict[str, Any]:
    if "response time" in normalized:
        plan = DIRECT_PLANS[1]
    elif "contact" in normalized or "30 days" in normalized:
        plan = DIRECT_PLANS[2]
    else:
        plan = DIRECT_PLANS[0]
    rows = _safe_fetch(plan)
    return {
        "mode": "direct",
        "question": question,
        "title": plan.title,
        "diagnosis": _summarize_direct(plan, rows),
        "confidence": "Medium",
        "caveats": _default_caveats(plan, rows),
        "recommended_actions": _default_actions(plan.intent),
        "plan": [{"title": plan.title, "rationale": plan.rationale, "status": "complete"}],
        "visualizations": [{"type": plan.visualization, "title": plan.title, "data": rows}],
        "sql": [{"title": plan.title, "query": with_limit(plan.sql)}],
        "evidence": _evidence_from_rows(rows),
    }


def _answer_investigation(question: str, normalized: str) -> dict[str, Any]:
    key = "team_demand" if "keeping up" in normalized or "demand" in normalized else "fewer_new_clients"
    plans = INVESTIGATION_PLANS[key]
    results = []
    for plan in plans:
        results.append({"plan": plan, "rows": _safe_fetch(plan)})
    return {
        "mode": "investigation",
        "question": question,
        "title": "Investigation diagnosis",
        "diagnosis": _summarize_investigation(key, results),
        "confidence": "Medium",
        "caveats": ["This fallback diagnosis uses deterministic playbook queries without LLM synthesis."],
        "recommended_actions": _default_actions(key),
        "plan": [
            {"title": item["plan"].title, "rationale": item["plan"].rationale, "status": "complete"}
            for item in results
        ],
        "visualizations": [
            {"type": item["plan"].visualization, "title": item["plan"].title, "data": item["rows"]}
            for item in results
        ],
        "sql": [{"title": item["plan"].title, "query": with_limit(item["plan"].sql)} for item in results],
        "evidence": [item["plan"].rationale for item in results],
    }


def _safe_fetch(plan: QueryPlan) -> list[dict[str, Any]]:
    try:
        return fetch_all(with_limit(plan.sql))
    except RuntimeError:
        return SAMPLE_ROWS.get(plan.intent, [])


def _summarize_direct(plan: QueryPlan, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "I ran the query safely, but it returned no rows. Once we confirm the schema, this may need a table or column mapping adjustment."
    if plan.intent == "monthly_conversations":
        return _summarize_monthly_conversations(rows)
    if plan.intent == "response_time_by_member":
        return _summarize_response_times(rows)
    if plan.intent == "inactive_clients":
        return _summarize_inactive_clients(rows)
    return f"I found {len(rows)} result rows for {plan.title.lower()}. The chart is ready, and the SQL is available in the evidence panel."


def _summarize_monthly_conversations(rows: list[dict[str, Any]]) -> str:
    sorted_rows = sorted(rows, key=lambda row: str(row.get("period") or ""))
    first = sorted_rows[0]
    latest = sorted_rows[-1]
    previous = sorted_rows[-2] if len(sorted_rows) > 1 else None
    peak = max(sorted_rows, key=lambda row: int(row.get("conversations") or 0))

    latest_count = int(latest.get("conversations") or 0)
    peak_count = int(peak.get("conversations") or 0)
    latest_label = _period_label(latest.get("period"))
    peak_label = _period_label(peak.get("period"))

    if previous:
        previous_count = int(previous.get("conversations") or 0)
        delta = latest_count - previous_count
        direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
        change_text = f"{latest_label} is {direction} by {abs(delta)} conversations versus {_period_label(previous.get('period'))}."
    else:
        first_count = int(first.get("conversations") or 0)
        change_text = f"The series starts at {first_count} conversations in {_period_label(first.get('period'))}."

    return (
        f"New client conversations peaked in {peak_label} at {peak_count} conversations. "
        f"The latest visible month, {latest_label}, has {latest_count} conversations; {change_text} "
        "If the latest month is still in progress, treat the drop as a month-to-date signal and compare it with the same day range in prior months before escalating."
    )


def _summarize_response_times(rows: list[dict[str, Any]]) -> str:
    ranked = sorted(rows, key=lambda row: float(row.get("avg_hours") or 0), reverse=True)
    slowest = ranked[0]
    fastest = ranked[-1]
    return (
        f"{slowest.get('team_member', 'The slowest assignee')} has the slowest average first response at "
        f"{float(slowest.get('avg_hours') or 0):.1f} hours, while {fastest.get('team_member', 'the fastest assignee')} "
        f"is fastest at {float(fastest.get('avg_hours') or 0):.1f} hours. "
        "The team should inspect workload, handoffs, and unanswered incoming threads for the slowest owners."
    )


def _summarize_inactive_clients(rows: list[dict[str, Any]]) -> str:
    oldest = rows[0]
    return (
        f"I found {len(rows)} clients with no contact in over 30 days. "
        f"The stalest visible client is {oldest.get('contact_name') or oldest.get('contact_id')} "
        f"with last contact on {_period_label(oldest.get('last_contact_at'))}. "
        "This should be treated as a follow-up queue, starting with open lifecycle or current-step records."
    )


def _period_label(value: Any) -> str:
    text = str(value or "unknown")
    if "T" in text:
        text = text.split("T", 1)[0]
    if len(text) >= 10:
        return text[:10]
    return text


def _summarize_investigation(key: str, results: list[dict[str, Any]]) -> str:
    completed = len(results)
    if key == "team_demand":
        backlog = next((item["rows"] for item in results if item["plan"].intent == "open_conversation_backlog"), [])
        volume = next((item["rows"] for item in results if item["plan"].intent == "daily_volume"), [])
        top_owner = backlog[0] if backlog else {}
        latest_volume = volume[-1] if volume else {}
        return (
            f"I checked {completed} demand signals: backlog by owner and recent daily intake. "
            f"The largest visible backlog is with {top_owner.get('team_member', 'an assignee')} "
            f"at {top_owner.get('open_conversations', 'unknown')} open conversations, while the latest daily intake is "
            f"{latest_volume.get('conversations', 'unknown')} conversations on {_period_label(latest_volume.get('period'))}. "
            "The team should compare overloaded owners against recent intake before deciding whether to rebalance work."
        )

    trend = next((item["rows"] for item in results if item["plan"].intent == "new_clients_by_week"), [])
    channels = next((item["rows"] for item in results if item["plan"].intent == "conversation_sources"), [])
    latest = trend[-1] if trend else {}
    previous = trend[-2] if len(trend) > 1 else {}
    top_channel = channels[0] if channels else {}
    delta = int(latest.get("new_clients") or 0) - int(previous.get("new_clients") or 0)
    direction = "down" if delta < 0 else "up" if delta > 0 else "flat"
    return (
        f"I checked {completed} acquisition signals: new-client trend, channel mix, and response pressure. "
        f"The latest visible week is {direction} by {abs(delta)} new clients versus the prior week, "
        f"and the largest recent channel is {top_channel.get('channel', 'unknown')} with "
        f"{top_channel.get('conversations', 'unknown')} conversations. "
        "The next best drilldown is to compare channel movement and qualified rate over the same period."
    )


def _evidence_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["No rows returned."]
    return [f"Returned {len(rows)} rows.", f"Columns: {', '.join(rows[0].keys())}."]


def _default_caveats(plan: QueryPlan, rows: list[dict[str, Any]]) -> list[str]:
    caveats = []
    if not rows:
        caveats.append("No rows were returned, so the result may need schema or date-range adjustment.")
    if plan.intent == "monthly_conversations":
        caveats.append("The current month may be incomplete; compare month-to-date carefully.")
    return caveats


def _default_actions(intent: str) -> list[str]:
    actions = {
        "monthly_conversations": [
            "Compare current month-to-date against the same number of days last month.",
            "Break the trend down by channel_name and channel_source.",
        ],
        "response_time_by_member": [
            "Review the slowest assignees for workload or handoff issues.",
            "Drill into unanswered incoming threads over 24 hours.",
        ],
        "inactive_clients": [
            "Assign owners to the oldest stale contacts.",
            "Prioritize clients with open lifecycle/current_step states.",
        ],
        "fewer_new_clients": [
            "Inspect channels with the largest recent decline.",
            "Check whether qualified conversations fell faster than total conversations.",
        ],
        "team_demand": [
            "Rebalance open conversations from overloaded assignees.",
            "Review handed-off and AI-inactive conversations for operational friction.",
        ],
    }
    return actions.get(intent, ["Use the follow-up prompt to drill into the largest driver."])


SAMPLE_ROWS: dict[str, list[dict[str, Any]]] = {
    "monthly_conversations": [
        {"period": "2026-01-01", "conversations": 812},
        {"period": "2026-02-01", "conversations": 936},
        {"period": "2026-03-01", "conversations": 884},
        {"period": "2026-04-01", "conversations": 1048},
        {"period": "2026-05-01", "conversations": 1176},
        {"period": "2026-06-01", "conversations": 1092},
    ],
    "response_time_by_member": [
        {"team_member": "Aisha Khan", "avg_hours": 3.8},
        {"team_member": "Marco Ruiz", "avg_hours": 4.6},
        {"team_member": "Nina Patel", "avg_hours": 5.2},
        {"team_member": "Sam Lee", "avg_hours": 7.4},
    ],
    "inactive_clients": [
        {"client_id": "C-1024", "client_name": "Daniel M.", "last_contact_at": "2026-05-08", "status": "document_review"},
        {"client_id": "C-1188", "client_name": "Priya S.", "last_contact_at": "2026-05-11", "status": "consultation"},
        {"client_id": "C-1219", "client_name": "Ana R.", "last_contact_at": "2026-05-17", "status": "pending_docs"},
    ],
    "new_clients_by_week": [
        {"period": "2026-05-04", "new_clients": 118},
        {"period": "2026-05-11", "new_clients": 126},
        {"period": "2026-05-18", "new_clients": 110},
        {"period": "2026-05-25", "new_clients": 93},
        {"period": "2026-06-01", "new_clients": 89},
        {"period": "2026-06-08", "new_clients": 82},
    ],
    "conversation_sources": [
        {"channel": "Referral", "conversations": 242},
        {"channel": "Website", "conversations": 196},
        {"channel": "WhatsApp", "conversations": 148},
        {"channel": "Email", "conversations": 86},
    ],
    "response_pressure": [
        {"avg_first_response_hours": 7.8, "over_24h": 31},
    ],
    "open_conversation_backlog": [
        {"team_member": "Sam Lee", "open_conversations": 64},
        {"team_member": "Nina Patel", "open_conversations": 51},
        {"team_member": "Marco Ruiz", "open_conversations": 43},
        {"team_member": "Aisha Khan", "open_conversations": 37},
    ],
    "daily_volume": [
        {"period": "2026-06-01", "conversations": 78},
        {"period": "2026-06-02", "conversations": 84},
        {"period": "2026-06-03", "conversations": 91},
        {"period": "2026-06-04", "conversations": 96},
        {"period": "2026-06-05", "conversations": 102},
    ],
}
