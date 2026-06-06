from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float  # 0.0 for local models


class BaseLLMAdapter(ABC):
    """Interface all LLM adapters must implement."""

    @abstractmethod
    def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> LLMResponse:
        """Single-turn completion. Returns structured response with cost tracking."""

    @abstractmethod
    def health_check(self) -> bool:
        """Returns True if the adapter is reachable and operational."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter identifier — used in logs and config."""
