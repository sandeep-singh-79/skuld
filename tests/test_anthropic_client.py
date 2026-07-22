"""Tests for skuld.providers.anthropic_client — Anthropic LLM provider."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from skuld.models import GenerationRequest, GenerationResponse


class TestAnthropicLLMClientProtocol:
    """AnthropicLLMClient satisfies the LLMClient protocol."""

    def test_is_protocol_compliant(self):
        from skuld.llm_client import LLMClient
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test-key"}):
            client = AnthropicLLMClient()
        assert isinstance(client, LLMClient)


class TestAnthropicLLMClientInit:
    """Initialization and API key handling."""

    def test_raises_without_api_key(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SKULD_ANTHROPIC_KEY"):
                AnthropicLLMClient()

    def test_reads_api_key_from_env(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-ant-test123"}):
            client = AnthropicLLMClient()
        # Key is consumed — not exposed as a public attribute
        assert not hasattr(client, "api_key")

    def test_explicit_api_key_parameter(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        env_without_key = {k: v for k, v in os.environ.items() if k != "SKULD_ANTHROPIC_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            client = AnthropicLLMClient(api_key="sk-explicit-key")
        assert client.model == "claude-sonnet-4-20250514"

    def test_explicit_api_key_takes_precedence_over_env(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient
        from unittest.mock import patch as mock_patch

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-env-key"}):
            with mock_patch("anthropic.Anthropic") as mock_cls:
                AnthropicLLMClient(api_key="sk-explicit-key")
                mock_cls.assert_called_once_with(api_key="sk-explicit-key")

    def test_default_model(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            client = AnthropicLLMClient()
        assert client.model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            client = AnthropicLLMClient(model="claude-haiku-4-20250514")
        assert client.model == "claude-haiku-4-20250514"

    def test_default_max_tokens(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            client = AnthropicLLMClient()
        assert client.max_tokens == 4096

    def test_custom_max_tokens(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            client = AnthropicLLMClient(max_tokens=8192)
        assert client.max_tokens == 8192

    def test_default_temperature(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            client = AnthropicLLMClient()
        assert client.temperature == 0.7

    def test_custom_temperature(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            client = AnthropicLLMClient(temperature=0.2)
        assert client.temperature == 0.2

    def test_raises_when_anthropic_not_installed(self):
        import builtins

        from skuld.providers.anthropic_client import AnthropicLLMClient

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ModuleNotFoundError("No module named 'anthropic'")
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            with patch("builtins.__import__", side_effect=mock_import):
                with pytest.raises(ValueError, match="pip install skuld"):
                    AnthropicLLMClient()

    def test_rejects_empty_string_api_key(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-env-key"}):
            with pytest.raises(ValueError, match="empty"):
                AnthropicLLMClient(api_key="")

    def test_rejects_whitespace_only_api_key(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-env-key"}):
            with pytest.raises(ValueError, match="empty"):
                AnthropicLLMClient(api_key="   ")


class TestAnthropicLLMClientGenerate:
    """generate() method — mocked Anthropic SDK calls."""

    def _make_client(self):
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            return AnthropicLLMClient()

    def _mock_anthropic_response(
        self,
        text: str = "Generated test cases",
        input_tokens: int = 150,
        output_tokens: int = 300,
        stop_reason: str = "end_turn",
        model: str = "claude-sonnet-4-20250514",
    ):
        """Create a mock Anthropic API response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=text)]
        mock_response.model = model
        mock_response.usage.input_tokens = input_tokens
        mock_response.usage.output_tokens = output_tokens
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.stop_reason = stop_reason
        return mock_response

    def test_generate_returns_generation_response(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response()

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="You are a tester", user_prompt="Generate tests")
            resp = client.generate(req)

        assert isinstance(resp, GenerationResponse)
        assert resp.content == "Generated test cases"
        assert resp.provider == "anthropic"
        assert resp.model == "claude-sonnet-4-20250514"
        assert resp.prompt_tokens == 150
        assert resp.completion_tokens == 300
        assert resp.finish_reason == "stop"

    def test_generate_passes_system_and_user_prompts(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response()

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp) as mock_create:
            req = GenerationRequest(system_prompt="Be a QE expert", user_prompt="Write edge cases")
            client.generate(req)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["system"] == [{
            "type": "text",
            "text": "Be a QE expert",
            "cache_control": {"type": "ephemeral"},
        }]
        assert call_kwargs["messages"] == [{"role": "user", "content": "Write edge cases"}]

    def test_generate_includes_cache_control_on_system_prompt(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response()

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp) as mock_create:
            req = GenerationRequest(system_prompt="System text", user_prompt="User text")
            client.generate(req)

        call_kwargs = mock_create.call_args[1]
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert len(system) == 1
        assert system[0]["type"] == "text"
        assert system[0]["text"] == "System text"
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_generate_passes_model_and_params(self):
        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            from skuld.providers.anthropic_client import AnthropicLLMClient

            client = AnthropicLLMClient(model="claude-haiku-4-20250514", max_tokens=2048, temperature=0.3)

        mock_resp = self._mock_anthropic_response(model="claude-haiku-4-20250514")

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp) as mock_create:
            req = GenerationRequest(system_prompt="sys", user_prompt="usr")
            client.generate(req)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-20250514"
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["temperature"] == 0.3

    def test_generate_maps_end_turn_to_stop(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response(stop_reason="end_turn")

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "stop"

    def test_generate_maps_max_tokens_to_length(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response(stop_reason="max_tokens")

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "length"

    def test_generate_maps_unknown_stop_reason(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response(stop_reason="stop_sequence")

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "stop_sequence"

    def test_generate_propagates_api_errors(self):
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()

        with patch.object(
            client._sdk_client.messages,
            "create",
            side_effect=Exception("Connection refused"),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="Connection refused") as exc_info:
                client.generate(req)
            assert exc_info.value.__cause__ is not None

    def test_generate_auth_error_gives_actionable_message(self):
        import anthropic

        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "invalid x-api-key"}}

        with patch.object(
            client._sdk_client.messages,
            "create",
            side_effect=anthropic.AuthenticationError(
                message="invalid x-api-key", response=mock_resp, body=None
            ),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="invalid or expired"):
                client.generate(req)

    def test_generate_rate_limit_gives_actionable_message(self):
        import anthropic

        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch.object(
            client._sdk_client.messages,
            "create",
            side_effect=anthropic.RateLimitError(
                message="rate limited", response=mock_resp, body=None
            ),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="rate limit exceeded"):
                client.generate(req)

    def test_generate_timeout_gives_actionable_message(self):
        import anthropic

        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()

        with patch.object(
            client._sdk_client.messages,
            "create",
            side_effect=anthropic.APITimeoutError(request=MagicMock()),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="Could not connect"):
                client.generate(req)

    def test_generate_connection_error_gives_actionable_message(self):
        import anthropic

        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()

        with patch.object(
            client._sdk_client.messages,
            "create",
            side_effect=anthropic.APIConnectionError(request=MagicMock()),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="Check your network"):
                client.generate(req)

    def test_generate_wraps_malformed_response_attribute_error(self):
        """Response processing errors (e.g. usage=None) are wrapped in AnthropicAPIError."""
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="ok")]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage = None  # will cause AttributeError on .input_tokens
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError):
                client.generate(req)

    def test_generate_handles_none_content(self):
        """response.content = None (not just empty list)."""
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.content = None
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 50
        mock_resp.usage.output_tokens = 0
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="empty"):
                client.generate(req)

    def test_generate_rejects_empty_text_response(self):
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="")]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 10
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="empty text"):
                client.generate(req)

    def test_generate_rejects_whitespace_only_text_response(self):
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="   \n  \t  ")]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 10
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="empty text"):
                client.generate(req)
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.content = []  # empty content blocks
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 50
        mock_resp.usage.output_tokens = 0
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="empty"):
                client.generate(req)

    def test_generate_concatenates_multiple_content_blocks(self):
        client = self._make_client()
        mock_resp = MagicMock()
        block1 = MagicMock()
        block1.text = "Part 1. "
        block2 = MagicMock()
        block2.text = "Part 2."
        mock_resp.content = [block1, block2]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 200
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.content == "Part 1. Part 2."

    def test_generate_skips_non_text_content_blocks(self):
        client = self._make_client()
        mock_resp = MagicMock()
        text_block = MagicMock()
        text_block.text = "Test cases here"
        tool_block = MagicMock(spec=["type", "id", "name", "input"])  # no .text
        mock_resp.content = [tool_block, text_block]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 200
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.content == "Test cases here"

    def test_generate_raises_when_only_non_text_blocks(self):
        from skuld.providers.anthropic_client import AnthropicAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        tool_block = MagicMock(spec=["type", "id", "name", "input"])
        mock_resp.content = [tool_block]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 50
        mock_resp.usage.output_tokens = 10
        mock_resp.stop_reason = "end_turn"

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(AnthropicAPIError, match="no text"):
                client.generate(req)

    def test_generate_handles_none_stop_reason(self):
        client = self._make_client()
        mock_resp = self._mock_anthropic_response(stop_reason=None)
        # Override stop_reason to None explicitly
        mock_resp.stop_reason = None

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "stop"  # None → treated as end_turn → "stop"

    def test_generate_counts_cache_creation_tokens(self):
        """Cache creation tokens are included in prompt_tokens."""
        client = self._make_client()
        mock_resp = self._mock_anthropic_response()
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.cache_creation_input_tokens = 500
        mock_resp.usage.cache_read_input_tokens = 0

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.prompt_tokens == 600  # 100 + 500 + 0

    def test_generate_counts_cache_read_tokens(self):
        """Cache read tokens are included in prompt_tokens."""
        client = self._make_client()
        mock_resp = self._mock_anthropic_response()
        mock_resp.usage.input_tokens = 50
        mock_resp.usage.cache_creation_input_tokens = 0
        mock_resp.usage.cache_read_input_tokens = 450

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.prompt_tokens == 500  # 50 + 0 + 450

    def test_generate_handles_missing_cache_fields(self):
        """Works when cache fields are absent (non-caching API versions)."""
        client = self._make_client()
        mock_resp = self._mock_anthropic_response()
        # Create usage mock without cache fields
        mock_usage = MagicMock(spec=["input_tokens", "output_tokens"])
        mock_usage.input_tokens = 200
        mock_usage.output_tokens = 300
        mock_resp.usage = mock_usage

        with patch.object(client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.prompt_tokens == 200


class TestAnthropicWithBudgetedClient:
    """Integration: BudgetedLLMClient wrapping AnthropicLLMClient."""

    def test_budgeted_wrapping_works(self):
        from skuld.llm_client import BudgetedLLMClient
        from skuld.providers.anthropic_client import AnthropicLLMClient

        with patch.dict(os.environ, {"SKULD_ANTHROPIC_KEY": "sk-test"}):
            anthropic_client = AnthropicLLMClient()
        budgeted = BudgetedLLMClient(anthropic_client, max_tokens=10_000)

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="response")]
        mock_resp.model = "claude-sonnet-4-20250514"
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 200
        mock_resp.usage.cache_creation_input_tokens = 0
        mock_resp.usage.cache_read_input_tokens = 0
        mock_resp.stop_reason = "end_turn"

        with patch.object(anthropic_client._sdk_client.messages, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = budgeted.generate(req)

        assert resp.content == "response"
        assert budgeted.used_tokens == 300
        assert budgeted.remaining_tokens == 9700
