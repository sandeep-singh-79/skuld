"""LLM client abstraction for Skuld."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from skuld.models import GenerationRequest, GenerationResponse


class TokenBudgetExceeded(RuntimeError):
    """Raised when cumulative tokens exceed the configured budget.

    Attributes:
        response: The GenerationResponse that caused the overshoot (if any).
                  Allows callers to salvage useful work from the final call.
    """

    def __init__(self, message: str, response: GenerationResponse | None = None):
        super().__init__(message)
        self.response = response


class TruncatedResponseError(RuntimeError):
    """Raised when LLM response was truncated (finish_reason != 'stop')."""


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic LLM interface."""

    def generate(self, request: GenerationRequest) -> GenerationResponse: ...


class SharedBudget:
    """Mutable token counter shared across multiple BudgetedLLMClient instances.

    Budget tracks only successful responses. Failed attempts (e.g. retried
    provider errors) do not consume budget because provider exceptions do
    not carry reliable token usage metadata.
    """

    def __init__(self, max_tokens: int = 32_000):
        self.max_tokens = max_tokens
        self.used_tokens = 0

    def reset(self) -> None:
        """Reset the token counter."""
        self.used_tokens = 0


class BudgetedLLMClient:
    """Wraps an LLMClient with token budget enforcement.

    When ``shared_budget`` is provided, multiple instances share the same
    token counter — useful for enforcing a per-run budget across generator,
    reviewer, and refinement phases.
    """

    def __init__(
        self,
        client: LLMClient,
        max_tokens: int = 32_000,
        shared_budget: SharedBudget | None = None,
    ):
        self._client = client
        self._budget = shared_budget or SharedBudget(max_tokens)

    @property
    def used_tokens(self) -> int:
        return self._budget.used_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(0, self._budget.max_tokens - self._budget.used_tokens)

    def reset(self) -> None:
        """Reset the token counter. Use for multi-story runs in one session."""
        self._budget.reset()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if self._budget.used_tokens >= self._budget.max_tokens:
            raise TokenBudgetExceeded(
                f"Token budget exhausted: {self._budget.used_tokens}/{self._budget.max_tokens} used"
            )
        response = self._client.generate(request)
        prompt_tokens = response.prompt_tokens or 0
        completion_tokens = response.completion_tokens or 0
        self._budget.used_tokens += prompt_tokens + completion_tokens
        if self._budget.used_tokens > self._budget.max_tokens:
            raise TokenBudgetExceeded(
                f"Token budget exceeded: {self._budget.used_tokens}/{self._budget.max_tokens} used",
                response=response,
            )
        if response.finish_reason != "stop":
            raise TruncatedResponseError(
                f"LLM response truncated (finish_reason={response.finish_reason!r})"
            )
        return response


class FakeLLMClient:
    """Deterministic test double — returns configurable responses.

    Supports both a single fixed response and a sequence of responses for
    multi-call workflows (e.g. Generator → Reviewer).
    """

    def __init__(
        self,
        response_content: str = "fake response",
        model: str = "fake-model",
        provider: str = "fake",
        prompt_tokens: int = 100,
        completion_tokens: int = 200,
        finish_reason: str = "stop",
        responses: list[str] | None = None,
        error: Exception | None = None,
    ):
        self._response_content = response_content
        self._responses = responses  # sequential responses (takes priority)
        self._model = model
        self._provider = provider
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._finish_reason = finish_reason
        self._error = error  # if set, generate() raises this
        self.call_count = 0
        self.last_request: GenerationRequest | None = None
        self.all_requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        self.last_request = request
        self.all_requests.append(request)
        if self._error:
            raise self._error
        content = self._response_content
        if self._responses:
            idx = min(self.call_count - 1, len(self._responses) - 1)
            content = self._responses[idx]
        return GenerationResponse(
            content=content,
            model=self._model,
            provider=self._provider,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            finish_reason=self._finish_reason,
        )
