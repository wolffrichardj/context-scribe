import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple

from context_scribe.observer.provider import BaseProvider, Interaction


class CursorProvider(BaseProvider):
    """Poll Cursor SQLite state databases for newly added user prompts."""

    GLOBAL_DB_DEFAULT = "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    WORKSPACE_ROOT_DEFAULT = "~/Library/Application Support/Cursor/User/workspaceStorage"
    WINDOWS_GLOBAL_DB_DEFAULT = r"%APPDATA%\\Cursor\\User\\globalStorage\\state.vscdb"
    WINDOWS_WORKSPACE_ROOT_DEFAULT = r"%APPDATA%\\Cursor\\User\\workspaceStorage"

    GLOBAL_KV_KEYS: Tuple[str, ...] = ("composerData",)
    WORKSPACE_KEYS: Tuple[str, ...] = (
        "aiService.prompts",
        "workbench.panel.aichat.view.aichat.chatdata",
    )

    def __init__(
        self,
        global_db_path: Optional[str] = None,
        workspace_root: Optional[str] = None,
        poll_interval: float = 1.0,
    ):
        self.global_db_path = Path(self._expand_path(global_db_path or self._default_global_db_path()))
        self.workspace_root = Path(self._expand_path(workspace_root or self._default_workspace_root()))
        self.poll_interval = poll_interval
        self.interaction_queue: List[Interaction] = []
        self.processed_entries: Set[str] = set()
        self.last_mtimes: Dict[str, Tuple[int, int]] = {}
        self._initialize_historical_state()

    def _expand_path(self, path: str) -> str:
        return os.path.expandvars(os.path.expanduser(path))

    def _default_global_db_path(self) -> str:
        return self.WINDOWS_GLOBAL_DB_DEFAULT if os.name == "nt" else self.GLOBAL_DB_DEFAULT

    def _default_workspace_root(self) -> str:
        return self.WINDOWS_WORKSPACE_ROOT_DEFAULT if os.name == "nt" else self.WORKSPACE_ROOT_DEFAULT

    def _initialize_historical_state(self) -> None:
        for db_path in self._iter_db_paths():
            self._scan_database(db_path, initialize=True)

    def _iter_db_paths(self) -> Iterator[Path]:
        seen: Set[Path] = set()
        candidates = [self.global_db_path]
        if self.workspace_root.exists():
            candidates.extend(sorted(self.workspace_root.glob("*/state.vscdb")))

        for path in candidates:
            resolved = Path(path)
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            yield resolved

    def _scan_database(self, db_path: Path, initialize: bool = False) -> None:
        try:
            stat = db_path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            return

        if not initialize and self.last_mtimes.get(str(db_path)) == signature:
            return
        self.last_mtimes[str(db_path)] = signature

        snapshot_path = self._snapshot_db(db_path)
        if snapshot_path is None:
            return

        try:
            records = self._read_cursor_records(snapshot_path)
        finally:
            try:
                os.remove(snapshot_path)
            except OSError:
                pass

        for record in records:
            entry_id = self._entry_id(db_path, record)
            if entry_id in self.processed_entries:
                continue
            self.processed_entries.add(entry_id)
            if not initialize:
                self._record_to_interactions(db_path, record)

    def _snapshot_db(self, db_path: Path) -> Optional[str]:
        try:
            fd, snapshot_path = tempfile.mkstemp(prefix="context_scribe_cursor_", suffix=".vscdb")
            os.close(fd)
            shutil.copy2(db_path, snapshot_path)
            wal_path = db_path.with_name(db_path.name + "-wal")
            shm_path = db_path.with_name(db_path.name + "-shm")
            if wal_path.exists():
                shutil.copy2(wal_path, snapshot_path + "-wal")
            if shm_path.exists():
                shutil.copy2(shm_path, snapshot_path + "-shm")
            return snapshot_path
        except OSError:
            return None

    def _read_cursor_records(self, snapshot_path: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        try:
            conn = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return records

        try:
            cursor = conn.cursor()
            tables = {
                row[0]
                for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

            if "ItemTable" in tables:
                records.extend(self._fetch_table_records(cursor, "ItemTable", "[key]", self.WORKSPACE_KEYS))
            if "cursorDiskKV" in tables:
                records.extend(self._fetch_table_records(cursor, "cursorDiskKV", "key", self.GLOBAL_KV_KEYS))
        except sqlite3.Error:
            return records
        finally:
            conn.close()

        return records

    def _fetch_table_records(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        key_column: str,
        keys: Sequence[str],
    ) -> List[Dict[str, Any]]:
        placeholders = ", ".join("?" for _ in keys)
        query = f"SELECT rowid, {key_column}, value FROM {table_name} WHERE {key_column} IN ({placeholders})"
        try:
            rows = cursor.execute(query, tuple(keys)).fetchall()
        except sqlite3.Error:
            return []

        return [
            {"rowid": rowid, "key": key, "value": value, "table": table_name}
            for rowid, key, value in rows
        ]

    def _entry_id(self, db_path: Path, record: Dict[str, Any]) -> str:
        value_bytes = record.get("value")
        if isinstance(value_bytes, memoryview):
            value_bytes = value_bytes.tobytes()
        if isinstance(value_bytes, str):
            value_bytes = value_bytes.encode("utf-8", errors="ignore")
        if value_bytes is None:
            value_bytes = b""
        digest = hashlib.sha256(value_bytes).hexdigest()
        return f"{db_path}:{record.get('table')}:{record.get('key')}:{record.get('rowid')}:{digest}"

    def _record_to_interactions(self, db_path: Path, record: Dict[str, Any]) -> None:
        payload = self._decode_json_payload(record.get("value"))
        if payload is None:
            return

        project_name = self._detect_project_name(db_path, payload)
        source_key = str(record.get("key", ""))

        if source_key == "aiService.prompts":
            for prompt in self._extract_prompt_texts(payload):
                self._enqueue_interaction(prompt, project_name, db_path, record)
            return

        for message in self._extract_user_messages(payload):
            self._enqueue_interaction(message, project_name, db_path, record)

    def _enqueue_interaction(self, text: str, project_name: str, db_path: Path, record: Dict[str, Any]) -> None:
        clean_text = text.strip()
        if not clean_text:
            return
        if "CONTEXT-SCRIBE-INTERNAL-EVALUATION" in clean_text.upper():
            return
        self.interaction_queue.append(
            Interaction(
                timestamp=datetime.now(),
                role="user",
                content=clean_text,
                project_name=project_name,
                metadata={
                    "db_path": str(db_path),
                    "table": record.get("table"),
                    "key": record.get("key"),
                    "rowid": record.get("rowid"),
                },
            )
        )

    def _decode_json_payload(self, value: Any) -> Optional[Any]:
        payload: Any = value
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="ignore")
        if payload is None:
            return None

        for _ in range(3):
            if isinstance(payload, str):
                stripped = payload.strip()
                if not stripped:
                    return None
                try:
                    payload = json.loads(stripped)
                    continue
                except json.JSONDecodeError:
                    return None
            break
        return payload

    def _extract_prompt_texts(self, payload: Any) -> List[str]:
        texts: List[str] = []
        for value in self._walk_values(payload):
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        return self._unique_preserve_order(texts)

    def _extract_user_messages(self, payload: Any) -> List[str]:
        messages: List[str] = []
        for item in self._walk_dicts(payload):
            if not self._looks_like_user_message(item):
                continue
            text = self._extract_text_from_message(item)
            if text:
                messages.append(text)
        return self._unique_preserve_order(messages)

    def _looks_like_user_message(self, item: Dict[str, Any]) -> bool:
        role_candidates = [
            item.get("role"),
            item.get("type"),
            item.get("speaker"),
            item.get("source"),
            item.get("author"),
        ]
        normalized = {str(candidate).strip().lower() for candidate in role_candidates if candidate is not None}
        if normalized.intersection({"user", "human", "composer", "prompt"}):
            return True
        return "prompt" in item and not normalized.intersection({"assistant", "system", "tool"})

    def _extract_text_from_message(self, item: Dict[str, Any]) -> str:
        for key in ("text", "message", "prompt", "content", "value"):
            if key not in item:
                continue
            text = self._flatten_text(item[key])
            if text.strip():
                return text.strip()
        return ""

    def _flatten_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(part for part in (self._flatten_text(entry) for entry in value) if part.strip())
        if isinstance(value, dict):
            for key in ("text", "value", "content", "message"):
                if key in value:
                    flattened = self._flatten_text(value[key])
                    if flattened.strip():
                        return flattened
            return "\n".join(part for part in (self._flatten_text(entry) for entry in value.values()) if part.strip())
        return str(value) if value is not None else ""

    def _detect_project_name(self, db_path: Path, payload: Any) -> str:
        if db_path == self.global_db_path:
            payload_project = self._basename_from_payload(payload)
            return payload_project or "global"

        if self.workspace_root in db_path.parents:
            workspace_hash = db_path.parent.name
            payload_project = self._basename_from_payload(payload)
            return payload_project or workspace_hash or "global"

        return self._basename_from_payload(payload) or "global"

    def _basename_from_payload(self, payload: Any) -> Optional[str]:
        path_keys = {
            "workspaceRoot", "workspacePath", "folderPath", "path", "fsPath", "uri", "workspaceUri"
        }
        for item in self._walk_dicts(payload):
            for key, value in item.items():
                if key not in path_keys:
                    continue
                normalized = self._normalize_path_candidate(value)
                if normalized:
                    return normalized
        return None

    def _normalize_path_candidate(self, value: Any) -> Optional[str]:
        raw = self._flatten_text(value).strip()
        if not raw:
            return None
        if raw.startswith("file://"):
            raw = raw[7:]
        raw = raw.rstrip("/")
        name = Path(raw).name
        if name and name != "state.vscdb":
            return name
        return None

    def _walk_values(self, payload: Any) -> Iterator[Any]:
        if isinstance(payload, dict):
            for value in payload.values():
                yield from self._walk_values(value)
        elif isinstance(payload, list):
            for item in payload:
                yield from self._walk_values(item)
        else:
            yield payload

    def _walk_dicts(self, payload: Any) -> Iterator[Dict[str, Any]]:
        if isinstance(payload, dict):
            yield payload
            for value in payload.values():
                yield from self._walk_dicts(value)
        elif isinstance(payload, list):
            for item in payload:
                yield from self._walk_dicts(item)

    def _unique_preserve_order(self, values: Sequence[str]) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def watch(self) -> Iterator[Interaction]:
        while True:
            try:
                for db_path in self._iter_db_paths():
                    self._scan_database(db_path)

                if self.interaction_queue:
                    while self.interaction_queue:
                        yield self.interaction_queue.pop(0)
                    continue

                yield None
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                return
