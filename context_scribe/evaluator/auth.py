import json
import os
from pathlib import Path
from typing import Optional, List, Any, Dict


def get_gemini_api_key() -> Optional[str]:
    """
    Attempts to retrieve the Gemini API key from environment variables
    or from common Gemini CLI configuration files.
    """
    # 1. Check environment variable
    if "GEMINI_API_KEY" in os.environ:
        return os.environ["GEMINI_API_KEY"]

    # 2. Check common Gemini CLI config paths
    config_paths: List[str] = [
        "~/.gemini/credentials.json",
        "~/.gemini/config.json",
        "~/.config/gemini/credentials.json"
    ]

    for path_str in config_paths:
        path: Path = Path(os.path.expanduser(path_str))
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data: Dict[str, Any] = json.load(f)
                    
                    # Common keys used for storing the API key
                    for key in ["gemini_api_key", "apiKey", "api_key", "key"]:
                        if key in data and data[key]:
                            return str(data[key])
            except Exception as e:
                print(f"Warning: Failed to parse {path}: {e}")

    return None
