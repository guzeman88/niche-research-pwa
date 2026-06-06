"""
Anthropic Claude LLM adapter — cloud API upgrade path.
Requires ANTHROPIC_API_KEY in environment.
"""

import json
import os

from adapters.base.llm import BaseLLMAdapter, LLMResponse

_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
}
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ClaudeAdapter(BaseLLMAdapter):
    """Calls Anthropic Messages API. Tracks token cost."""

    def __init__(self, model: str = _DEFAULT_MODEL):
        self._model = model
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def name(self) -> str:
        return f"claude/{self._model}"

    def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> LLMResponse:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed: pip install anthropic")

        client = anthropic.Anthropic(api_key=self._api_key)

        kwargs: dict = {
            "model": self._model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        content = response.content[0].text

        if json_mode:
            json.loads(content)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        pricing = _PRICING.get(self._model, {"input": 3.00, "output": 15.00})
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
