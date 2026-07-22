"""Tests for skuld.providers.openai_client — OpenAI LLM provider."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from skuld.models import GenerationRequest, GenerationResponse


class TestOpenAILLMClientProtocol:
    """OpenAILLMClient satisfies the LLMClient protocol."""

    def test_is_protocol_compliant(self):
        from skuld.llm_client import LLMClient
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test-key"}):
            client = OpenAILLMClient()
        assert isinstance(client, LLMClient)


class TestOpenAILLMClientInit:
    """Initialization and API key handling."""

    def test_raises_without_api_key(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SKULD_OPENAI_KEY"):
                OpenAILLMClient()

    def test_reads_api_key_from_env(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-openai-test123"}):
            client = OpenAILLMClient()
        assert not hasattr(client, "api_key")

    def test_explicit_api_key_parameter(self):
        from skuld.providers.openai_client import OpenAILLMClient

        env_without_key = {k: v for k, v in os.environ.items() if k != "SKULD_OPENAI_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            client = OpenAILLMClient(api_key="sk-explicit-key")
        assert client.model == "gpt-4o"

    def test_explicit_api_key_takes_precedence_over_env(self):
        from skuld.providers.openai_client import OpenAILLMClient
        from unittest.mock import patch as mock_patch

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-env-key"}):
            with mock_patch("openai.OpenAI") as mock_cls:
                OpenAILLMClient(api_key="sk-explicit-key")
                mock_cls.assert_called_once_with(api_key="sk-explicit-key")

    def test_default_model(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            client = OpenAILLMClient()
        assert client.model == "gpt-4o"

    def test_custom_model(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            client = OpenAILLMClient(model="gpt-4o-mini")
        assert client.model == "gpt-4o-mini"

    def test_default_max_tokens(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            client = OpenAILLMClient()
        assert client.max_tokens == 4096

    def test_custom_max_tokens(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            client = OpenAILLMClient(max_tokens=8192)
        assert client.max_tokens == 8192

    def test_default_temperature(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            client = OpenAILLMClient()
        assert client.temperature == 0.7

    def test_custom_temperature(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            client = OpenAILLMClient(temperature=0.2)
        assert client.temperature == 0.2

    def test_raises_when_openai_not_installed(self):
        import builtins

        from skuld.providers.openai_client import OpenAILLMClient

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "openai":
                raise ModuleNotFoundError("No module named 'openai'")
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            with patch("builtins.__import__", side_effect=mock_import):
                with pytest.raises(ValueError, match="pip install skuld"):
                    OpenAILLMClient()

    def test_rejects_empty_string_api_key(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-env-key"}):
            with pytest.raises(ValueError, match="empty"):
                OpenAILLMClient(api_key="")

    def test_rejects_whitespace_only_api_key(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-env-key"}):
            with pytest.raises(ValueError, match="empty"):
                OpenAILLMClient(api_key="   ")


class TestOpenAILLMClientGenerate:
    """generate() method — mocked OpenAI SDK calls."""

    def _make_client(self):
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            return OpenAILLMClient()

    def _mock_openai_response(
        self,
        text: str = "Generated test cases",
        prompt_tokens: int = 150,
        completion_tokens: int = 300,
        finish_reason: str = "stop",
        model: str = "gpt-4o",
    ):
        """Create a mock OpenAI API response."""
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = text
        mock_choice.finish_reason = finish_reason
        mock_response.choices = [mock_choice]
        mock_response.model = model
        mock_response.usage.prompt_tokens = prompt_tokens
        mock_response.usage.completion_tokens = completion_tokens
        return mock_response

    def test_generate_returns_generation_response(self):
        client = self._make_client()
        mock_resp = self._mock_openai_response()

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="You are a tester", user_prompt="Generate tests")
            resp = client.generate(req)

        assert isinstance(resp, GenerationResponse)
        assert resp.content == "Generated test cases"
        assert resp.provider == "openai"
        assert resp.model == "gpt-4o"
        assert resp.prompt_tokens == 150
        assert resp.completion_tokens == 300
        assert resp.finish_reason == "stop"

    def test_generate_passes_system_and_user_prompts(self):
        client = self._make_client()
        mock_resp = self._mock_openai_response()

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp) as mock_create:
            req = GenerationRequest(system_prompt="Be a QE expert", user_prompt="Write edge cases")
            client.generate(req)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["messages"] == [
            {"role": "system", "content": "Be a QE expert"},
            {"role": "user", "content": "Write edge cases"},
        ]

    def test_generate_passes_model_and_params(self):
        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            from skuld.providers.openai_client import OpenAILLMClient

            client = OpenAILLMClient(model="gpt-4o-mini", max_tokens=2048, temperature=0.3)

        mock_resp = self._mock_openai_response(model="gpt-4o-mini")

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp) as mock_create:
            req = GenerationRequest(system_prompt="sys", user_prompt="usr")
            client.generate(req)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["temperature"] == 0.3

    def test_generate_finish_reason_stop(self):
        client = self._make_client()
        mock_resp = self._mock_openai_response(finish_reason="stop")

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "stop"

    def test_generate_finish_reason_length(self):
        client = self._make_client()
        mock_resp = self._mock_openai_response(finish_reason="length")

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "length"

    def test_generate_handles_none_finish_reason(self):
        client = self._make_client()
        mock_resp = self._mock_openai_response()
        mock_resp.choices[0].finish_reason = None

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = client.generate(req)

        assert resp.finish_reason == "stop"

    def test_generate_propagates_api_errors(self):
        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()

        with patch.object(
            client._sdk_client.chat.completions,
            "create",
            side_effect=Exception("Connection refused"),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="Connection refused") as exc_info:
                client.generate(req)
            assert exc_info.value.__cause__ is not None

    def test_generate_auth_error_gives_actionable_message(self):
        import openai

        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "invalid api key"}}

        with patch.object(
            client._sdk_client.chat.completions,
            "create",
            side_effect=openai.AuthenticationError(
                message="invalid api key", response=mock_resp, body=None
            ),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="invalid or expired"):
                client.generate(req)

    def test_generate_rate_limit_gives_actionable_message(self):
        import openai

        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch.object(
            client._sdk_client.chat.completions,
            "create",
            side_effect=openai.RateLimitError(
                message="rate limited", response=mock_resp, body=None
            ),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="rate limit exceeded"):
                client.generate(req)

    def test_generate_timeout_gives_actionable_message(self):
        import openai

        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()

        with patch.object(
            client._sdk_client.chat.completions,
            "create",
            side_effect=openai.APITimeoutError(request=MagicMock()),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="Could not connect"):
                client.generate(req)

    def test_generate_connection_error_gives_actionable_message(self):
        import openai

        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()

        with patch.object(
            client._sdk_client.chat.completions,
            "create",
            side_effect=openai.APIConnectionError(request=MagicMock()),
        ):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="Check your network"):
                client.generate(req)

    def test_generate_wraps_malformed_response_attribute_error(self):
        """Response processing errors (e.g. usage=None) are wrapped in OpenAIAPIError."""
        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_choice.finish_reason = "stop"
        mock_resp.choices = [mock_choice]
        mock_resp.model = "gpt-4o"
        mock_resp.usage = None  # will cause AttributeError on .prompt_tokens

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError):
                client.generate(req)

    def test_generate_handles_empty_choices(self):
        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.choices = []
        mock_resp.model = "gpt-4o"
        mock_resp.usage.prompt_tokens = 50
        mock_resp.usage.completion_tokens = 0

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="empty choices"):
                client.generate(req)

    def test_generate_handles_none_content(self):
        """response.choices[0].message.content = None."""
        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.finish_reason = "stop"
        mock_resp.choices = [mock_choice]
        mock_resp.model = "gpt-4o"
        mock_resp.usage.prompt_tokens = 50
        mock_resp.usage.completion_tokens = 0

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="None content"):
                client.generate(req)

    def test_generate_rejects_empty_text_response(self):
        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.finish_reason = "stop"
        mock_resp.choices = [mock_choice]
        mock_resp.model = "gpt-4o"
        mock_resp.usage.prompt_tokens = 100
        mock_resp.usage.completion_tokens = 10

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="empty text"):
                client.generate(req)

    def test_generate_rejects_whitespace_only_text_response(self):
        from skuld.providers.openai_client import OpenAIAPIError

        client = self._make_client()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "   \n  \t  "
        mock_choice.finish_reason = "stop"
        mock_resp.choices = [mock_choice]
        mock_resp.model = "gpt-4o"
        mock_resp.usage.prompt_tokens = 100
        mock_resp.usage.completion_tokens = 10

        with patch.object(client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            with pytest.raises(OpenAIAPIError, match="empty text"):
                client.generate(req)


class TestOpenAIWithBudgetedClient:
    """Integration: BudgetedLLMClient wrapping OpenAILLMClient."""

    def test_budgeted_wrapping_works(self):
        from skuld.llm_client import BudgetedLLMClient
        from skuld.providers.openai_client import OpenAILLMClient

        with patch.dict(os.environ, {"SKULD_OPENAI_KEY": "sk-test"}):
            openai_client = OpenAILLMClient()
        budgeted = BudgetedLLMClient(openai_client, max_tokens=10_000)

        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "response"
        mock_choice.finish_reason = "stop"
        mock_resp.choices = [mock_choice]
        mock_resp.model = "gpt-4o"
        mock_resp.usage.prompt_tokens = 100
        mock_resp.usage.completion_tokens = 200

        with patch.object(openai_client._sdk_client.chat.completions, "create", return_value=mock_resp):
            req = GenerationRequest(system_prompt="s", user_prompt="u")
            resp = budgeted.generate(req)

        assert resp.content == "response"
        assert budgeted.used_tokens == 300
        assert budgeted.remaining_tokens == 9700
