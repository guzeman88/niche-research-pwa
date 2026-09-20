from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class NicheSignal:
    keyword: str
    monthly_searches: int | None
    competition_score: float | None
    avg_price_usd: float | None
    trend_direction: str | None
    source: str              # adapter name
    relative_interest: float | None = None
    relative_interest_period: str | None = None
    observed_at: str | None = None
    geography: str | None = None
    query: str | None = None
    position: int | None = None
    time_series: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


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
