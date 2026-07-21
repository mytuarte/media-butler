from datetime import datetime, timezone


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "Unknown"

    units = ["B", "KB", "MB", "GB", "TB"]

    size = float(size_bytes)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"

        size /= 1024


def format_date(date_string: str | None) -> str:
    if not date_string:
        return "Unknown"

    date = datetime.fromisoformat(
        date_string.replace("Z", "+00:00")
    )

    return date.strftime("%b %d, %Y")


def format_age(date_string: str | None) -> str:
    if not date_string:
        return "Unknown"

    added = datetime.fromisoformat(
        date_string.replace("Z", "+00:00")
    )

    now = datetime.now(timezone.utc)

    delta = now - added

    days = delta.days

    if days < 30:
        return f"{days} days"

    months = days // 30

    if months < 12:
        return f"{months} months"

    years = months // 12
    months %= 12

    if months == 0:
        return f"{years} years"

    return f"{years} years, {months} months"