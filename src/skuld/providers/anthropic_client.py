"""Anthropic LLM provider for Skuld."""
from __future__ import annotations

from skuld.models import GenerationRequest
from skuld.providers.base import BaseLLMProvider, ProviderAPIError


class AnthropicAPIError(ProviderAPIError):
    """Raised when the Anthropic API call fails."""


class AnthropicLLMClient(BaseLLMProvider):
    """LLM client backed by the Anthropic Messages API."""

    _ENV_VAR = "SKULD_ANTHROPIC_KEY"
    _PROVIDER_NAME = "anthropic"
    _DISPLAY_NAME = "Anthropic"
    _PACKAGE_NAME = "anthropic"
    _INSTALL_HINT = "pip install skuld[anthropic]"
    _DEFAULT_MODEL = "claude-sonnet-4-20250514"
    _ERROR_CLASS = AnthropicAPIError

    _STOP_REASON_MAP: dict[str, str] = {
        "end_turn": "stop",
        "max_tokens": "length",
    }

    def _create_sdk_client(self, sdk_module, api_key: str):
        return sdk_module.Anthropic(api_key=api_key)

    def _call_api(self, request: GenerationRequest):
        return self._sdk_client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=[{
                "type": "text",
                "text": request.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": request.user_prompt}],
        )

    def _extract_response(self, raw_response) -> tuple[str, str, int, int, str]:
        if not raw_response.content:
            raise self._make_error("Anthropic returned empty content blocks")

        text_parts = [
            block.text for block in raw_response.content if hasattr(block, "text")
        ]
        if not text_parts:
            raise self._make_error(
                "Anthropic response contained no text content blocks"
            )
        text = "".join(text_parts)

        raw_reason = raw_response.stop_reason or "end_turn"
        finish_reason = self._STOP_REASON_MAP.get(raw_reason, raw_reason)

        prompt_tokens = (
            raw_response.usage.input_tokens
            + getattr(raw_response.usage, "cache_creation_input_tokens", 0)
            + getattr(raw_response.usage, "cache_read_input_tokens", 0)
        )

        return (
            text,
            raw_response.model,
            prompt_tokens,
            raw_response.usage.output_tokens,
            finish_reason,
        )

    def _sdk_error_map(self, sdk) -> list[tuple[tuple, str]]:
        return [
            (
                (sdk.AuthenticationError,),
                "Anthropic API key is invalid or expired. "
                "Verify SKULD_ANTHROPIC_KEY is correct.",
            ),
            (
                (sdk.RateLimitError,),
                "Anthropic rate limit exceeded. Wait a moment and retry, "
                "or use a smaller model (e.g. claude-haiku-4-20250514).",
            ),
            (
                (sdk.APITimeoutError, sdk.APIConnectionError),
                "Could not connect to Anthropic API. "
                "Check your network connection and try again.",
            ),
        ]
