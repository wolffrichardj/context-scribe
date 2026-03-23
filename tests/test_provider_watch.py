import os
import pytest
from unittest.mock import patch

from context_scribe.observer.gemini_provider import GeminiProvider


@pytest.mark.timeout(5)
def test_provider_watch_manual_scan_trigger(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    provider = GeminiProvider(log_dir=str(log_dir))

    test_file = log_dir / "test.json"
    test_file.write_text('[]')
    provider.last_mtimes[str(test_file)] = os.path.getmtime(test_file)

    with patch("context_scribe.observer.provider.Observer") as mock_obs:
        with patch("time.sleep", side_effect=[None, KeyboardInterrupt()]):
            new_file = log_dir / "new.json"
            new_file.write_text('{"sessionId": "s", "messages": [{"id": "m", "type": "user", "text": "manual"}]}')

            gen = provider.watch()

            interaction = next(gen)
            assert interaction.content == "manual"
