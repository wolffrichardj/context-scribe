import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, Set

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from context_scribe.observer.provider import BaseProvider, Interaction


class AntigravityStateHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith("state.vscdb"):
            self.callback(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith("state.vscdb"):
            self.callback(event.src_path)


class AntigravityProvider(BaseProvider):
    tool_name = "antigravity"
    sqlite_state_key = "workbench.panel.aichat.view.aichat.chatdata"

    def __init__(self, workspace_storage_dir: Optional[str] = None):
        self.workspace_storage_dirs = self._resolve_workspace_storage_dirs(workspace_storage_dir)
        self.interaction_queue = []
        self.processed_message_ids: Set[str] = set()
        self.last_mtimes = {}
        self._initialize_historical_dbs()

    def _resolve_workspace_storage_dirs(self, workspace_storage_dir: Optional[str]) -> list[Path]:
        if workspace_storage_dir:
            return [Path(os.path.expanduser(workspace_storage_dir))]

        candidates = [
            Path(os.path.expanduser("~/.config/Antigravity/User/workspaceStorage")),
            Path(os.path.expanduser("~/Library/Application Support/Antigravity/User/workspaceStorage")),
        ]

        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Antigravity" / "User" / "workspaceStorage")

        unique_candidates = []
        for candidate in candidates:
            if candidate not in unique_candidates:
                unique_candidates.append(candidate)
        return unique_candidates

    @property
    def default_log_dir(self) -> str:
        return str(self.workspace_storage_dirs[0]) if self.workspace_storage_dirs else ""

    def _iter_state_db_paths(self) -> list[Path]:
        db_paths = []
        for root in self.workspace_storage_dirs:
            if not root.exists():
                continue
            db_paths.extend(sorted(root.glob("**/state.vscdb")))
        return db_paths

    def _initialize_historical_dbs(self):
        for db_path in self._iter_state_db_paths():
            try:
                self.last_mtimes[str(db_path)] = os.path.getmtime(db_path)
                for interaction in self._load_interactions_from_db(db_path):
                    self.processed_message_ids.add(self._build_message_id(db_path, interaction.content, interaction.metadata))
            except Exception:
                pass

    def _build_message_id(self, db_path: Path, content: str, metadata: Optional[dict]) -> str:
        raw_id = None
        if metadata:
            raw_id = metadata.get("id") or metadata.get("requestId") or metadata.get("messageId")
        if raw_id is None:
            raw_id = content
        return f"{db_path}:{raw_id}"

    def _process_db(self, db_path: str):
        db_path_obj = Path(db_path)
        try:
            for interaction in self._load_interactions_from_db(db_path_obj):
                message_id = self._build_message_id(db_path_obj, interaction.content, interaction.metadata)
                if message_id in self.processed_message_ids:
                    continue
                self.interaction_queue.append(interaction)
                self.processed_message_ids.add(message_id)
        except Exception:
            pass

    def _load_interactions_from_db(self, db_path: Path) -> list[Interaction]:
        chat_data = self._read_chat_state(db_path)
        if not chat_data:
            return []

        project_name = self._infer_project_name(chat_data) or "global"
        interactions = []
        for message in self._collect_user_messages(chat_data):
            content = message["content"].strip()
            if not content:
                continue
            if "CONTEXT-SCRIBE-INTERNAL-EVALUATION" in content.upper():
                continue
            interactions.append(
                Interaction(
                    timestamp=datetime.now(),
                    role="user",
                    content=content,
                    project_name=project_name,
                    metadata=message,
                )
            )
        return interactions

    def _read_chat_state(self, db_path: Path) -> Any:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT value FROM ItemTable WHERE key = ?",
                (self.sqlite_state_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            raw_value = row[0]
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8")
            if not raw_value:
                return None
            return json.loads(raw_value)
        finally:
            connection.close()

    def _collect_user_messages(self, data: Any) -> list[dict]:
        messages = []

        def walk(node: Any):
            if isinstance(node, dict):
                message = self._message_from_node(node)
                if message:
                    messages.append(message)
                for value in node.values():
                    walk(value)
                return

            if isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        return messages

    def _message_from_node(self, node: dict) -> Optional[dict]:
        request_content = self._extract_text(node.get("request"))
        if request_content:
            return {
                "id": node.get("requestId") or node.get("id"),
                "content": request_content,
            }

        role = self._normalize_role(node)
        if role != "user":
            return None

        content = self._extract_text(
            node.get("content")
            or node.get("message")
            or node.get("text")
            or node.get("prompt")
            or node.get("query")
        )
        if not content:
            return None

        return {
            "id": node.get("id") or node.get("messageId") or node.get("requestId"),
            "content": content,
        }

    def _normalize_role(self, node: dict) -> str:
        role = node.get("role") or node.get("type") or node.get("speaker")
        if isinstance(role, str):
            lowered = role.lower()
            if lowered in {"user", "human", "request"}:
                return "user"
        author = node.get("author")
        if isinstance(author, dict):
            author_role = author.get("role")
            if isinstance(author_role, str) and author_role.lower() in {"user", "human"}:
                return "user"
        return "unknown"

    def _extract_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [self._extract_text(item) for item in value]
            return "\n".join(part for part in parts if part)
        if isinstance(value, dict):
            for key in ("text", "value", "content", "message", "prompt"):
                text = self._extract_text(value.get(key))
                if text:
                    return text
        return ""

    def _infer_project_name(self, data: Any) -> Optional[str]:
        project_path = self._find_project_path(data)
        if not project_path:
            return None
        return Path(project_path).name or None

    def _find_project_path(self, node: Any) -> Optional[str]:
        if isinstance(node, dict):
            for key in ("workspaceFolder", "workspacePath", "fsPath", "path"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            for value in node.values():
                found = self._find_project_path(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_project_path(item)
                if found:
                    return found
        return None

    def watch(self) -> Iterator[Interaction]:
        observer = Observer()
        event_handler = AntigravityStateHandler(self._process_db)

        scheduled = False
        for root in self.workspace_storage_dirs:
            if root.exists():
                observer.schedule(event_handler, str(root), recursive=True)
                scheduled = True

        if scheduled:
            observer.start()

        try:
            while True:
                for db_path in self._iter_state_db_paths():
                    try:
                        mtime = os.path.getmtime(db_path)
                        if str(db_path) not in self.last_mtimes or mtime > self.last_mtimes.get(str(db_path), 0):
                            self.last_mtimes[str(db_path)] = mtime
                            self._process_db(str(db_path))
                    except Exception:
                        pass

                if not self.interaction_queue:
                    yield None
                    time.sleep(1)
                    continue

                while self.interaction_queue:
                    yield self.interaction_queue.pop(0)
        except KeyboardInterrupt:
            if scheduled:
                observer.stop()
        finally:
            if scheduled:
                observer.join()
