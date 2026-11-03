"""Bounded retry/backoff and secret-safe structured event logging helpers."""
from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TransientHTTPError(RuntimeError):
    """HTTP status eligible for a bounded retry (429 or 5xx)."""
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token|authorization)(\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"0x[a-fA-F0-9]{64}"),
)


def redact(value: object) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: (match.group(1) + match.group(2) + "[REDACTED]")
                           if match.lastindex and match.lastindex >= 2 else "[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def retry_call(
    operation: Callable[[], T],
    *,
    retryable: tuple[type[BaseException], ...],
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    sleeper: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    if max_attempts < 1 or base_delay < 0 or max_delay < 0:
        raise ValueError("invalid retry configuration")
    for attempt in range(max_attempts):
        try:
            return operation()
        except retryable:
            if attempt + 1 >= max_attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            sleeper(delay * (0.5 + jitter() * 0.5))
    raise RuntimeError("unreachable retry state")
