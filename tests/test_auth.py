import os
import json
from unittest.mock import patch, mock_open
from context_scribe.evaluator.auth import get_gemini_api_key

def test_get_gemini_api_key_from_env():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}):
        assert get_gemini_api_key() == "env-key"

def test_get_gemini_api_key_from_file_json():
    config_data = {"gemini_api_key": "json-key"}
    with patch.dict(os.environ, {}, clear=True):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
                assert get_gemini_api_key() == "json-key"

def test_get_gemini_api_key_from_file_apiKey():
    config_data = {"apiKey": "alt-key"}
    with patch.dict(os.environ, {}, clear=True):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
                assert get_gemini_api_key() == "alt-key"

def test_get_gemini_api_key_fail_parsing():
    with patch.dict(os.environ, {}, clear=True):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="invalid json")):
                assert get_gemini_api_key() is None

def test_get_gemini_api_key_none_anywhere():
    with patch.dict(os.environ, {}, clear=True):
        with patch("pathlib.Path.exists", return_value=False):
            assert get_gemini_api_key() is None
