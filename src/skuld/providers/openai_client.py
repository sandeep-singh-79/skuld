"""OpenAI LLM provider for Skuld."""
from __future__ import annotations

from skuld.models import GenerationRequest
from skuld.providers.base import BaseLLMProvider, ProviderAPIError


class OpenAIAPIError(ProviderAPIError):
    """Raised when the OpenAI API call fails."""


class OpenAILLMClient(BaseLLMProvider):
    """LLM client backed by the OpenAI Chat Completions API."""

    _ENV_VAR = "SKULD_OPENAI_KEY"
    _PROVIDER_NAME = "openai"
    _DISPLAY_NAME = "OpenAI"
    _PACKAGE_NAME = "openai"
    _INSTALL_HINT = "pip install skuld[openai]"
    _DEFAULT_MODEL = "gpt-4o"
    _ERROR_CLASS = OpenAIAPIError

    def _create_sdk_client(self, sdk_module, api_key: str):
        return sdk_module.OpenAI(api_key=api_key)

    def _call_api(self, request: GenerationRequest):
        return self._sdk_client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        )

    def _extract_response(self, raw_response) -> tuple[str, str, int, int, str]:
        if not raw_response.choices:
            raise self._make_error("OpenAI returned empty choices")

        content = raw_response.choices[0].message.content
        if content is None:
            raise self._make_error("OpenAI returned None content")

        finish_reason = raw_response.choices[0].finish_reason or "stop"

        return (
            content,
            raw_response.model,
            raw_response.usage.prompt_tokens,
            raw_response.usage.completion_tokens,
            finish_reason,
        )

    def _sdk_error_map(self, sdk) -> list[tuple[tuple, str]]:
        return [
            (
                (sdk.AuthenticationError,),
                "OpenAI API key is invalid or expired. "
                "Verify SKULD_OPENAI_KEY is correct.",
            ),
            (
                (sdk.RateLimitError,),
                "OpenAI rate limit exceeded. Wait a moment and retry, "
                "or use a smaller model.",
            ),
            (
                (sdk.APITimeoutError, sdk.APIConnectionError),
                "Could not connect to OpenAI API. "
                "Check your network connection and try again.",
            ),
        ]
