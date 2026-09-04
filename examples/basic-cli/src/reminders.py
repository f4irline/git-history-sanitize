"""Build reminder payloads without placing provider credentials in code."""

from datetime import date, timedelta


def due_on(as_of: date) -> date:
    return as_of + timedelta(days=7)
