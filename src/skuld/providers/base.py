"""Base class for LLM provider implementations."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from skuld.models import GenerationRequest, GenerationResponse


class ProviderAPIError(RuntimeError):
    """Base error for all LLM provider API failures."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class BaseLLMProvider(ABC):
    """Template Method base class for LLM providers.

    Subclasses define class attributes and implement 4 abstract methods.
    The base class handles key resolution, SDK import guarding, empty-response
    validation, error wrapping, and GenerationResponse construction.
    """

    _ENV_VAR: str                          # e.g. "SKULD_ANTHROPIC_KEY"
    _PROVIDER_NAME: str                    # e.g. "anthropic"
    _DISPLAY_NAME: str                     # e.g. "Anthropic", "OpenAI"
    _PACKAGE_NAME: str                     # e.g. "anthropic"
    _INSTALL_HINT: str                     # e.g. "pip install skuld[anthropic]"
    _DEFAULT_MODEL: str                    # e.g. "claude-sonnet-4-20250514"
    _ERROR_CLASS: type[ProviderAPIError]   # e.g. AnthropicAPIError

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        resolved_key = self._resolve_key(api_key)
        sdk_module = self._import_sdk()
        self._sdk_client = self._create_sdk_client(sdk_module, resolved_key)
        self.model = model or self._DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature

    def _resolve_key(self, api_key: str | None) -> str:
        """Resolve API key from explicit param or environment variable."""
        if api_key is not None:
            resolved = api_key.strip()
            if not resolved:
                raise ValueError(
                    f"{self._DISPLAY_NAME} API key is empty. Pass a valid api_key or "
                    f"set the {self._ENV_VAR} environment variable."
                )
            return resolved

        resolved = os.environ.get(self._ENV_VAR, "").strip() or None
        if not resolved:
            raise ValueError(
                f"{self._DISPLAY_NAME} API key not provided. Pass api_key to the "
                f"constructor or set the {self._ENV_VAR} environment variable."
            )
        return resolved

    def _import_sdk(self):
        """Import and return the provider SDK module."""
        try:
            return __import__(self._PACKAGE_NAME)
        except ModuleNotFoundError:
            raise ValueError(
                f"The '{self._PACKAGE_NAME}' package is not installed. "
                f"Install it with: {self._INSTALL_HINT}"
            ) from None

    def _make_error(self, message: str, *, retryable: bool = False) -> ProviderAPIError:
        """Create a provider-specific error instance."""
        return self._ERROR_CLASS(message, retryable=retryable)

    @abstractmethod
    def _create_sdk_client(self, sdk_module, api_key: str):
        """Create the provider's SDK client instance."""

    @abstractmethod
    def _call_api(self, request: GenerationRequest):
        """Make the provider-specific API call. Return raw SDK response."""

    @abstractmethod
    def _extract_response(self, raw_response) -> tuple[str, str, int, int, str]:
        """Extract (text, model, prompt_tokens, completion_tokens, finish_reason) from raw response.

        Raise self._make_error(...) for provider-specific extraction failures
        (empty content, missing choices, etc.).
        """

    @abstractmethod
    def _sdk_error_map(self, sdk) -> list[tuple[tuple, str, bool]]:
        """Return list of (exception_types_tuple, user_message, retryable) for error wrapping.

        Called with the imported SDK module so exception classes are available.
        """

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Send a generation request to the provider API."""
        sdk = self._import_sdk()

        try:
            raw = self._call_api(request)
            text, model, prompt_tokens, completion_tokens, finish_reason = (
                self._extract_response(raw)
            )

            if not text.strip():
                raise self._make_error(
                    f"{self._DISPLAY_NAME} returned empty text response"
                )

            return GenerationResponse(
                content=text,
                model=model,
                provider=self._PROVIDER_NAME,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                finish_reason=finish_reason,
            )
        except ProviderAPIError:
            raise
        except Exception as exc:
            for exc_types, message, retryable in self._sdk_error_map(sdk):
                if isinstance(exc, exc_types):
                    raise self._make_error(message, retryable=retryable) from exc
            raise self._make_error(str(exc)) from exc
