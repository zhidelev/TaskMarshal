from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

CORRELATION_HEADER = "X-Correlation-ID"
correlation_id_context: ContextVar[str | None] = ContextVar(
    "taskmarshal_correlation_id", default=None
)


def normalized_correlation_id(value: str | None) -> str:
    """Accept UUID values only and canonicalize them; replace all other values."""
    if value is not None:
        try:
            return str(UUID(value))
        except (ValueError, AttributeError):
            pass
    return str(uuid4())
