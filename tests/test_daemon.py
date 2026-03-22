import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from context_scribe.main import run_daemon
from context_scribe.observer.provider import Interaction
from context_scribe.evaluator.llm import RuleOutput

@pytest.mark.asyncio
async def test_run_daemon_loop_one_iteration():
    # Mock dependencies
    mock_provider = MagicMock()
    mock_evaluator = MagicMock()
    mock_mcp = AsyncMock()
    
    # Setup interaction
    mock_interaction = Interaction(
        timestamp=None, 
        role="user", 
        content="New Rule", 
        project_name="p1"
    )
    
    # Mock watch iterator: yield one interaction then raise KeyboardInterrupt
    def mock_watch():
        yield mock_interaction
        raise KeyboardInterrupt()
    
    mock_provider.watch.return_value = mock_watch()
    
    # Correct RuleOutput with description
    mock_rule_output = RuleOutput(scope="GLOBAL", content="Extracted Rule", description="Added new rule")
    mock_evaluator.evaluate_interaction.return_value = mock_rule_output
    
    # Mock read_rules
    mock_mcp.read_rules.return_value = ""
    
    with patch("context_scribe.main.GeminiProvider", return_value=mock_provider):
        with patch("context_scribe.main.Evaluator", return_value=mock_evaluator):
            with patch("context_scribe.main.MemoryBankClient", return_value=mock_mcp):
                with patch("context_scribe.main.bootstrap_global_config"):
                    # Mock Live to avoid rich rendering logic completely
                    with patch("context_scribe.main.Live") as mock_live:
                        # Make the context manager work
                        mock_live.return_value.__enter__.return_value = MagicMock()
                        
                        # run_daemon should return True on KeyboardInterrupt
                        result = await run_daemon("gemini")
                        assert result is True
                        
                        # Verify calls
                        mock_mcp.connect.assert_called_once()
                        mock_mcp.read_rules.assert_called()
                        mock_evaluator.evaluate_interaction.assert_called()
                        mock_mcp.save_rule.assert_called_once_with("Extracted Rule", "global", "global_rules.md")
