import logging

import pytest

from arbitrage_trade.registry import Registry, RegistryError
from arbitrage_trade.resilience import (
    RedactingFilter,
    configure_logging,
    redact,
    retry_call,
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


def test_formatter_never_emits_any_supported_secret_sample():
    import io

    samples = [
        ('Authorization: Basic dXNlcjpwYXNz', "dXNlcjpwYXNz"),
        ("authorization=Token abc.def-123", "abc.def-123"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9", "eyJhbGciOiJIUzI1NiJ9"),
        ('{"api_key": "value with spaces"}', "value with spaces"),
        ('{"private_key": "private phrase with spaces"}', "private phrase with spaces"),
        ('{"mnemonic": "twelve secret words here"}', "twelve secret words here"),
        ('{"seed": "seed material"}', "seed material"),
        ('{"passphrase": "a phrase with spaces"}', "a phrase with spaces"),
    ]
    logger = logging.getLogger("test.redaction.all-formats")
    logger.handlers.clear()
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    configure_logging(handler=handler, logger=logger)
    for sample, _ in samples:
        logger.error("%s", sample)
    output = stream.getvalue()
    for _, secret in samples:
        assert secret not in output
    logger.removeHandler(handler)


@pytest.mark.parametrize(
    ("sample", "secret"),
    [
        ("secret_key=sk-live-123", "sk-live-123"),
        ("aws_secret_access_key=aws-value-456", "aws-value-456"),
        ("ACCESS_KEY: access-value-789", "access-value-789"),
        ('{"client_secret": "client secret with spaces"}', "client secret with spaces"),
        ('{"auth": "auth value"}', "auth value"),
    ],
)
def test_redact_new_secret_key_aliases(sample, secret):
    assert secret not in redact(sample)
    assert "[REDACTED]" in redact(sample)


@pytest.mark.parametrize(
    ("sample", "secret"),
    [
        ("mnemonic: words one two three", "words one two three"),
        ("seed=seed phrase material", "seed phrase material"),
        ("passphrase: phrase with several words", "phrase with several words"),
        ("password=password with spaces", "password with spaces"),
    ],
)
def test_unquoted_recovery_values_are_redacted_to_end_of_line(sample, secret):
    output = redact(sample + "\npublic diagnostic line")
    assert secret not in output
    assert "public diagnostic line" in output


@pytest.mark.parametrize(
    "ordinary_text",
    [
        "Invalid token format",
        "token format is unsupported",
        "basic authentication is not configured",
    ],
)
def test_ordinary_authentication_words_are_not_redacted(ordinary_text):
    assert redact(ordinary_text) == ordinary_text


def test_authorization_schemes_and_bearer_context_are_redacted():
    for value in (
        "Authorization: Basic dXNlcjpwYXNz",
        "Authorization: Token token-value-123",
        "Authorization: Bearer bearer-value-123",
        "Bearer standalone-value-123",
    ):
        output = redact(value)
        assert value.split()[-1] not in output
        assert "[REDACTED]" in output


def test_configure_logging_is_idempotent_for_handler_and_filter():
    logger = logging.getLogger("test.redaction.idempotent")
    logger.handlers.clear()
    handler = logging.NullHandler()
    first = configure_logging(handler=handler, logger=logger)
    second = configure_logging(handler=handler, logger=logger)
    assert first is second is handler
    assert logger.handlers.count(handler) == 1
    assert sum(isinstance(item, RedactingFilter) for item in handler.filters) == 1
    logger.removeHandler(handler)
