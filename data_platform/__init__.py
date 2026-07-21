"""Stable public exports for the data platform package."""

from .providers.a_share_sqlite_repository import AShareSQLiteRepository
from .providers.legacy_sqlite_repository import LegacySQLiteMarketDataRepository
from .providers.external_market_provider import ExternalMarketProviderRepository
from .providers.ricequant_repository import (
    RicequantClientProtocol,
    RicequantMarketDataRepository,
)
from .repository.cached_market_repository import CachedMarketDataRepository
from .repository.contracts import MarketDataRepository
from .storage.sqlite_metadata_store import SqliteMetadataStore
from .storage.a_share_market_store import AShareMarketStore
from .storage.classification_history_store import ClassificationHistoryStore

__all__ = [
    "AShareMarketStore",
    "AShareSQLiteRepository",
    "CachedMarketDataRepository",
    "ClassificationHistoryStore",
    "LegacySQLiteMarketDataRepository",
    "ExternalMarketProviderRepository",
    "MarketDataRepository",
    "RicequantClientProtocol",
    "RicequantMarketDataRepository",
    "SqliteMetadataStore",
]

