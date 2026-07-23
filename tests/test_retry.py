"""Tests for skuld.retry — retry logic for LLM provider calls."""
from __future__ import annotations

import pytest

from skuld.llm_client import LLMClient, TokenBudgetExceeded
from skuld.models import GenerationRequest, GenerationResponse
from skuld.providers.base import ProviderAPIError


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FakeClient:
    """Configurable fake LLM client for retry tests.

    Pass a list of results: each element is either a GenerationResponse
    (returned on that call) or an Exception (raised on that call).
    """

    def __init__(self, results: list):
        self._results = list(results)
        self._call_index = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if self._call_index >= len(self._results):
            raise RuntimeError("FakeClient exhausted configured results")
        result = self._results[self._call_index]
        self._call_index += 1
        if isinstance(result, Exception):
            raise result
        return result

    @property
    def call_count(self) -> int:
        return self._call_index


def _make_response(content: str = "ok") -> GenerationResponse:
    return GenerationResponse(
        content=content,
        model="test-model",
        provider="test",
        prompt_tokens=10,
        completion_tokens=5,
        finish_reason="stop",
    )


def _make_request() -> GenerationRequest:
    return GenerationRequest(system_prompt="sys", user_prompt="usr")


def _sleep_recorder() -> tuple[list[float], callable]:
    """Returns (recorded_delays, sleep_func)."""
    delays: list[float] = []

    def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    return delays, fake_sleep


# ---------------------------------------------------------------------------
# ProviderAPIError retryable attribute
# ---------------------------------------------------------------------------


class TestProviderAPIErrorRetryable:
    """ProviderAPIError retryable attribute."""

    def test_default_retryable_is_false(self):
        err = ProviderAPIError("something broke")
        assert err.retryable is False

    def test_retryable_can_be_set_true(self):
        err = ProviderAPIError("rate limit", retryable=True)
        assert err.retryable is True

    def test_retryable_can_be_set_false_explicitly(self):
        err = ProviderAPIError("auth failed", retryable=False)
        assert err.retryable is False

    def test_message_is_preserved(self):
        err = ProviderAPIError("something broke", retryable=True)
        assert str(err) == "something broke"


# ---------------------------------------------------------------------------
# RetryingLLMClient
# ---------------------------------------------------------------------------


class TestRetryingLLMClientProtocol:
    """Protocol compliance."""

    def test_is_llm_client_protocol_compliant(self):
        from skuld.retry import RetryingLLMClient

        client = FakeClient([_make_response()])
        retrying = RetryingLLMClient(client)
        assert isinstance(retrying, LLMClient)


class TestRetryingLLMClientSuccess:
    """Successful calls — no retries needed."""

    def test_first_attempt_success_no_retry(self):
        from skuld.retry import RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([_make_response("hello")])
        retrying = RetryingLLMClient(client, sleep_func=sleep_fn)

        resp = retrying.generate(_make_request())
        assert resp.content == "hello"
        assert client.call_count == 1
        assert delays == []

    def test_retryable_error_succeeds_on_second_attempt(self):
        from skuld.retry import RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("rate limit", retryable=True),
            _make_response("recovered"),
        ])
        retrying = RetryingLLMClient(client, sleep_func=sleep_fn)

        resp = retrying.generate(_make_request())
        assert resp.content == "recovered"
        assert client.call_count == 2
        assert len(delays) == 1

    def test_retryable_error_succeeds_on_third_attempt(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("timeout", retryable=True),
            ProviderAPIError("timeout", retryable=True),
            _make_response("finally"),
        ])
        retrying = RetryingLLMClient(client, policy=RetryPolicy(max_retries=3), sleep_func=sleep_fn)

        resp = retrying.generate(_make_request())
        assert resp.content == "finally"
        assert client.call_count == 3
        assert len(delays) == 2


