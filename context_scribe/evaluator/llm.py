import subprocess
import logging
from typing import Optional
import json

from context_scribe.observer.provider import Interaction

logger = logging.getLogger(__name__)

class Evaluator:
    def __init__(self):
        try:
            subprocess.run(["gemini", "--version"], capture_output=True, check=True)
            logger.debug("Gemini CLI found successfully.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Gemini CLI not found.")

    def evaluate_interaction(self, interaction: Interaction) -> Optional[str]:
        prompt = f"""
You are a 'Persistent Secretary' for an AI agent. Your job is to read user-agent chat logs
and extract ONLY long-term behavioral rules, project constraints, or user preferences.
Ignore transient task chatter, coding requests, debugging steps, or temporary instructions.

Analyze the following interaction (Role: {interaction.role}):
'''
{interaction.content}
'''

If there is a clear, long-term rule or constraint that should be saved to the Memory Bank,
extract it and output ONLY the rule. If it contradicts an existing common practice, note that.
If there is NO long-term rule, output exactly: NO_RULE
"""
        logger.debug(f"Evaluating interaction: {interaction.content[:50]}...")
        try:
            # We use non-interactive mode and json output with a strict timeout
            result = subprocess.run(
                ["gemini", "--prompt", prompt, "--output-format", "json"], 
                capture_output=True, 
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=30
            )
            
            output = result.stdout.strip()
            
            json_str = None
            try:
                start_idx = output.find('{')
                end_idx = output.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = output[start_idx:end_idx+1]
                    data = json.loads(json_str)
                    response_text = data.get("response", "").strip()
                else:
                    response_text = output
            except json.JSONDecodeError:
                response_text = output
            
            if "NO_RULE" in response_text or not response_text:
                return None
            
            # Clean up ephemeral messages
            if "<EPHEMERAL_MESSAGE>" in response_text:
                response_text = response_text.split("<EPHEMERAL_MESSAGE>")[0].strip()
            
            plain_marker = "The following is an ephemeral message"
            if plain_marker in response_text:
                response_text = response_text.split(plain_marker)[0].strip()

            return response_text
        except subprocess.TimeoutExpired:
            logger.error("Gemini CLI evaluation timed out after 30 seconds.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling gemini CLI: {e}")
            return None
