"""
Google Gemini LLM adapter — cheapest quality cloud fallback.
Default: gemini-2.0-flash-lite — $0.075/1M input, $0.30/1M output.
Free tier: 30 RPM, 1,500 req/day — sufficient for pipeline use.

Requires GEMINI_API_KEY in environment.
Get a free key at: https://aistudio.google.com/apikey
"""

import json
import os

from adapters.base.llm import BaseLLMAdapter, LLMResponse

_PRICING = {
    "gemini-2.0-flash-lite":         {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash":              {"input": 0.10,  "output": 0.40},
    "gemini-2.5-flash-lite":         {"input": 0.10,  "output": 0.40},
    "gemini-2.5-flash":              {"input": 0.30,  "output": 2.50},
    "gemini-2.5-pro":                {"input": 1.25,  "output": 10.00},
    "gemini-3-flash-preview":        {"input": 0.50,  "output": 3.00},
    "gemini-3.1-flash-lite-preview": {"input": 0.25,  "output": 1.50},
}
# Gemini 2.0 Flash-Lite is retired; allow env override for future model moves.
_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


class GeminiAdapter(BaseLLMAdapter):
    """Calls Google Gemini API. Tracks real token cost."""

    def __init__(self, model: str = _DEFAULT_MODEL):
        self._model = model
        self._api_key = os.getenv("GEMINI_API_KEY", "")

    @property
    def name(self) -> str:
        return f"gemini/{self._model}"

    def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> LLMResponse:
        try:
            from google import genai
            from google.genai import types
            from google.genai.errors import ClientError
        except ImportError:
            raise RuntimeError("google-genai package not installed: pip install google-genai")

        client = genai.Client(api_key=self._api_key)

        config_kwargs: dict = {"max_output_tokens": 8192}
        if system:
            config_kwargs["system_instruction"] = system
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except ClientError as e:
            status = getattr(e, "status_code", None) or getattr(e, "code", "?")
            if "API_KEY_SERVICE_BLOCKED" in str(e) or "PERMISSION_DENIED" in str(e):
                raise RuntimeError(
                    f"Gemini API key is blocked or restricted (HTTP {status}). "
                    "Fix: get a fresh key at https://aistudio.google.com/apikey"
                ) from e
            raise
        content = response.text

        if json_mode:
            json.loads(content)

        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        pricing = _PRICING.get(self._model, {"input": 0.10, "output": 0.40})
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )

    def health_check(self) -> bool:
        return bool(self._api_key) and not self._api_key.startswith("your_")