class TestRetryingLLMClientExhaustion:
    """Retries exhausted — re-raise last error."""

    def test_exhausts_all_retries_raises_last_error(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        errors = [
            ProviderAPIError(f"attempt {i}", retryable=True)
            for i in range(4)
        ]
        client = FakeClient(errors)
        retrying = RetryingLLMClient(
            client, policy=RetryPolicy(max_retries=3), sleep_func=sleep_fn
        )

        with pytest.raises(ProviderAPIError, match="attempt 3"):
            retrying.generate(_make_request())
        assert client.call_count == 4
        assert len(delays) == 3


class TestRetryingLLMClientNoRetry:
    """Cases where retry is NOT attempted."""

    def test_permanent_error_raises_immediately(self):
        from skuld.retry import RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("auth failed", retryable=False),
            _make_response("should not reach"),
        ])
        retrying = RetryingLLMClient(client, sleep_func=sleep_fn)

        with pytest.raises(ProviderAPIError, match="auth failed"):
            retrying.generate(_make_request())
        assert client.call_count == 1
        assert delays == []

    def test_non_provider_error_passes_through(self):
        from skuld.retry import RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([ValueError("bad input")])
        retrying = RetryingLLMClient(client, sleep_func=sleep_fn)

        with pytest.raises(ValueError, match="bad input"):
            retrying.generate(_make_request())
        assert client.call_count == 1
        assert delays == []

    def test_token_budget_exceeded_passes_through(self):
        from skuld.retry import RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([TokenBudgetExceeded("budget blown")])
        retrying = RetryingLLMClient(client, sleep_func=sleep_fn)

        with pytest.raises(TokenBudgetExceeded, match="budget blown"):
            retrying.generate(_make_request())
        assert client.call_count == 1
        assert delays == []


class TestRetryDelayCalculation:
    """Exponential backoff delay logic."""

    def test_exponential_backoff_delays(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
        ])
        retrying = RetryingLLMClient(
            client,
            policy=RetryPolicy(max_retries=3, base_delay=1.0, jitter=False),
            sleep_func=sleep_fn,
        )

        with pytest.raises(ProviderAPIError):
            retrying.generate(_make_request())

        # attempt 0 → 1.0, attempt 1 → 2.0, attempt 2 → 4.0
        assert delays == [1.0, 2.0, 4.0]

    def test_max_delay_cap_is_respected(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
        ])
        retrying = RetryingLLMClient(
            client,
            policy=RetryPolicy(max_retries=3, base_delay=10.0, max_delay=15.0, jitter=False),
            sleep_func=sleep_fn,
        )

        with pytest.raises(ProviderAPIError):
            retrying.generate(_make_request())

        # attempt 0 → 10.0, attempt 1 → min(20, 15)=15, attempt 2 → min(40, 15)=15
        assert delays == [10.0, 15.0, 15.0]

    def test_jitter_produces_delay_in_range(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
        ])
        retrying = RetryingLLMClient(
            client,
            policy=RetryPolicy(max_retries=3, base_delay=2.0, jitter=True),
            sleep_func=sleep_fn,
        )

        with pytest.raises(ProviderAPIError):
            retrying.generate(_make_request())

        # With jitter: delay in [0, computed_delay]
        assert len(delays) == 3
        assert 0 <= delays[0] <= 2.0   # attempt 0: [0, 2.0]
        assert 0 <= delays[1] <= 4.0   # attempt 1: [0, 4.0]
        assert 0 <= delays[2] <= 8.0   # attempt 2: [0, 8.0]

    def test_no_jitter_produces_exact_delay(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("err", retryable=True),
            _make_response("ok"),
        ])
        retrying = RetryingLLMClient(
            client,
            policy=RetryPolicy(max_retries=3, base_delay=5.0, jitter=False),
            sleep_func=sleep_fn,
        )

        retrying.generate(_make_request())
        assert delays == [5.0]


