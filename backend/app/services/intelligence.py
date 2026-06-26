from __future__ import annotations

from typing import Any

from app.services.db import fetch_all
from app.services.sql_guard import with_limit


def get_anomaly_radar() -> dict[str, Any]:
    signals = [
        _conversation_pace_signal(),
        _channel_shift_signal(),
        _response_gap_signal(),
        _operations_friction_signal(),
    ]
    ranked = sorted(signals, key=lambda item: item["severity_score"], reverse=True)
    return {
        "title": "Anomaly Radar",
        "summary": _radar_summary(ranked),
        "signals": ranked,
    }


def get_client_risk_queue() -> dict[str, Any]:
    rows = fetch_all(
        with_limit(
            """
            with message_rollup as (
                select
                    contact_id,
                    max(created_at) as last_message_at,
                    count(*) filter (where lower(direction) in ('incoming', 'inbound', 'received'))::int as incoming_messages,
                    count(*) filter (where lower(direction) in ('outgoing', 'outbound', 'sent'))::int as outgoing_messages
                from messages
                group by 1
            ),
            scored as (
                select
                    c.contact_id,
                    c.contact_name,
                    coalesce(c.dashboard_assignee_name, c.assignee_name, 'Unassigned') as assignee,
                    coalesce(c.contact_status, c.lifecycle, c.current_step, 'Unknown') as status,
                    coalesce(m.last_message_at, c.updated_at, c.created_at) as last_contact_at,
                    coalesce(m.incoming_messages, c.incoming_message_count, 0) as incoming_messages,
                    coalesce(m.outgoing_messages, c.outgoing_message_count, 0) as outgoing_messages,
                    c.blocked,
                    c.is_handed_off,
                    c.is_emergency,
                    c.ai_active,
                    c.ai_eligible,
                    (
                        case when coalesce(m.last_message_at, c.updated_at, c.created_at) < now() - interval '30 days' then 25 else 0 end
                        + case when coalesce(m.last_message_at, c.updated_at, c.created_at) < now() - interval '14 days' then 12 else 0 end
                        + case when coalesce(c.blocked, false) then 25 else 0 end
                        + case when coalesce(m.outgoing_messages, c.outgoing_message_count, 0) = 0 and coalesce(m.incoming_messages, c.incoming_message_count, 0) > 0 then 20 else 0 end
                        + case when coalesce(m.incoming_messages, c.incoming_message_count, 0) - coalesce(m.outgoing_messages, c.outgoing_message_count, 0) >= 5 then 15 else 0 end
                        + case when coalesce(c.dashboard_assignee_name, c.assignee_name) is null then 15 else 0 end
                        + case when coalesce(c.is_emergency, false) then 15 else 0 end
                        + case when coalesce(c.ai_active, false) = false or coalesce(c.ai_eligible, false) = false then 8 else 0 end
                    )::int as risk_score
                from conversations c
                left join message_rollup m on m.contact_id = c.contact_id
                where lower(coalesce(c.contact_status, c.lifecycle, c.current_step, 'open')) not in ('closed', 'resolved', 'inactive', 'churned')
            )
            select *
            from scored
            where risk_score > 0
            order by risk_score desc, last_contact_at asc
            limit 25
            """
        )
    )
    return {
        "title": "Client Risk Queue",
        "summary": _risk_summary(rows),
        "clients": rows,
    }


def _conversation_pace_signal() -> dict[str, Any]:
    rows = fetch_all(
        with_limit(
            """
            with bounds as (
                select
                    date_trunc('month', current_date)::date as this_month,
                    (date_trunc('month', current_date) - interval '1 month')::date as last_month,
                    extract(day from current_date)::int as day_of_month
            ),
            counts as (
                select
                    count(*) filter (
                        where coalesce(conversation_opened_at, created_at) >= b.this_month
                          and coalesce(conversation_opened_at, created_at) < current_date + interval '1 day'
                    )::int as current_mtd,
                    count(*) filter (
                        where coalesce(conversation_opened_at, created_at) >= b.last_month
                          and coalesce(conversation_opened_at, created_at) < b.last_month + (b.day_of_month || ' days')::interval
                    )::int as previous_mtd
                from conversations, bounds b
            )
            select
                current_mtd,
                previous_mtd,
                round(100.0 * (current_mtd - previous_mtd) / nullif(previous_mtd, 0), 1) as pct_change
            from counts
            """
        )
    )
    row = rows[0] if rows else {}
    pct = float(row.get("pct_change") or 0)
    return {
        "name": "New conversation pace",
        "severity": _severity(abs(pct), 35, 15),
        "severity_score": min(100, abs(pct)),
        "metric": f"{pct:+.1f}%",
        "detail": f"Month-to-date conversations are {pct:+.1f}% versus the same span last month.",
        "data": rows,
    }


