"""T16: Architecture guardrails and coverage hardening tests.

Validates structural invariants that protect the deterministic/LLM boundary,
token budget enforcement, input limits, and resource safety.
"""
from __future__ import annotations

import importlib
import inspect
import tempfile

import pytest


class TestArchitectureGuardrails:
    """Deterministic modules must never import or reference LLM code."""

    @pytest.mark.parametrize("mod_name", [
        "skuld.rtm_builder",
        "skuld.rtm_scorer",
        "skuld.confidence_scorer",
    ])
    def test_deterministic_modules_dont_import_llm(self, mod_name):
        """rtm_builder, rtm_scorer, confidence_scorer must not import LLM code."""
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        assert "llm_client" not in source, f"{mod_name} imports llm_client"
        assert "LLMClient" not in source, f"{mod_name} references LLMClient"
        assert "FakeLLMClient" not in source, f"{mod_name} references FakeLLMClient"

    def test_token_budget_enforcement_overshoot(self):
        """Response tokens exceed remaining budget → TokenBudgetExceeded."""
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded
        from skuld.models import GenerationRequest

        inner = FakeLLMClient(response_content='{"test": true}', completion_tokens=200)
        budgeted = BudgetedLLMClient(inner, max_tokens=10)

        request = GenerationRequest(system_prompt="sys", user_prompt="user")
        with pytest.raises(TokenBudgetExceeded):
            budgeted.generate(request)

    def test_token_budget_enforcement_pre_call_exhaustion(self):
        """Budget already exhausted before the call → TokenBudgetExceeded."""
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded
        from skuld.models import GenerationRequest

        inner = FakeLLMClient(response_content='{"test": true}', prompt_tokens=0, completion_tokens=5)
        budgeted = BudgetedLLMClient(inner, max_tokens=12)

        request = GenerationRequest(system_prompt="sys", user_prompt="user")
        # First call uses 5 tokens (within budget)
        budgeted.generate(request)
        # Second call: 5 used + 5 new = 10 (within budget)
        budgeted.generate(request)
        # Third call: 10 used + 5 = 15 > 12 → raises
        with pytest.raises(TokenBudgetExceeded):
            budgeted.generate(request)

    def test_ac_count_limit_rejected(self):
        """31 ACs → InputValidationError from input_loader."""
        import yaml

        from skuld.input_loader import InputValidationError, load_input

        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [
                {"id": f"AC-{i}", "description": f"AC {i}", "criticality": "medium"}
                for i in range(31)
            ],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete_on_close=False, encoding="utf-8") as f:
            yaml.dump(data, f)
            f.flush()
            with pytest.raises(InputValidationError):
                load_input(f.name)

    def test_yaml_bomb_rejected(self):
        """File > 1MB → InputValidationError from input_loader (spec T16 contract)."""
        from skuld.input_loader import InputValidationError, load_input

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete_on_close=False, encoding="utf-8") as f:
            # Write just over 1MB of valid-ish YAML content
            f.write("story:\n  id: S-1\n  title: T\n  description: D\n")
            f.write("# padding\n" * (1024 * 1024 // 10))
            f.flush()
            with pytest.raises(InputValidationError, match="exceeds maximum size"):
                load_input(f.name)

    def test_generate_rejects_oversized_input_via_loader(self):
        """skuld generate with >1MB file exits 2 with loader's size error message."""
        from click.testing import CliRunner

        from skuld.cli import main

        runner = CliRunner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete_on_close=False, encoding="utf-8") as f:
            f.write("story:\n  id: S-1\n  title: T\n  description: D\n")
            f.write("# padding\n" * (1024 * 1024 // 10))
            f.flush()
            result = runner.invoke(main, ["generate", f.name, "--dry-run"])
        assert result.exit_code == 2
        assert "exceeds maximum size" in result.output or "1MB" in result.output
