import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from context_scribe.main import run_daemon


def test_run_daemon_mcp_connection_failure():
    mock_mcp = AsyncMock()
    mock_mcp.connect.side_effect = Exception("Connection failed")
    mock_provider = MagicMock()
    mock_provider.watch.return_value = iter([])

    with patch("context_scribe.main.MemoryBankClient", return_value=mock_mcp):
        with patch("context_scribe.main.GeminiProvider", return_value=mock_provider):
            with patch("context_scribe.main.Evaluator"):
                with patch("context_scribe.main.bootstrap_global_config"):
                    with patch("context_scribe.main.Dashboard") as mock_db_class:
                        mock_db_class.return_value.generate_layout.return_value = MagicMock()
                        with patch("os._exit", side_effect=SystemExit(1)) as mock_exit:
                            with patch("context_scribe.main.Live") as mock_live:
                                mock_live.return_value.__enter__.return_value = MagicMock()
                                try:
                                    asyncio.run(run_daemon("gemini", "~/.memory-bank"))
                                    raise AssertionError("Expected SystemExit")
                                except SystemExit:
                                    pass
                                mock_exit.assert_called_once_with(1)


def test_run_daemon_unsupported_tool():
    result = asyncio.run(run_daemon("unsupported", "~/.memory-bank"))
    assert result is False
