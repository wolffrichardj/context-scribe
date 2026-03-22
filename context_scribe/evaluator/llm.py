import subprocess
import logging
from typing import Optional, Dict
import json
from dataclasses import dataclass
import re

from context_scribe.observer.provider import Interaction

logger = logging.getLogger(__name__)

INTERNAL_SIGNATURE = "--- CONTEXT-SCRIBE-INTERNAL-EVALUATION ---"

@dataclass
class RuleOutput:
    content: str
    scope: str  # "GLOBAL" or "PROJECT"
    description: str # Concise summary of what changed

class Evaluator:
    def __init__(self):
        try:
            subprocess.run(["gemini", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Gemini CLI not found.")

    def evaluate_interaction(self, interaction: Interaction, existing_global: str = "", existing_project: str = "") -> Optional[RuleOutput]:
        prompt = f"""
{INTERNAL_SIGNATURE}
You are a 'Persistent Secretary' for an AI agent. Your job is to read user-agent chat logs
and extract long-term behavioral rules, project constraints, or user preferences.

CURRENT PROJECT NAME: {interaction.project_name}

EXISTING GLOBAL RULES:
'''
{existing_global}
'''

EXISTING PROJECT RULES ({interaction.project_name}):
'''
{existing_project}
'''

LATEST USER INTERACTION TO ANALYZE:
'''
{interaction.content}
'''

INSTRUCTIONS:
1. Categorize the rule with a strict **"Global-Unless-Proven-Local"** policy:
   - **GLOBAL (DEFAULT)**: All general coding styles, naming conventions, and personal preferences.
   - **PROJECT (EXCEPTION)**: Strictly for rules unique to "{interaction.project_name}".
2. Rule Enhancement (CRITICAL):
   - Professionalize slang into technical descriptions.
   - Ensure rules are clear directives.
   - Add a tiny inline example for complex rules.
3. Output Format:
   - Output a JSON object with:
     - "scope": "GLOBAL" or "PROJECT"
     - "description": "A very concise (3-5 words) summary of the NEW rule or update."
     - "rules": "The NEW or UPDATED rules ONLY. Format them as Markdown (e.g., '### Style\n- Use 4 spaces'). Do not include existing rules unless you are modifying them."
4. If NO NEW rules are identified, output exactly: NO_RULE

CRITICAL: **Do not repeat existing rules** unless they need to be changed. Output ONLY the JSON object or NO_RULE.
"""
        try:
            result = subprocess.run(
                [
                    "gemini", 
                    "--model", "gemini-2.5-flash-lite",
                    "--extensions", "",
                    "--allowed-mcp-server-names", "",
                    "--prompt", prompt, 
                    "--output-format", "json"
                ], 
                capture_output=True, 
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=120
            )
            
            output = result.stdout.strip()
            
            response_text = output
            try:
                data = json.loads(output)
                if isinstance(data, dict):
                    response_text = data.get("response", output)
            except json.JSONDecodeError:
                pass

            json_match = re.search(r'\{.*\}', str(response_text), re.DOTALL)
            if json_match:
                try:
                    rule_data = json.loads(json_match.group(0))
                    if "scope" in rule_data and "rules" in rule_data:
                        rules_raw = rule_data["rules"]
                        desc = rule_data.get("description", "Updated rules")
                        if isinstance(rules_raw, list):
                            rules_content = "\n".join([str(r) for r in rules_raw]).strip()
                        else:
                            rules_content = str(rules_raw).strip()
                        return RuleOutput(content=rules_content, scope=rule_data["scope"].upper(), description=str(desc))
                except json.JSONDecodeError:
                    pass

            if "NO_RULE" in str(response_text):
                return None
            
            # Fallback
            scope = "PROJECT" if "PROJECT" in str(response_text).upper() else "GLOBAL"
            return RuleOutput(content=str(response_text), scope=scope, description="Extracted rule")
            
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None
