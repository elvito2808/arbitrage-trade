import logging

import pytest

from arbitrage_trade.registry import Registry, RegistryError
from arbitrage_trade.resilience import (
    RedactingFilter, configure_logging, redact, retry_call,
)


def test_registry_rejects_duplicates_and_supports_replace():
    registry = Registry[str]()
    registry.register("x", "one")
    with pytest.raises(RegistryError):
        registry.register("x", "two")
    registry.register("x", "two", replace=True)
    assert registry.get("x") == "two"
    assert registry.keys() == ("x",)


def test_retry_is_bounded_and_uses_backoff():
    attempts = []
    delays = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("transient")
        return "ok"

    result = retry_call(operation, retryable=(TimeoutError,), max_attempts=3,
                        base_delay=0.2, sleeper=delays.append, jitter=lambda: 1.0)
    assert result == "ok"
    assert len(attempts) == 3
    assert delays == [0.2, 0.4]


def test_retry_does_not_retry_unlisted_errors():
    attempts = []
    def operation():
        attempts.append(1)
        raise ValueError("bad payload")
    with pytest.raises(ValueError):
        retry_call(operation, retryable=(TimeoutError,), max_attempts=4,
                   sleeper=lambda _: None)
    assert len(attempts) == 1


def test_secret_redaction_and_logging_filter():
    assert "secret=[REDACTED]" in redact("secret=abc123")
    assert "0x" not in redact("key 0x" + "a" * 64)
    record = logging.LogRecord("x", logging.INFO, "", 0, "api_key=abc", (), None)
    assert RedactingFilter().filter(record)
    assert "[REDACTED]" in record.msg


def test_redacting_filter_sanitizes_exception_tracebacks_and_stack_info():
    import io

    logger = logging.getLogger("test.redaction.traceback")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    secret = "api_key=super-secret-value"
    private_key = "0x" + "a" * 64
    try:
        raise RuntimeError(f"request failed {secret}; wallet={private_key}")
    except RuntimeError:
        logger.exception("adapter failure")
    output = stream.getvalue()
    assert "super-secret-value" not in output
    assert private_key not in output
    assert "[REDACTED]" in output
    logger.removeHandler(handler)


def test_redact_handles_bearer_authorization_value():
    assert "Bearer hidden" not in redact("Authorization: Bearer hidden")
    assert "b" * 64 not in redact("private=" + "b" * 64)


@pytest.mark.parametrize(
    ("sample", "secret"),
    [
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("authorization=Token abc.def-123", "abc.def-123"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9", "eyJhbGciOiJIUzI1NiJ9"),
        ('{"api_key": "value with spaces"}', "value with spaces"),
        ('{"private_key":"0x' + "a" * 64 + '"}', "0x" + "a" * 64),
        ('{"mnemonic": "twelve secret words here"}', "twelve secret words here"),
        ('{"seed": "seed material"}', "seed material"),
        ('{"passphrase": "a phrase with spaces"}', "a phrase with spaces"),
        ('{"token": "quoted token"}', "quoted token"),
    ],
)
def test_redact_all_supported_secret_formats(sample, secret):
    output = redact(sample)
    assert secret not in output
    assert "[REDACTED]" in output


def test_real_stack_info_logging_is_formatted_and_redacted():
    import io

    logger = logging.getLogger("test.redaction.real-stack")
    logger.handlers.clear()
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    configure_logging(handler=handler, logger=logger)
    logger.warning('payload={"mnemonic": "words with spaces"}', stack_info=True)
    output = stream.getvalue()
    assert "words with spaces" not in output
    assert "Stack (most recent call last)" in output
    logger.removeHandler(handler)


def test_configure_logging_attaches_redaction_filter():
    logger = logging.getLogger("test.redaction.configure")
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.NullHandler()
    configured = configure_logging(handler=handler, logger=logger)
    assert configured is handler
    assert any(isinstance(item, RedactingFilter) for item in handler.filters)
    logger.removeHandler(handler)
