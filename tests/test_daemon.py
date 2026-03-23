import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from context_scribe.evaluator.llm import RuleOutput
from context_scribe.main import run_daemon
from context_scribe.observer.provider import Interaction


def test_run_daemon_loop_one_iteration():
    mock_provider = MagicMock()
    mock_evaluator = MagicMock()
    mock_mcp = AsyncMock()

    mock_interaction = Interaction(
        timestamp=None,
        role="user",
        content="New Rule",
        project_name="p1",
    )

    def mock_watch():
        yield mock_interaction
        yield None
        raise KeyboardInterrupt()

    mock_provider.watch.return_value = mock_watch()
    mock_evaluator.evaluate_interaction.return_value = RuleOutput(
        scope="GLOBAL",
        content="Extracted Rule",
        description="Added new rule",
    )
    mock_mcp.read_rules.return_value = ""

    processed_interaction = False

    async def save_rule_side_effect(*args, **kwargs):
        nonlocal processed_interaction
        processed_interaction = True
        return MagicMock()

    mock_mcp.save_rule.side_effect = save_rule_side_effect

    with patch("context_scribe.main.GeminiProvider", return_value=mock_provider):
        with patch("context_scribe.main.Evaluator", return_value=mock_evaluator):
            with patch("context_scribe.main.MemoryBankClient", return_value=mock_mcp):
                with patch("context_scribe.main.bootstrap_global_config"):
                    with patch("context_scribe.main.Live") as mock_live:
                        with patch("os._exit"):
                            mock_live.return_value.__enter__.return_value = MagicMock()

                            async def exercise_daemon():
                                daemon_task = asyncio.create_task(run_daemon("gemini", "~/.memory-bank"))
                                for _ in range(50):
                                    if processed_interaction:
                                        break
                                    await asyncio.sleep(0.1)

                                daemon_task.cancel()
                                try:
                                    await daemon_task
                                except asyncio.CancelledError:
                                    pass

                            asyncio.run(exercise_daemon())

    mock_mcp.connect.assert_called_once()
    mock_mcp.read_rules.assert_called()
    mock_evaluator.evaluate_interaction.assert_called()
    mock_mcp.save_rule.assert_called_once_with("Extracted Rule", "global", "global_rules.md")


def test_run_daemon_cursor_uses_cursor_provider():
    mock_provider = MagicMock()
    mock_mcp = AsyncMock()

    def mock_watch():
        yield None
        raise KeyboardInterrupt()

    mock_provider.watch.return_value = mock_watch()

    with patch("context_scribe.main.CursorProvider", return_value=mock_provider):
        with patch("context_scribe.main.Evaluator"):
            with patch("context_scribe.main.MemoryBankClient", return_value=mock_mcp):
                with patch("context_scribe.main.bootstrap_global_config"):
                    with patch("context_scribe.main.Live") as mock_live:
                        mock_live.return_value.__enter__.return_value = MagicMock()
                        result = asyncio.run(run_daemon("cursor", "~/.memory-bank"))

    assert result is True
    mock_mcp.connect.assert_called_once()
