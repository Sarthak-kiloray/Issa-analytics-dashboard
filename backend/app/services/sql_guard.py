import re


FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|execute|merge|vacuum)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    normalized = sql.strip().rstrip(";")
    if not normalized:
        raise ValueError("SQL cannot be empty.")
    if ";" in normalized:
        raise ValueError("Only one SQL statement is allowed.")
    if not re.match(r"^(select|with)\b", normalized, re.IGNORECASE):
        raise ValueError("Only SELECT statements are allowed.")
    if FORBIDDEN.search(normalized):
        raise ValueError("This query contains a forbidden SQL operation.")
    return normalized


def with_limit(sql: str, limit: int = 500) -> str:
    guarded = validate_readonly_sql(sql)
    if re.search(r"\blimit\s+\d+\b", guarded, re.IGNORECASE):
        return guarded
    return f"{guarded}\nlimit {limit}"

