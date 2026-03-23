import json
import os
import sqlite3
from unittest.mock import patch

import pytest

from context_scribe.observer.antigravity_provider import AntigravityProvider


CHAT_STATE_KEY = "workbench.panel.aichat.view.aichat.chatdata"


def write_chat_db(db_path, chat_payload):
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
        connection.execute(
            "INSERT INTO ItemTable(key, value) VALUES (?, ?)",
            (CHAT_STATE_KEY, json.dumps(chat_payload)),
        )
        connection.commit()
    finally:
        connection.close()


def test_antigravity_provider_uses_workspace_storage_dir(tmp_path):
    provider = AntigravityProvider(workspace_storage_dir=str(tmp_path))

    assert provider.tool_name == "antigravity"
    assert provider.default_log_dir == str(tmp_path)
    assert provider.workspace_storage_dirs == [tmp_path]


def test_antigravity_provider_reads_user_messages_from_sqlite(tmp_path):
    workspace_dir = tmp_path / "workspaceStorage"
    session_dir = workspace_dir / "workspace-1"
    session_dir.mkdir(parents=True)
    db_path = session_dir / "state.vscdb"
    write_chat_db(
        db_path,
        {
            "sessions": [
                {
                    "workspaceFolder": "/tmp/demo-project",
                    "requests": [
                        {
                            "requestId": "req-1",
                            "request": {"text": "Pull the Antigravity chat"},
                        }
                    ],
                }
            ]
        },
    )

    provider = AntigravityProvider(workspace_storage_dir=str(workspace_dir))
    provider.processed_message_ids.clear()

    provider._process_db(str(db_path))

    assert len(provider.interaction_queue) == 1
    assert provider.interaction_queue[0].content == "Pull the Antigravity chat"
    assert provider.interaction_queue[0].project_name == "demo-project"


def test_antigravity_provider_dedupes_sqlite_messages(tmp_path):
    workspace_dir = tmp_path / "workspaceStorage"
    session_dir = workspace_dir / "workspace-1"
    session_dir.mkdir(parents=True)
    db_path = session_dir / "state.vscdb"
    write_chat_db(
        db_path,
        {
            "conversations": [
                {
                    "workspacePath": "/tmp/demo-project",
                    "messages": [
                        {
                            "id": "msg-1",
                            "role": "user",
                            "content": "Only once",
                        }
                    ],
                }
            ]
        },
    )

    provider = AntigravityProvider(workspace_storage_dir=str(workspace_dir))
    provider.processed_message_ids.clear()

    provider._process_db(str(db_path))
    provider._process_db(str(db_path))

    assert len(provider.interaction_queue) == 1


@pytest.mark.timeout(5)
def test_antigravity_provider_watch_scans_state_db(tmp_path):
    workspace_dir = tmp_path / "workspaceStorage"
    session_dir = workspace_dir / "workspace-1"
    session_dir.mkdir(parents=True)
    db_path = session_dir / "state.vscdb"
    write_chat_db(
        db_path,
        {
            "sessions": [
                {
                    "workspaceFolder": "/tmp/demo-project",
                    "requests": [
                        {
                            "requestId": "req-2",
                            "request": {"text": "Watched from sqlite"},
                        }
                    ],
                }
            ]
        },
    )

    provider = AntigravityProvider(workspace_storage_dir=str(workspace_dir))
    provider.processed_message_ids.clear()
    provider.last_mtimes[str(db_path)] = 0

    with patch("context_scribe.observer.antigravity_provider.Observer"):
        with patch("time.sleep", side_effect=[None, KeyboardInterrupt()]):
            gen = provider.watch()
            interaction = next(gen)

    assert interaction.content == "Watched from sqlite"
    assert interaction.project_name == "demo-project"
