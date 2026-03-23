import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from context_scribe.bridge.mcp_client import MemoryBankClient


def test_mcp_client_read_rules_success():
    client = MemoryBankClient()
    client.session = AsyncMock()

    mock_res = MagicMock()
    mock_res.isError = False
    mock_content = MagicMock()
    mock_content.text = "Existing content"
    mock_res.content = [mock_content]
    client.session.call_tool.return_value = mock_res

    content = asyncio.run(client.read_rules("project", "file.md"))
    assert content == "Existing content"
    client.session.call_tool.assert_called_once_with(
        "memory_bank_read",
        arguments={"projectName": "project", "fileName": "file.md"},
    )


def test_mcp_client_save_rule_update_success():
    client = MemoryBankClient()
    client.session = AsyncMock()

    mock_res = MagicMock()
    mock_res.isError = False
    client.session.call_tool.return_value = mock_res

    result = asyncio.run(client.save_rule("New Content", "project", "file.md"))
    assert result == mock_res
    client.session.call_tool.assert_called_once_with(
        "memory_bank_update",
        arguments={"projectName": "project", "fileName": "file.md", "content": "New Content"},
    )


def test_mcp_client_connect_failure():
    client = MemoryBankClient()
    with patch("context_scribe.bridge.mcp_client.stdio_client", side_effect=Exception("Conn error")):
        try:
            asyncio.run(client.connect())
            raise AssertionError("Expected connection failure")
        except Exception as exc:
            assert "Conn error" in str(exc)


def test_mcp_client_read_rules_no_session():
    client = MemoryBankClient()
    content = asyncio.run(client.read_rules())
    assert content == ""


def test_mcp_client_save_rule_no_session():
    client = MemoryBankClient()
    try:
        asyncio.run(client.save_rule("content"))
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert "Not connected" in str(exc)


def test_mcp_client_save_rule_all_fails():
    client = MemoryBankClient()
    client.session = AsyncMock()
    client.session.call_tool.side_effect = Exception("Fatal")

    result = asyncio.run(client.save_rule("content"))
    assert result is None