def _channel_shift_signal() -> dict[str, Any]:
    rows = fetch_all(
        with_limit(
            """
            with recent as (
                select coalesce(channel_name, channel_source, 'Unknown') as channel, count(*)::int as recent_count
                from conversations
                where coalesce(conversation_opened_at, created_at) >= current_date - interval '30 days'
                group by 1
            ),
            prior as (
                select coalesce(channel_name, channel_source, 'Unknown') as channel, count(*)::int as prior_count
                from conversations
                where coalesce(conversation_opened_at, created_at) >= current_date - interval '60 days'
                  and coalesce(conversation_opened_at, created_at) < current_date - interval '30 days'
                group by 1
            )
            select
                coalesce(r.channel, p.channel) as channel,
                coalesce(r.recent_count, 0) as recent_count,
                coalesce(p.prior_count, 0) as prior_count,
                round(100.0 * (coalesce(r.recent_count, 0) - coalesce(p.prior_count, 0)) / nullif(p.prior_count, 0), 1) as pct_change
            from recent r
            full outer join prior p on p.channel = r.channel
            order by abs(coalesce(round(100.0 * (coalesce(r.recent_count, 0) - coalesce(p.prior_count, 0)) / nullif(p.prior_count, 0), 1), 0)) desc
            limit 5
            """
        )
    )
    top = rows[0] if rows else {}
    pct = float(top.get("pct_change") or 0)
    channel = top.get("channel") or "Unknown"
    return {
        "name": "Channel mix shift",
        "severity": _severity(abs(pct), 40, 20),
        "severity_score": min(100, abs(pct)),
        "metric": f"{channel}: {pct:+.1f}%",
        "detail": f"{channel} has the largest 30-day channel movement versus the prior 30 days.",
        "data": rows,
    }


def _response_gap_signal() -> dict[str, Any]:
    rows = fetch_all(
        with_limit(
            """
            with recent_incoming as (
                select
                    contact_id,
                    max(created_at) as last_incoming_at
                from messages
                where lower(direction) in ('incoming', 'inbound', 'received')
                  and created_at >= current_date - interval '30 days'
                group by 1
            ),
            later_outgoing as (
                select ri.contact_id, min(m.created_at) as next_outgoing_at
                from recent_incoming ri
                left join messages m
                    on m.contact_id = ri.contact_id
                    and lower(m.direction) in ('outgoing', 'outbound', 'sent')
                    and m.created_at > ri.last_incoming_at
                group by 1
            )
            select
                count(*)::int as recent_incoming_threads,
                count(*) filter (where next_outgoing_at is null and last_incoming_at < now() - interval '24 hours')::int as unanswered_over_24h,
                round(100.0 * count(*) filter (where next_outgoing_at is null and last_incoming_at < now() - interval '24 hours') / nullif(count(*), 0), 1) as unanswered_rate
            from recent_incoming ri
            join later_outgoing lo on lo.contact_id = ri.contact_id
            """
        )
    )
    row = rows[0] if rows else {}
    rate = float(row.get("unanswered_rate") or 0)
    return {
        "name": "Response gap",
        "severity": _severity(rate, 25, 10),
        "severity_score": min(100, rate * 2),
        "metric": f"{rate:.1f}%",
        "detail": f"{rate:.1f}% of recent incoming threads appear unanswered for more than 24 hours.",
        "data": rows,
    }


def _operations_friction_signal() -> dict[str, Any]:
    rows = fetch_all(
        with_limit(
            """
            select
                count(*)::int as active_conversations,
                count(*) filter (where coalesce(blocked, false))::int as blocked_count,
                count(*) filter (where coalesce(is_handed_off, false))::int as handed_off_count,
                count(*) filter (where coalesce(ai_active, false) = false or coalesce(ai_eligible, false) = false)::int as ai_inactive_or_ineligible_count,
                round(100.0 * count(*) filter (
                    where coalesce(blocked, false)
                       or coalesce(is_handed_off, false)
                       or coalesce(ai_active, false) = false
                       or coalesce(ai_eligible, false) = false
                ) / nullif(count(*), 0), 1) as friction_rate
            from conversations
            where lower(coalesce(contact_status, lifecycle, current_step, 'open')) not in ('closed', 'resolved', 'inactive', 'churned')
            """
        )
    )
    row = rows[0] if rows else {}
    rate = float(row.get("friction_rate") or 0)
    return {
        "name": "Operational friction",
        "severity": _severity(rate, 35, 15),
        "severity_score": min(100, rate * 1.5),
        "metric": f"{rate:.1f}%",
        "detail": f"{rate:.1f}% of active conversations are blocked, handed off, or AI-disabled.",
        "data": rows,
    }


def _severity(value: float, high: float, medium: float) -> str:
    if value >= high:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def _radar_summary(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "No anomaly signals are available yet."
    top = signals[0]
    return f"Top signal: {top['name']} ({top['metric']}). {top['detail']}"


def _risk_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No high-risk active clients detected from the current scoring rules."
    top = rows[0]
    return f"{len(rows)} clients are currently flagged. Highest risk: {top.get('contact_name') or top.get('contact_id')} with score {top.get('risk_score')}."
