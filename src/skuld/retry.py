"""Retry logic for LLM provider calls."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

from skuld.llm_client import LLMClient
from skuld.models import GenerationRequest, GenerationResponse
from skuld.providers.base import ProviderAPIError


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry behaviour."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.base_delay < 0:
            raise ValueError("base_delay must be >= 0")
        if self.max_delay < 0:
            raise ValueError("max_delay must be >= 0")


class RetryingLLMClient:
    """Wraps an LLMClient with retry logic for transient errors."""

    def __init__(
        self,
        client: LLMClient,
        policy: RetryPolicy | None = None,
        sleep_func: Callable[[float], None] | None = None,
    ):
        self._client = client
        self._policy = policy or RetryPolicy()
        self._sleep = sleep_func or time.sleep

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        last_error: ProviderAPIError | None = None
        for attempt in range(1 + self._policy.max_retries):
            try:
                return self._client.generate(request)
            except ProviderAPIError as exc:
                if not exc.retryable:
                    raise
                last_error = exc
                if attempt < self._policy.max_retries:
                    delay = self._compute_delay(attempt)
                    self._sleep(delay)
        raise last_error  # type: ignore[misc]

    def _compute_delay(self, attempt: int) -> float:
        delay = min(self._policy.base_delay * (2**attempt), self._policy.max_delay)
        if self._policy.jitter:
            delay = random.uniform(0, delay)
        return delay
