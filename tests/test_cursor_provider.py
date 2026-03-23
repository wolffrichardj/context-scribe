import json
import sqlite3
from pathlib import Path

from context_scribe.observer.cursor_provider import CursorProvider


def create_cursor_db(db_path: Path, *, item_rows=None, kv_rows=None):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        if item_rows is not None:
            cursor.execute("CREATE TABLE ItemTable ([key] TEXT, value BLOB)")
            cursor.executemany(
                "INSERT INTO ItemTable ([key], value) VALUES (?, ?)",
                item_rows,
            )
        if kv_rows is not None:
            cursor.execute("CREATE TABLE cursorDiskKV (key TEXT, value BLOB)")
            cursor.executemany(
                "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
                kv_rows,
            )
        conn.commit()
    finally:
        conn.close()


def test_cursor_provider_extracts_workspace_chat_messages(tmp_path):
    workspace_root = tmp_path / "workspaceStorage"
    workspace_db = workspace_root / "abc123" / "state.vscdb"
    workspace_db.parent.mkdir(parents=True)
    payload = {
        "workspaceRoot": "/Users/test/project-alpha",
        "messages": [
            {"role": "user", "content": "Use Ruff for linting."},
            {"role": "assistant", "content": "Okay"},
        ],
    }
    create_cursor_db(
        workspace_db,
        item_rows=[
            (
                "workbench.panel.aichat.view.aichat.chatdata",
                json.dumps(payload),
            )
        ],
    )

    provider = CursorProvider(
        global_db_path=str(tmp_path / "missing.vscdb"),
        workspace_root=str(workspace_root),
    )

    # Seed new data after initialization so it is treated as fresh activity.
    conn = sqlite3.connect(workspace_db)
    try:
        conn.execute(
            "INSERT INTO ItemTable ([key], value) VALUES (?, ?)",
            (
                "workbench.panel.aichat.view.aichat.chatdata",
                json.dumps(
                    {
                        "workspaceRoot": "/Users/test/project-alpha",
                        "messages": [{"role": "user", "content": "Prefer single quotes."}],
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    provider.last_mtimes.pop(str(workspace_db), None)
    provider._scan_database(workspace_db)

    assert len(provider.interaction_queue) == 1
    interaction = provider.interaction_queue[0]
    assert interaction.content == "Prefer single quotes."
    assert interaction.project_name == "project-alpha"
    assert interaction.metadata["key"] == "workbench.panel.aichat.view.aichat.chatdata"


def test_cursor_provider_extracts_global_prompts(tmp_path):
    global_db = tmp_path / "state.vscdb"
    create_cursor_db(
        global_db,
        kv_rows=[
            (
                "composerData",
                json.dumps(
                    {
                        "workspacePath": "/Users/test/project-beta",
                        "conversation": [
                            {"type": "user", "text": "Use Python 3.12 for this repo."}
                        ],
                    }
                ),
            )
        ],
    )

    provider = CursorProvider(
        global_db_path=str(global_db),
        workspace_root=str(tmp_path / "workspaceStorage"),
    )

    conn = sqlite3.connect(global_db)
    try:
        conn.execute(
            "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
            (
                "composerData",
                json.dumps(
                    {
                        "workspacePath": "/Users/test/project-beta",
                        "conversation": [{"type": "user", "text": "Store release notes too."}],
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    provider.last_mtimes.pop(str(global_db), None)
    provider._scan_database(global_db)

    assert len(provider.interaction_queue) == 1
    interaction = provider.interaction_queue[0]
    assert interaction.content == "Store release notes too."
    assert interaction.project_name == "project-beta"


def test_cursor_provider_extracts_prompt_entries(tmp_path):
    workspace_root = tmp_path / "workspaceStorage"
    workspace_db = workspace_root / "hash-1" / "state.vscdb"
    workspace_db.parent.mkdir(parents=True)
    create_cursor_db(
        workspace_db,
        item_rows=[("aiService.prompts", json.dumps(["Initial prompt"]))],
    )

    provider = CursorProvider(
        global_db_path=str(tmp_path / "missing.vscdb"),
        workspace_root=str(workspace_root),
    )

    conn = sqlite3.connect(workspace_db)
    try:
        conn.execute(
            "INSERT INTO ItemTable ([key], value) VALUES (?, ?)",
            (
                "aiService.prompts",
                json.dumps({"recent": ["Capture architecture decisions."]}),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    provider.last_mtimes.pop(str(workspace_db), None)
    provider._scan_database(workspace_db)

    assert [item.content for item in provider.interaction_queue] == ["Capture architecture decisions."]
    assert provider.interaction_queue[0].project_name == "hash-1"
