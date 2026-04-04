"""
Tests for GradingAgent initialization and LLM configuration.

Verifies that the grading agent uses a dedicated LLM with higher token limits
to prevent JSON truncation during structured output parsing (fixes #346).
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGradingLLMConfiguration:
    """Test that grading uses a dedicated LLM with sufficient token capacity."""

    def test_get_grading_llm_has_higher_max_tokens(self):
        """get_grading_llm() should return an LLM with max_tokens=4096."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from common.services.simulation_helper.langchain_service import LangChainManager
            manager = LangChainManager()
            grading_llm = manager.get_grading_llm()
            assert grading_llm.max_tokens == 4096

    def test_get_grading_llm_streaming_disabled(self):
        """Grading LLM should have streaming disabled for structured output."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from common.services.simulation_helper.langchain_service import LangChainManager
            manager = LangChainManager()
            grading_llm = manager.get_grading_llm()
            assert grading_llm.streaming is False

    def test_standard_llm_has_lower_max_tokens(self):
        """Standard LLM should still use max_tokens=1000."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from common.services.simulation_helper.langchain_service import LangChainManager
            manager = LangChainManager()
            standard_llm = manager.llm
            assert standard_llm.max_tokens == 1000

    def test_grading_agent_uses_grading_llm(self):
        """GradingAgent should use get_grading_llm(), not the standard llm."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=MagicMock())

        with patch("modules.simulation.agents.grading_agent.langchain_manager") as mock_manager:
            mock_manager.get_grading_llm.return_value = mock_llm
            from modules.simulation.agents.grading_agent import GradingAgent
            agent = GradingAgent()

            mock_manager.get_grading_llm.assert_called_once()
            # Should NOT have accessed the standard .llm property
            mock_manager.llm.__get__ = MagicMock()
            assert agent.llm == mock_llm
