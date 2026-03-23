from context_scribe.observer.provider import JsonLogProvider


class GeminiProvider(JsonLogProvider):
    default_log_dir = "~/.gemini/tmp/"
    tool_name = "gemini"
