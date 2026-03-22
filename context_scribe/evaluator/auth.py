import json
import os
from pathlib import Path
from typing import Optional


def get_gemini_api_key() -> Optional[str]:
    """
    Attempts to retrieve the Gemini API key from environment variables
    or from common Gemini CLI configuration files.
    """
    # 1. Check environment variable
    if "GEMINI_API_KEY" in os.environ:
        return os.environ["GEMINI_API_KEY"]

    # 2. Check common Gemini CLI config paths
    config_paths = [
        "~/.gemini/credentials.json",
        "~/.gemini/config.json",
        "~/.config/gemini/credentials.json"
    ]

    for path_str in config_paths:
        path = Path(os.path.expanduser(path_str))
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    # Common keys used for storing the API key
                    for key in ["gemini_api_key", "apiKey", "api_key", "key"]:
                        if key in data and data[key]:
                            return data[key]
            except Exception as e:
                print(f"Warning: Failed to parse {path}: {e}")

    return None
