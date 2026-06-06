"""
Ollama LLM adapter — local inference via Ollama HTTP API.
Supports any model pulled with `ollama pull <model>`.
"""

import json
import os
from pathlib import Path

import httpx

from adapters.base.llm import BaseLLMAdapter, LLMResponse


class OllamaAdapter(BaseLLMAdapter):
    """Calls Ollama's /api/chat endpoint. Zero cost (local)."""

    # Preferred model families in priority order for auto-selection
    _PREFERRED_FAMILIES = ["qwen3", "qwen2.5", "gemma3", "gemma2", "llama3", "mistral", "phi"]

    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self._base_url = base_url.rstrip("/")
        self._model = self._resolve_model(model)

    @staticmethod
    def _param_count(model_name: str) -> float:
        """Extract numeric parameter count (in billions) from a model name, e.g. 'qwen3.5:9b' -> 9.0."""
        import re
        m = re.search(r':(\d+\.?\d*)b', model_name.lower())
        if m:
            return float(m.group(1))
        # Also check base name e.g. "llama3-8b"
        m = re.search(r'[-_](\d+\.?\d*)b', model_name.lower())
        if m:
            return float(m.group(1))
        return 0.0

    def _best_in_family(self, available: list[str], family_prefix: str, max_params: float = float("inf")) -> str | None:
        """Return the largest model in a family at or below max_params."""
        matches = [m for m in available if m.startswith(family_prefix)
                   and self._param_count(m) <= max_params]
        if not matches:
            return None
        return max(matches, key=self._param_count)

    def _resolve_model(self, requested: str) -> str:
        """Return requested model if available, otherwise pick the best available model."""
        try:
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return requested
            available = [m.get("name", "") for m in resp.json().get("models", [])]
            if not available:
                return requested
            # Exact match
            if requested in available:
                return requested
            # On localhost (CPU-only), cap at 7B — larger models time out on CPU inference
            is_local = "localhost" in self._base_url or "127.0.0.1" in self._base_url
            cpu_cap = 7.0 if is_local else float("inf")

            # Find best in preferred families within the param cap
            best_preferred = None
            best_preferred_params = 0.0
            for family in self._PREFERRED_FAMILIES:
                candidate = self._best_in_family(available, family, max_params=cpu_cap)
                if candidate:
                    p = self._param_count(candidate)
                    if p > best_preferred_params:
                        best_preferred_params = p
                        best_preferred = candidate
                    break  # stop at first matching preferred family

            # If nothing fits under cap, relax and take whatever is available
            if best_preferred is None:
                for family in self._PREFERRED_FAMILIES:
                    candidate = self._best_in_family(available, family)
                    if candidate:
                        best_preferred = candidate
                        best_preferred_params = self._param_count(candidate)
                        break

            # Prefix match within the requested family (also capped)
            req_base = requested.split(":")[0]
            req_params = self._param_count(requested)
            prefix_best = self._best_in_family(available, req_base, max_params=cpu_cap)

            if prefix_best:
                prefix_params = self._param_count(prefix_best)
                # Use prefix match only if it's at least 40% the size of what was requested
                # AND at least as good as the best preferred family option
                if prefix_params >= req_params * 0.40 or (best_preferred is None):
                    if best_preferred and best_preferred_params > prefix_params * 1.5:
                        # Preferred family has a notably better model — use it
                        print(f"[ollama] '{requested}' not found; using '{best_preferred}' (better model available)")
                        return best_preferred
                    print(f"[ollama] '{requested}' not found; using '{prefix_best}'")
                    return prefix_best

            # Fall through to preferred family
            if best_preferred:
                print(f"[ollama] '{requested}' not found; using '{best_preferred}' (auto-selected)")
                return best_preferred

            # Last resort
            chosen = available[0]
            print(f"[ollama] '{requested}' not found; using '{chosen}' (fallback)")
            return chosen
        except Exception:
            return requested

    @property
    def name(self) -> str:
        return f"ollama/{self._model}"

    def _is_thinking_model(self) -> bool:
        """qwen3.x models have thinking mode enabled by default in Ollama."""
        return self._model.startswith("qwen3")

    def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> LLMResponse:
        import re as _re
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        # Disable thinking mode for qwen3 models — cuts token output in half on CPU
        user_content = prompt
        if self._is_thinking_model():
            user_content = "/no_think\n" + prompt

        messages.append({"role": "user", "content": user_content})

        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        resp = httpx.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=600,  # 10 min — large models on CPU need time
        )
        resp.raise_for_status()
        data = resp.json()

        content = data["message"]["content"]
        # Strip <think>...</think> blocks that qwen3 sometimes emits despite /no_think
        content = _re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        if json_mode:
            json.loads(content)

        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return any(m == self._model or m.startswith(self._model.split(":")[0]) for m in models)
        except Exception:
            return False
