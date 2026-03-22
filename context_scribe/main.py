import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Optional, NoReturn
import click
from rich.console import Console # type: ignore
from rich.live import Live # type: ignore
from rich.panel import Panel # type: ignore
from rich.text import Text # type: ignore

from context_scribe.observer.gemini_provider import GeminiProvider
from context_scribe.evaluator.llm import Evaluator
from context_scribe.bridge.mcp_client import MemoryBankClient
from context_scribe.observer.provider import Interaction, BaseProvider

console: Console = Console()

MASTER_RETRIEVAL_RULE: str = """
# Memory Bank Integration
You have access to a persistent Memory Bank via MCP. Before beginning any task, you MUST invoke the appropriate tools (e.g. `list_projects`, `memory_bank_read`) to identify current project constraints and user preferences. Do not assume you have full context until this sync is complete.
"""

def bootstrap_global_config() -> None:
    """Injects the master retrieval rule into Gemini CLI's global config."""
    gemini_config_dir: Path = Path(os.path.expanduser("~/.gemini"))
    gemini_config_dir.mkdir(parents=True, exist_ok=True)
    gemini_md_path: Path = gemini_config_dir / "GEMINI.md"

    rule_exists: bool = False
    if gemini_md_path.exists():
        with open(gemini_md_path, "r", encoding="utf-8") as f:
            if "Memory Bank Integration" in f.read():
                rule_exists = True

    if not rule_exists:
        with open(gemini_md_path, "a", encoding="utf-8") as f:
            f.write(f"\n{MASTER_RETRIEVAL_RULE}\n")
        console.print(f"[green]Bootstrapped: Injected Master Retrieval Rule into {gemini_md_path}[/green]")
    else:
        console.print(f"[blue]Bootstrap: Master Retrieval Rule already exists in {gemini_md_path}[/blue]")

async def run_daemon(tool: str) -> bool:
    bootstrap_global_config()

    provider: BaseProvider
    if tool == "gemini":
        provider = GeminiProvider()
    else:
        console.print(f"[red]Unsupported tool: {tool}[/red]")
        return False

    evaluator: Evaluator = Evaluator()
    mcp_client: MemoryBankClient = MemoryBankClient()
    
    try:
        await mcp_client.connect()
    except Exception as e:
        console.print(f"[bold red]Fatal Error: Could not connect to the Memory Bank MCP server.[/bold red]")
        console.print("[red]Context-Scribe requires a working persistence layer to function. Ensure your MCP server is installed and configured correctly.[/red]")
        os._exit(1)

    console.print(f"[bold green]Context-Scribe started. Monitoring {tool} logs...[/bold green]")
    
    with Live(Panel("Waiting for activity...", title="Context-Scribe Status", style="blue"), refresh_per_second=4) as live:
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
            
            # Since provider.watch() yields, we need to iterate it.
            watch_iter = provider.watch()
            
            while True:
                live.update(Panel(Text("[WATCH] Active file monitoring...", style="cyan"), title="Context-Scribe Status"))
                
                # Fetch next interaction
                interaction = await loop.run_in_executor(None, next, watch_iter)

                # Fetch existing rules for conflict resolution
                existing_global = await mcp_client.read_rules(project_name="global", file_name="global_rules.md")
                existing_project = await mcp_client.read_rules(project_name=interaction.project_name, file_name="rules.md")

                live.update(Panel(Text(f"[THINK] Evaluating interaction from {interaction.role} ({interaction.project_name})...", style="yellow"), title="Context-Scribe Status"))

                rule_output = await loop.run_in_executor(None, evaluator.evaluate_interaction, interaction, existing_global, existing_project)

                if rule_output:
                    live.update(Panel(Text(f"[RESOLVE] Updating {rule_output.scope} Memory Bank...", style="magenta"), title="Context-Scribe Status"))

                    # Determine destination
                    if rule_output.scope == "GLOBAL":
                        dest_project = "global"
                        dest_file = "global_rules.md"
                    else:
                        dest_project = interaction.project_name
                        dest_file = "rules.md"

                    live.update(Panel(Text(f"[BANK] Committing to {dest_project}/{dest_file}...", style="green"), title="Context-Scribe Status"))

                    result = await mcp_client.save_rule(rule_output.content, project_name=dest_project, file_name=dest_file)
                    if hasattr(result, 'isError') and result.isError:
                        console.print(f"\n[bold red]Failed to save rule:[/bold red] {result.content}")
                    else:
                        console.print(f"\n[bold green]{rule_output.scope} Memory Bank Updated Successfully.[/bold green]")
                    
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
        finally:
            await mcp_client.close()

    return True

@click.command()
@click.option('--tool', default='gemini', help='The AI tool to monitor (e.g., gemini)')
def cli(tool: str) -> None:
    """Context-Scribe: Persistent Secretary Daemon"""
    success: bool = asyncio.run(run_daemon(tool))
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    cli()
