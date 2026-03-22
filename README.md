# Context-Scribe

A "Persistent Secretary" daemon designed to eliminate "Agent Amnesia." It monitors local AI session logs in the background, extracts long-term behavioral rules and project constraints using a lightweight LLM, and seamlessly commits them to a centralized Memory Bank via the Model Context Protocol (MCP).

## Core Features
* **Zero-Touch Sync:** Automatically extracts and persists rules natively from chat logs, entirely out of band.
* **Intelligent Evaluation:** Employs the `gemini-2.5-flash` (via your local CLI) to differentiate "Signal" (long-term rules) from "Noise" (transient task chatter).
* **Conflict Resolution:** Implements "New-Trumps-Old" logic. If a new instruction contradicts an existing memory, the system autonomously updates the Memory Bank to reflect your most recent intent.
* **Pointer Strategy:** Bootstraps new sessions with a single directive, forcing agents to natively lookup current project constraints via MCP.

## Architecture
Context-Scribe operates on an **Observer-Evaluator-Bridge** pattern:
1. **Observer**: A robust `watchdog` powered log monitor with manual periodic scanning to ensure zero missed events.
2. **Evaluator**: Headless evaluation powered by your local `gemini` CLI (no extra API keys required).
3. **Bridge**: Direct MCP integration via standard I/O syncing data into `@allpepper/memory-bank-mcp`.

## Installation & Setup

Ensure you have Python 3.10+ installed.

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd context-scribe
   ```

2. **Set up a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install the package:**
   ```bash
   pip install -e .
   ```

## Usage

Start the daemon:
```bash
context-scribe --tool gemini
```

### Integration
Upon running, `context-scribe` will bootstrap your `~/.gemini/GEMINI.md` file globally to ensure agents inherently know how to query the persistent memory via MCP. Ensure you have the corresponding memory-bank server correctly configured within your Gemini CLI setup.

## Testing the Tool

To verify that the tool is correctly extracting and persisting rules, follow these steps:

1.  **Start the daemon** in a terminal:
    ```bash
    context-scribe --tool gemini
    ```
2.  **Simulate an AI interaction** by creating a mock log file in the Gemini temporary directory:
    ```bash
    echo '[{"role": "user", "content": "Rule: All variables must be named using snake_case in Python scripts."}]' > ~/.gemini/tmp/test_rule.json
    ```
3.  **Wait for processing** (usually 20-40 seconds). You will see the status in the daemon UI change from `[WATCH]` to `[THINK]`, `[RESOLVE]`, and finally `[BANK]`.
4.  **Verify the Memory Bank**:
    ```bash
    cat ~/.memory-bank/global/global_rules.md
    ```
5.  **Test Conflict Resolution**:
    Send a contradictory rule to see the system intelligently update the list:
    ```bash
    echo '[{"role": "user", "content": "Rule: Actually, all variables must be named using UPPERCASE."}]' > ~/.gemini/tmp/test_conflict.json
    ```
    After processing, check the rules file again; the snake_case rule should be replaced by the UPPERCASE rule.
