import subprocess
import logging
from typing import Optional, Dict
import json
from dataclasses import dataclass
import re

from context_scribe.observer.provider import Interaction

logger = logging.getLogger(__name__)

@dataclass
class RuleOutput:
    content: str
    scope: str  # "GLOBAL" or "PROJECT"

class Evaluator:
    def __init__(self):
        try:
            subprocess.run(["gemini", "--version"], capture_output=True, check=True)
            logger.debug("Gemini CLI found successfully.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Gemini CLI not found.")

    def evaluate_interaction(self, interaction: Interaction, existing_global: str = "", existing_project: str = "") -> Optional[RuleOutput]:
        prompt = f"""
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
1. Determine if the user is establishing a long-term rule, preference, or project constraint.
2. Categorize the rule:
   - "GLOBAL": Applies to ALL projects.
   - "PROJECT": Specific to the current project "{interaction.project_name}".
3. Apply "New-Trumps-Old" logic if there's a contradiction.
4. Output a JSON object with:
   - "scope": "GLOBAL" or "PROJECT"
   - "rules": "The ENTIRE consolidated list of rules for that specific scope in clean Markdown bullets."
5. If NO new rules or changes are needed, output exactly: NO_RULE

CRITICAL: Output ONLY the JSON object or NO_RULE. Do not include any conversational filler or preamble.
"""
        logger.debug(f"Evaluating interaction for project {interaction.project_name}...")
        try:
            result = subprocess.run(
                ["gemini", "--prompt", prompt, "--output-format", "json"], 
                capture_output=True, 
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=60
            )
            
            output = result.stdout.strip()
            
            # Extract the response text which might be a JSON string itself
            response_text = output
            try:
                # First, parse the outer JSON from the CLI
                data = json.loads(output)
                response_text = data.get("response", output)
            except json.JSONDecodeError:
                pass

            # Now try to parse the actual rule JSON from that response text
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    rule_data = json.loads(json_match.group(0))
                    if "scope" in rule_data and "rules" in rule_data:
                        return RuleOutput(content=rule_data["rules"].strip(), scope=rule_data["scope"].upper())
                except json.JSONDecodeError:
                    pass

            if "NO_RULE" in response_text:
                return None
            
            # Last-ditch parsing
            if "GLOBAL" in response_text.upper():
                scope = "GLOBAL"
            else:
                scope = "PROJECT"
                
            # Clean up ephemeral noise
            if "<EPHEMERAL_MESSAGE>" in response_text:
                response_text = response_text.split("<EPHEMERAL_MESSAGE>")[0].strip()
            
            plain_marker = "The following is an ephemeral message"
            if plain_marker in response_text:
                response_text = response_text.split(plain_marker)[0].strip()

            return RuleOutput(content=response_text, scope=scope)
            
        except subprocess.TimeoutExpired:
            logger.error("Gemini CLI evaluation timed out.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
