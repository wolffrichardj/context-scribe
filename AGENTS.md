# AGENTS.md

## 1. Project Goal
**Context-Scribe** is a background daemon that monitors AI logs to extract persistent rules and stores them in an MCP-managed Memory Bank. It manages a **Retrieval-Based** memory system where agents are instructed to actively fetch their context.

## 2. Agent Personas
* **The Scribe:** Silent observer. Monitors `~/.gemini/tmp/` for JSON log updates.
* **The Evaluator:** Decision engine. Identifies new rules and performs **Autonomous Conflict Resolution** (New rules overwrite old ones in the bank).

## 3. Global Bootstrap Logic (User Level)
To ensure all sessions across all directories are "Memory-Aware," the tool ensures the following instruction exists in `~/.gemini/GEMINI.md` (or the equivalent rule file for the specific tool):

> **Master Retrieval Directive:**
> "You have access to a persistent Memory Bank via the `memory-bank-mcp-server`. Before beginning any task, you **MUST** invoke the appropriate tool (e.g., `read_memory_bank`) to identify current project constraints and user preferences. Do not assume you have full context until this check is complete."

## 4. Conflict Handling (State Management)
The system operates on a **Latest-is-Truth** model:
1. **Detection:** Scribe detects a new instruction in logs.
2. **Comparison:** Evaluator checks the Bank for contradictory rules.
3. **Resolution:** If a conflict is found, the **new rule replaces the old one**. 
4. **Log:** The tool outputs `[RESOLVE] Overwriting stale rule with new user preference.`

## 5. Observability (The Heartbeat)
Real-time console feedback for background operations:

| Event | Level | Output Example |
| :--- | :--- | :--- |
| **Detection** | `INFO` | `[WATCH] Activity in ~/.gemini/tmp/chats/logs.json` |
| **Analysis** | `INFO` | `[THINK] Evaluating last exchange for persistent rules...` |
| **Conflict** | `WARN` | `[RESOLVE] New instruction 'Use Python 3.12' overwriting 'Use Python 3.10'` |
| **Commit** | `ACTION` | `[BANK] Update successful via MCP tool 'write_file'` |

## 6. Guidelines & Constraints
* **Non-Blocking:** Use `shutil.copy2` for log snapshots to avoid locking the active Gemini session.
* **Minimalism:** Summarize rules into single, actionable sentences.
* **Tool-Agnostic:** Support tool-specific log formats via the `--tool` flag.