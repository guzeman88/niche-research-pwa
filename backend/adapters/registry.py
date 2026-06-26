"""
Adapter registry — instantiates adapters from config strings.
Niche Research PWA edition — LLM + research adapters only.
"""
from __future__ import annotations

from adapters.base.llm import BaseLLMAdapter, LLMResponse


# ---------------------------------------------------------------------------
# Real-time cost logging wrapper
# ---------------------------------------------------------------------------

class _CostLoggingAdapter(BaseLLMAdapter):
    """Wraps any LLM adapter, prints cost after every call, and handles fallback."""

    def __init__(self, inner: BaseLLMAdapter, fallback: "_CostLoggingAdapter | None" = None) -> None:
        self._inner = inner
        self._fallback = fallback

    @property
    def name(self) -> str:
        return self._inner.name

    def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> LLMResponse:
        try:
            resp = self._inner.complete(prompt, system=system, json_mode=json_mode)
            _print_cost(resp)
            return resp
        except Exception as primary_err:
            if self._fallback is not None:
                print(
                    f"  [llm] '{self._inner.name}' failed ({primary_err.__class__.__name__}) "
                    f"— falling back to '{self._fallback._inner.name}'",
                    flush=True,
                )
                return self._fallback.complete(prompt, system=system, json_mode=json_mode)
            raise

    def health_check(self) -> bool:
        return self._inner.health_check()


def _print_cost(resp: LLMResponse) -> None:
    if resp.cost_usd == 0.0:
        tag = "FREE (local)"
        cost_str = ""
    else:
        tag = f"${resp.cost_usd:.6f}"
        cost_str = f"  [{resp.input_tokens:,} in + {resp.output_tokens:,} out tokens]"
    print(f"  [cost] {resp.model}  {tag}{cost_str}", flush=True)


# ---------------------------------------------------------------------------
# LLM adapter factory
# ---------------------------------------------------------------------------

def get_llm_adapter(name: str, **kwargs) -> BaseLLMAdapter:
    """Return an LLM adapter by name. Names: 'ollama', 'gemini', 'claude'."""
    if name == "ollama":
        from adapters.llm.ollama import OllamaAdapter
        return OllamaAdapter(**kwargs)
    if name == "gemini":
        from adapters.llm.gemini import GeminiAdapter
        return GeminiAdapter(**kwargs)
    if name == "claude":
        from adapters.llm.claude import ClaudeAdapter
        return ClaudeAdapter(**kwargs)
    raise ValueError(f"Unknown LLM adapter: {name!r}. Available: ollama, gemini, claude")


def get_llm_with_fallback(primary: str = "ollama", fallback: str | None = "gemini", **kwargs) -> BaseLLMAdapter:
    """Try primary adapter; fall back to secondary if health check fails or call errors."""
    adapter = get_llm_adapter(primary, **kwargs)
    primary_healthy = adapter.health_check()

    fb_wrapped: _CostLoggingAdapter | None = None
    if fallback:
        fb = get_llm_adapter(fallback)
        if fb.health_check():
            fb_wrapped = _CostLoggingAdapter(fb, fallback=None)
            if not primary_healthy:
                print(f"  [llm] primary '{primary}' unavailable or model not pulled", flush=True)
                print(f"  [llm] using fallback '{fallback}'", flush=True)
                return fb_wrapped

    return _CostLoggingAdapter(adapter, fallback=fb_wrapped)
