# Context-Scribe

A "Persistent Secretary" daemon designed to eliminate "Agent Amnesia." It monitors local AI session logs in the background, extracts long-term behavioral rules and project constraints using a lightweight LLM, and seamlessly commits them to a centralized Memory Bank via the Model Context Protocol (MCP).

## Core Features
* **Zero-Touch Sync:** Automatically extracts and persists rules natively from chat logs, entirely out of band.
* **Extensible Provider Architecture:** Readily supports AI agent logs (currently supports `gemini` logs).
* **Pointer Strategy:** Bootstraps new sessions with a single directive rather than bloating the initial context window, forcing agents to natively lookup current project constraints via MCP.
* **Intelligent Evaluation:** Employs the `gemini-2.5-flash` model to rapidly differentiate "Signal" (long-term rules) from "Noise" (transient task chatter).

## Architecture
Context-Scribe operates on an **Observer-Evaluator-Bridge** pattern:
1. **Observer**: A robust `watchdog` powered log monitor seamlessly ingesting continuous file outputs natively.
2. **Evaluator**: Contextual filtering powered by `google-genai` evaluating log diffs.
3. **Bridge**: Direct MCP integration via standard I/O syncing data into `@allpepper/memory-bank`.

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

### Authentication
The Evaluator needs a Gemini API key. Context-Scribe automatically checks standard locations (e.g. `~/.gemini/credentials.json`) or falls back to using the `GEMINI_API_KEY` environment variable.

### Integration
Upon running, `context-scribe` will bootstrap your `~/.gemini/GEMINI.md` file globally to ensure agents inherently know how to query the persistent memory via MCP. Ensure you have the corresponding memory-bank server correctly configured within your Gemini CLI setup.
