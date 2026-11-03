"""Bounded retry/backoff and secret-safe structured event logging helpers."""
from __future__ import annotations

import logging
import random
import re
import time
import traceback
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TransientHTTPError(RuntimeError):
    """HTTP status eligible for a bounded retry (429 or 5xx)."""
_SECRET_KEY = (
    r"(?:api[_-]?key|secret|password|token|authorization|private[_-]?key|"
    r"mnemonic|seed|passphrase)"
)
_SECRET_PATTERNS = (
    re.compile(
        rf"""(?ix)(?P<prefix>["']?{_SECRET_KEY}["']?\s*[:=]\s*)"""
        rf"""(?P<quote>["'])(?P<value>.*?)(?P=quote)"""
    ),
    re.compile(
        rf"""(?i)(?P<prefix>["']?{_SECRET_KEY}["']?\s*[:=]\s*)"""
        r"""(?:(?:bearer|basic|token)\s+)?[^\s,;}]+"""
    ),
    re.compile(r"(?i)\b(?:bearer|basic|token)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(?:0x)?[a-f0-9]{64}\b"),
)


def redact(value: object) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        if "prefix" in pattern.groupindex:
            text = pattern.sub(lambda match: match.group("prefix") + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def configure_logging(
    *,
    level: int = logging.INFO,
    handler: logging.Handler | None = None,
    logger: logging.Logger | None = None,
) -> logging.Handler:
    """Configure a handler with secret redaction enabled."""
    target = logger or logging.getLogger()
    configured_handler = handler or logging.StreamHandler()
    configured_handler.addFilter(RedactingFilter())
    target.setLevel(level)
    target.addHandler(configured_handler)
    return configured_handler


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
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
