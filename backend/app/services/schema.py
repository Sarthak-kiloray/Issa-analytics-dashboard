from app.services.db import fetch_all


def list_public_tables() -> list[str]:
    try:
        rows = fetch_all(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
            order by table_name;
            """
        )
        return [row["table_name"] for row in rows]
    except RuntimeError:
        return ["clients", "conversations", "messages", "team_members"]


def get_schema_summary() -> dict:
    try:
        columns = fetch_all(
            """
            select
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable
            from information_schema.columns c
            join information_schema.tables t
                on t.table_schema = c.table_schema
                and t.table_name = c.table_name
            where c.table_schema = 'public'
                and t.table_type = 'BASE TABLE'
            order by c.table_name, c.ordinal_position;
            """
        )
    except RuntimeError:
        columns = [
            {"table_name": "clients", "column_name": "id", "data_type": "uuid", "is_nullable": "NO"},
            {"table_name": "clients", "column_name": "created_at", "data_type": "timestamp", "is_nullable": "NO"},
            {"table_name": "clients", "column_name": "last_contact_at", "data_type": "timestamp", "is_nullable": "YES"},
            {"table_name": "conversations", "column_name": "id", "data_type": "uuid", "is_nullable": "NO"},
            {"table_name": "conversations", "column_name": "created_at", "data_type": "timestamp", "is_nullable": "NO"},
            {"table_name": "conversations", "column_name": "channel", "data_type": "text", "is_nullable": "YES"},
            {"table_name": "team_members", "column_name": "name", "data_type": "text", "is_nullable": "NO"},
        ]
    tables: dict[str, list[dict[str, str]]] = {}
    for row in columns:
        tables.setdefault(row["table_name"], []).append(
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"],
            }
        )
    return {"tables": tables}


def get_schema_context() -> str:
    summary = get_schema_summary()
    lines = [
        "Business semantics:",
        "- conversations.contact_id links to messages.contact_id.",
        "- conversations.conversation_opened_at is the best conversation start date; use created_at as fallback.",
        "- messages.created_at is the message timestamp; messages.direction separates incoming and outgoing messages.",
        "- conversations.channel_name/channel_source describe acquisition or communication channel.",
        "- conversations.dashboard_assignee_name/assignee_name describe the team member owner.",
        "- conversations.contact_status/lifecycle/current_step describe client state.",
        "- blocked, is_handed_off, is_qualified, is_emergency, ai_active, ai_eligible are boolean operational signals.",
        "",
        "Tables:",
    ]
    for table_name, columns in summary["tables"].items():
        column_text = ", ".join(f"{column['name']} {column['type']}" for column in columns)
        lines.append(f"- {table_name}({column_text})")
    return "\n".join(lines)
