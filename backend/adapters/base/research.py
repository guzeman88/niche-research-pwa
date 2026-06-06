from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NicheSignal:
    keyword: str
    monthly_searches: int    # 0 if unavailable
    competition_score: float # 0-100 (higher = more competitive)
    avg_price_usd: float     # 0.0 if unavailable
    trend_direction: str     # "rising" | "stable" | "declining"
    source: str              # adapter name


class BaseResearchAdapter(ABC):
    """Interface all niche research adapters must implement."""

    @abstractmethod
    def search(self, keyword: str, category: str = "") -> list[NicheSignal]:
        """Search for a single keyword. Returns NicheSignal list."""

    @abstractmethod
    def bulk_search(self, keywords: list[str]) -> list[NicheSignal]:
        """Search multiple keywords. Implementations may batch API calls."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns False if required API key is missing — used for graceful skip."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter identifier."""