class TestRetryPolicyCustomValues:
    """Custom RetryPolicy values are honored."""

    def test_custom_policy_values(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([
            ProviderAPIError("err", retryable=True),
            ProviderAPIError("err", retryable=True),
        ])
        retrying = RetryingLLMClient(
            client,
            policy=RetryPolicy(max_retries=1, base_delay=0.5, max_delay=0.5, jitter=False),
            sleep_func=sleep_fn,
        )

        with pytest.raises(ProviderAPIError):
            retrying.generate(_make_request())

        assert client.call_count == 2  # initial + 1 retry
        assert delays == [0.5]


class TestRetryComposition:
    """Composable with BudgetedLLMClient."""

    def test_composable_with_budgeted_client(self):
        from skuld.llm_client import BudgetedLLMClient
        from skuld.retry import RetryingLLMClient

        inner = FakeClient([
            ProviderAPIError("rate limit", retryable=True),
            _make_response("ok"),
        ])
        _, sleep_fn = _sleep_recorder()
        retrying = RetryingLLMClient(inner, sleep_func=sleep_fn)
        budgeted = BudgetedLLMClient(retrying, max_tokens=100_000)

        resp = budgeted.generate(_make_request())
        assert resp.content == "ok"

    def test_failed_retries_do_not_consume_budget(self):
        """Budget is only debited on successful response, not on retried failures."""
        from skuld.llm_client import BudgetedLLMClient, SharedBudget
        from skuld.retry import RetryingLLMClient, RetryPolicy

        inner = FakeClient([
            ProviderAPIError("rate limit", retryable=True),
            ProviderAPIError("timeout", retryable=True),
            _make_response("ok"),  # prompt_tokens=10, completion_tokens=5
        ])
        _, sleep_fn = _sleep_recorder()
        shared = SharedBudget(max_tokens=100_000)
        retrying = RetryingLLMClient(inner, policy=RetryPolicy(max_retries=3), sleep_func=sleep_fn)
        budgeted = BudgetedLLMClient(retrying, shared_budget=shared)

        resp = budgeted.generate(_make_request())
        assert resp.content == "ok"
        # Only the successful response's tokens counted (10 + 5 = 15)
        assert shared.used_tokens == 15


# ---------------------------------------------------------------------------
# Provider error classification (integration with real _sdk_error_map)
# ---------------------------------------------------------------------------


class TestProviderErrorClassification:
    """Provider error maps produce correct retryable flags."""

    def test_anthropic_rate_limit_is_retryable(self):
        from unittest.mock import MagicMock, patch

        from skuld.providers.anthropic_client import AnthropicLLMClient

        sdk = MagicMock()
        sdk.AuthenticationError = type("AuthenticationError", (Exception,), {})
        sdk.RateLimitError = type("RateLimitError", (Exception,), {})
        sdk.APITimeoutError = type("APITimeoutError", (Exception,), {})
        sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})

        with patch.object(AnthropicLLMClient, "__init__", lambda self: None):
            client = AnthropicLLMClient.__new__(AnthropicLLMClient)
            error_map = client._sdk_error_map(sdk)

        rate_limit_entry = [e for e in error_map if sdk.RateLimitError in e[0]][0]
        assert rate_limit_entry[2] is True

    def test_anthropic_auth_is_not_retryable(self):
        from unittest.mock import MagicMock, patch

        from skuld.providers.anthropic_client import AnthropicLLMClient

        sdk = MagicMock()
        sdk.AuthenticationError = type("AuthenticationError", (Exception,), {})
        sdk.RateLimitError = type("RateLimitError", (Exception,), {})
        sdk.APITimeoutError = type("APITimeoutError", (Exception,), {})
        sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})

        with patch.object(AnthropicLLMClient, "__init__", lambda self: None):
            client = AnthropicLLMClient.__new__(AnthropicLLMClient)
            error_map = client._sdk_error_map(sdk)

        auth_entry = [e for e in error_map if sdk.AuthenticationError in e[0]][0]
        assert auth_entry[2] is False

    def test_openai_rate_limit_is_retryable(self):
        from unittest.mock import MagicMock, patch

        from skuld.providers.openai_client import OpenAILLMClient

        sdk = MagicMock()
        sdk.AuthenticationError = type("AuthenticationError", (Exception,), {})
        sdk.RateLimitError = type("RateLimitError", (Exception,), {})
        sdk.APITimeoutError = type("APITimeoutError", (Exception,), {})
        sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})

        with patch.object(OpenAILLMClient, "__init__", lambda self: None):
            client = OpenAILLMClient.__new__(OpenAILLMClient)
            error_map = client._sdk_error_map(sdk)

        rate_limit_entry = [e for e in error_map if sdk.RateLimitError in e[0]][0]
        assert rate_limit_entry[2] is True

    def test_openai_auth_is_not_retryable(self):
        from unittest.mock import MagicMock, patch

        from skuld.providers.openai_client import OpenAILLMClient

        sdk = MagicMock()
        sdk.AuthenticationError = type("AuthenticationError", (Exception,), {})
        sdk.RateLimitError = type("RateLimitError", (Exception,), {})
        sdk.APITimeoutError = type("APITimeoutError", (Exception,), {})
        sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})

        with patch.object(OpenAILLMClient, "__init__", lambda self: None):
            client = OpenAILLMClient.__new__(OpenAILLMClient)
            error_map = client._sdk_error_map(sdk)

        auth_entry = [e for e in error_map if sdk.AuthenticationError in e[0]][0]
        assert auth_entry[2] is False

    def test_anthropic_server_error_is_retryable(self):
        from unittest.mock import MagicMock, patch

        from skuld.providers.anthropic_client import AnthropicLLMClient

        sdk = MagicMock()
        sdk.AuthenticationError = type("AuthenticationError", (Exception,), {})
        sdk.RateLimitError = type("RateLimitError", (Exception,), {})
        sdk.APITimeoutError = type("APITimeoutError", (Exception,), {})
        sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})
        sdk.InternalServerError = type("InternalServerError", (Exception,), {})
        sdk.OverloadedError = type("OverloadedError", (Exception,), {})

        with patch.object(AnthropicLLMClient, "__init__", lambda self: None):
            client = AnthropicLLMClient.__new__(AnthropicLLMClient)
            error_map = client._sdk_error_map(sdk)

        server_entry = [e for e in error_map if sdk.InternalServerError in e[0]][0]
        assert server_entry[2] is True
        assert sdk.OverloadedError in server_entry[0]

    def test_openai_server_error_is_retryable(self):
        from unittest.mock import MagicMock, patch

        from skuld.providers.openai_client import OpenAILLMClient

        sdk = MagicMock()
        sdk.AuthenticationError = type("AuthenticationError", (Exception,), {})
        sdk.RateLimitError = type("RateLimitError", (Exception,), {})
        sdk.APITimeoutError = type("APITimeoutError", (Exception,), {})
        sdk.APIConnectionError = type("APIConnectionError", (Exception,), {})
        sdk.InternalServerError = type("InternalServerError", (Exception,), {})

        with patch.object(OpenAILLMClient, "__init__", lambda self: None):
            client = OpenAILLMClient.__new__(OpenAILLMClient)
            error_map = client._sdk_error_map(sdk)

        server_entry = [e for e in error_map if sdk.InternalServerError in e[0]][0]
        assert server_entry[2] is True


