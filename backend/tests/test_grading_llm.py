"""
Tests for grading LLM configuration and GradingAgent initialization.

Verifies that:
1. get_grading_llm() returns an LLM with max_tokens=4096 (prevents JSON truncation)
2. get_grading_llm() disables streaming (required for structured output parsing)
3. GradingAgent uses the grading LLM, not the default 1000-token LLM
4. Default LLM remains unchanged at 1000 tokens
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGradingLLMConfiguration:
    """Tests for the dedicated grading LLM in langchain_service."""

    def test_grading_llm_has_4096_max_tokens(self):
        """get_grading_llm() must return an LLM with max_tokens=4096 to prevent JSON truncation."""
        from common.services.simulation_helper.langchain_service import langchain_manager

        llm = langchain_manager.get_grading_llm()
        assert llm.max_tokens == 4096

    def test_grading_llm_streaming_disabled(self):
        """Grading LLM should have streaming=False for structured output parsing."""
        from common.services.simulation_helper.langchain_service import langchain_manager

        llm = langchain_manager.get_grading_llm()
        assert llm.streaming is False

    def test_default_llm_unchanged_at_1000_tokens(self):
        """Default LLM must remain at 1000 tokens for cost-efficient conversation use."""
        from common.services.simulation_helper.langchain_service import langchain_manager

        llm = langchain_manager.llm
        assert llm.max_tokens == 1000

    def test_default_llm_streaming_enabled(self):
        """Default LLM should still have streaming enabled."""
        from common.services.simulation_helper.langchain_service import langchain_manager

        llm = langchain_manager.llm
        assert llm.streaming is True

    def test_grading_llm_uses_same_model_as_default(self):
        """Grading LLM should use the same model as the default LLM."""
        from common.services.simulation_helper.langchain_service import langchain_manager

        default_llm = langchain_manager.llm
        grading_llm = langchain_manager.get_grading_llm()
        assert grading_llm.model_name == default_llm.model_name

    def test_grading_llm_creates_fresh_instance(self):
        """Each call to get_grading_llm() should return a new instance."""
        from common.services.simulation_helper.langchain_service import langchain_manager

        llm1 = langchain_manager.get_grading_llm()
        llm2 = langchain_manager.get_grading_llm()
        assert llm1 is not llm2


class TestGradingAgentInit:
    """Tests that GradingAgent uses the grading-specific LLM."""

    @patch("modules.simulation.agents.grading_agent.langchain_manager")
    def test_grading_agent_uses_grading_llm(self, mock_manager):
        """GradingAgent.__init__ must call get_grading_llm(), not .llm property."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        mock_manager.get_grading_llm.return_value = mock_llm

        from modules.simulation.agents.grading_agent import GradingAgent
        agent = GradingAgent()

        mock_manager.get_grading_llm.assert_called_once()
        assert agent.llm is mock_llm

    @patch("modules.simulation.agents.grading_agent.langchain_manager")
    def test_grading_agent_creates_structured_output_chains(self, mock_manager):
        """GradingAgent should create both scene_grader and overall_grader chains."""
        mock_llm = MagicMock()
        mock_scene_grader = MagicMock()
        mock_overall_grader = MagicMock()
        mock_llm.with_structured_output.side_effect = [mock_scene_grader, mock_overall_grader]
        mock_manager.get_grading_llm.return_value = mock_llm

        from modules.simulation.agents.grading_agent import GradingAgent
        agent = GradingAgent()

        assert mock_llm.with_structured_output.call_count == 2
        assert agent.scene_grader is mock_scene_grader
        assert agent.overall_grader is mock_overall_grader
