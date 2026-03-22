import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from context_scribe.bridge.mcp_client import MemoryBankClient

@pytest.mark.asyncio
async def test_mcp_client_read_rules_success():
    client = MemoryBankClient()
    client.session = AsyncMock()
    
    mock_res = MagicMock()
    mock_res.isError = False
    mock_content = MagicMock()
    mock_content.text = "Existing content"
    mock_res.content = [mock_content]
    client.session.call_tool.return_value = mock_res
    
    content = await client.read_rules("project", "file.md")
    assert content == "Existing content"
    client.session.call_tool.assert_called_once_with(
        "memory_bank_read",
        arguments={"projectName": "project", "fileName": "file.md"}
    )

@pytest.mark.asyncio
async def test_mcp_client_save_rule_update_success():
    client = MemoryBankClient()
    client.session = AsyncMock()
    
    mock_res = MagicMock()
    mock_res.isError = False
    client.session.call_tool.return_value = mock_res
    
    result = await client.save_rule("New Content", "project", "file.md")
    assert result == mock_res
    client.session.call_tool.assert_called_once_with(
        "memory_bank_update",
        arguments={"projectName": "project", "fileName": "file.md", "content": "New Content"}
    )

@pytest.mark.asyncio
async def test_mcp_client_connect_failure():
    client = MemoryBankClient()
    # Mocking the actual import path used in mcp_client.py
    with patch("context_scribe.bridge.mcp_client.stdio_client", side_effect=Exception("Conn error")):
        with pytest.raises(Exception, match="Conn error"):
            await client.connect()

@pytest.mark.asyncio
async def test_mcp_client_read_rules_no_session():
    client = MemoryBankClient()
    # session is None
    content = await client.read_rules()
    assert content == ""

@pytest.mark.asyncio
async def test_mcp_client_save_rule_no_session():
    client = MemoryBankClient()
    with pytest.raises(RuntimeError, match="Not connected"):
        await client.save_rule("content")

@pytest.mark.asyncio
async def test_mcp_client_save_rule_all_fails():
    client = MemoryBankClient()
    client.session = AsyncMock()
    
    # Both tools fail with exceptions
    client.session.call_tool.side_effect = Exception("Fatal")
    
    result = await client.save_rule("content")
    assert result is None