# ---------------------------------------------------------------------------
# RetryPolicy validation
# ---------------------------------------------------------------------------


class TestRetryPolicyValidation:
    """RetryPolicy rejects invalid configuration."""

    def test_negative_max_retries_raises_value_error(self):
        from skuld.retry import RetryPolicy

        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            RetryPolicy(max_retries=-1)

    def test_negative_base_delay_raises_value_error(self):
        from skuld.retry import RetryPolicy

        with pytest.raises(ValueError, match="base_delay must be >= 0"):
            RetryPolicy(base_delay=-1.0)

    def test_negative_max_delay_raises_value_error(self):
        from skuld.retry import RetryPolicy

        with pytest.raises(ValueError, match="max_delay must be >= 0"):
            RetryPolicy(max_delay=-5.0)

    def test_zero_max_retries_is_valid(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([_make_response("immediate")])
        policy = RetryPolicy(max_retries=0)
        retrying = RetryingLLMClient(client, policy=policy, sleep_func=sleep_fn)

        resp = retrying.generate(_make_request())
        assert resp.content == "immediate"
        assert client.call_count == 1
        assert delays == []

    def test_zero_max_retries_raises_on_first_retryable_error(self):
        from skuld.retry import RetryPolicy, RetryingLLMClient

        delays, sleep_fn = _sleep_recorder()
        client = FakeClient([ProviderAPIError("fail", retryable=True)])
        policy = RetryPolicy(max_retries=0)
        retrying = RetryingLLMClient(client, policy=policy, sleep_func=sleep_fn)

        with pytest.raises(ProviderAPIError, match="fail"):
            retrying.generate(_make_request())
        assert client.call_count == 1
        assert delays == []
