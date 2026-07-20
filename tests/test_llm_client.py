"""Tests for skuld.llm_client — LLM client abstraction."""
from __future__ import annotations

import pytest

from skuld.models import GenerationRequest, GenerationResponse


class TestLLMClientProtocol:
    """Protocol compliance checks."""

    def test_fake_client_is_protocol_compliant(self):
        from skuld.llm_client import FakeLLMClient, LLMClient

        client = FakeLLMClient()
        assert isinstance(client, LLMClient)

    def test_budgeted_client_is_protocol_compliant(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, LLMClient

        budgeted = BudgetedLLMClient(FakeLLMClient(), max_tokens=10_000)
        assert isinstance(budgeted, LLMClient)


class TestFakeLLMClient:
    """FakeLLMClient behaviour."""

    def test_returns_configured_response(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(response_content="hello", model="gpt-4o", provider="openai")
        req = GenerationRequest(system_prompt="sys", user_prompt="usr")
        resp = client.generate(req)
        assert resp.content == "hello"
        assert resp.model == "gpt-4o"
        assert resp.provider == "openai"

    def test_tracks_call_count(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient()
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        assert client.call_count == 0
        client.generate(req)
        client.generate(req)
        assert client.call_count == 2

    def test_tracks_last_request(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient()
        req = GenerationRequest(system_prompt="system", user_prompt="user")
        client.generate(req)
        assert client.last_request is req

    def test_default_response(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient()
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        resp = client.generate(req)
        assert resp.content == "fake response"
        assert resp.model == "fake-model"
        assert resp.provider == "fake"
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 200


class TestBudgetedLLMClient:
    """BudgetedLLMClient token budget enforcement."""

    def test_passes_through_to_underlying_client(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(response_content="delegated")
        budgeted = BudgetedLLMClient(fake, max_tokens=10_000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        resp = budgeted.generate(req)
        assert resp.content == "delegated"
        assert fake.call_count == 1

    def test_tracks_used_tokens(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(prompt_tokens=50, completion_tokens=150)
        budgeted = BudgetedLLMClient(fake, max_tokens=10_000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)
        assert budgeted.used_tokens == 200

    def test_remaining_tokens_decreases(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(prompt_tokens=100, completion_tokens=100)
        budgeted = BudgetedLLMClient(fake, max_tokens=1000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        assert budgeted.remaining_tokens == 1000
        budgeted.generate(req)
        assert budgeted.remaining_tokens == 800

    def test_budget_exceeded_raises_on_overshoot(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded

        fake = FakeLLMClient(prompt_tokens=300, completion_tokens=300)
        budgeted = BudgetedLLMClient(fake, max_tokens=500)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        with pytest.raises(TokenBudgetExceeded, match="exceeded"):
            budgeted.generate(req)

    def test_budget_exceeded_raises_on_pre_exhaustion(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded

        fake = FakeLLMClient(prompt_tokens=500, completion_tokens=500)
        budgeted = BudgetedLLMClient(fake, max_tokens=1000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)  # uses exactly 1000
        with pytest.raises(TokenBudgetExceeded, match="exhausted"):
            budgeted.generate(req)

    def test_none_tokens_treated_as_zero(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(prompt_tokens=0, completion_tokens=0)
        # Override response tokens to None via monkey-patch
        original_generate = fake.generate

        def patched_generate(request):
            resp = original_generate(request)
            return GenerationResponse(
                content=resp.content,
                model=resp.model,
                provider=resp.provider,
                prompt_tokens=None,
                completion_tokens=None,
            )

        fake.generate = patched_generate
        budgeted = BudgetedLLMClient(fake, max_tokens=1000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)
        assert budgeted.used_tokens == 0

    def test_multiple_calls_accumulate(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(prompt_tokens=50, completion_tokens=50)
        budgeted = BudgetedLLMClient(fake, max_tokens=10_000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)
        budgeted.generate(req)
        budgeted.generate(req)
        assert budgeted.used_tokens == 300
        assert budgeted.remaining_tokens == 9700

    def test_budget_overshoot_includes_response_in_exception(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded

        fake = FakeLLMClient(
            response_content="useful output",
            prompt_tokens=300,
            completion_tokens=300,
        )
        budgeted = BudgetedLLMClient(fake, max_tokens=500)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        with pytest.raises(TokenBudgetExceeded) as exc_info:
            budgeted.generate(req)
        # Response is salvageable from the exception
        assert exc_info.value.response is not None
        assert exc_info.value.response.content == "useful output"

    def test_pre_exhaustion_exception_has_no_response(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded

        fake = FakeLLMClient(prompt_tokens=500, completion_tokens=500)
        budgeted = BudgetedLLMClient(fake, max_tokens=1000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)  # uses exactly 1000
        with pytest.raises(TokenBudgetExceeded) as exc_info:
            budgeted.generate(req)
        # Pre-exhaustion means no call was made — no response
        assert exc_info.value.response is None

    def test_reset_clears_token_counter(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(prompt_tokens=100, completion_tokens=100)
        budgeted = BudgetedLLMClient(fake, max_tokens=1000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)
        assert budgeted.used_tokens == 200
        budgeted.reset()
        assert budgeted.used_tokens == 0
        assert budgeted.remaining_tokens == 1000

    def test_reset_allows_fresh_calls(self):
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(prompt_tokens=400, completion_tokens=400)
        budgeted = BudgetedLLMClient(fake, max_tokens=1000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        budgeted.generate(req)  # 800 tokens
        budgeted.reset()
        # Should succeed — budget is fresh
        resp = budgeted.generate(req)
        assert resp.content == "fake response"
        assert budgeted.used_tokens == 800


class TestFakeLLMClientSequentialResponses:
    """FakeLLMClient sequential response support."""

    def test_sequential_responses(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(responses=["first", "second", "third"])
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        assert client.generate(req).content == "first"
        assert client.generate(req).content == "second"
        assert client.generate(req).content == "third"

    def test_sequential_responses_repeats_last_when_exhausted(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(responses=["only"])
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        assert client.generate(req).content == "only"
        assert client.generate(req).content == "only"

    def test_sequential_responses_tracks_all_requests(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(responses=["a", "b"])
        req1 = GenerationRequest(system_prompt="gen", user_prompt="generate")
        req2 = GenerationRequest(system_prompt="rev", user_prompt="review")
        client.generate(req1)
        client.generate(req2)
        assert client.all_requests == [req1, req2]
        assert client.last_request is req2

    def test_fallback_to_fixed_response_when_no_sequence(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(response_content="fixed")
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        assert client.generate(req).content == "fixed"
        assert client.generate(req).content == "fixed"


class TestFakeLLMClientErrorSimulation:
    """FakeLLMClient error injection for testing failure paths."""

    def test_error_raises_on_generate(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(error=RuntimeError("API timeout"))
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        with pytest.raises(RuntimeError, match="API timeout"):
            client.generate(req)

    def test_error_still_tracks_call_count(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(error=ValueError("bad request"))
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        with pytest.raises(ValueError):
            client.generate(req)
        assert client.call_count == 1

    def test_error_still_tracks_last_request(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(error=IOError("network"))
        req = GenerationRequest(system_prompt="sys", user_prompt="usr")
        with pytest.raises(IOError):
            client.generate(req)
        assert client.last_request is req

    def test_no_error_by_default(self):
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient()
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        resp = client.generate(req)  # should not raise
        assert resp.content == "fake response"


class TestTruncatedResponseHandling:
    """BudgetedLLMClient raises TruncatedResponseError on non-stop finish_reason."""

    def test_budgeted_client_raises_on_truncated_response(self):
        """finish_reason='length' → TruncatedResponseError raised before returning."""
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TruncatedResponseError

        fake = FakeLLMClient(response_content='{"test_cases": []}', finish_reason="length")
        budgeted = BudgetedLLMClient(fake, max_tokens=32000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        with pytest.raises(TruncatedResponseError, match="finish_reason='length'"):
            budgeted.generate(req)

    def test_budgeted_client_passes_stop_reason(self):
        """finish_reason='stop' (default) → response returned normally."""
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        fake = FakeLLMClient(response_content="valid json", finish_reason="stop")
        budgeted = BudgetedLLMClient(fake, max_tokens=32000)
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        resp = budgeted.generate(req)
        assert resp.content == "valid json"
        assert resp.finish_reason == "stop"

    def test_fake_client_returns_configured_finish_reason(self):
        """FakeLLMClient propagates the configured finish_reason in the response."""
        from skuld.llm_client import FakeLLMClient

        client = FakeLLMClient(response_content="partial", finish_reason="content_filter")
        req = GenerationRequest(system_prompt="s", user_prompt="u")
        resp = client.generate(req)
        assert resp.finish_reason == "content_filter"
