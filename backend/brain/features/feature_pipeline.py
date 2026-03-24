"""
Feature Pipeline

Orchestrates all feature computation for the Brain. Reads raw data from
provided data sources, runs all 4 feature categories, combines results into
a single feature vector, and publishes FeatureEvent to the event bus.

Usage:
    pipeline = FeaturePipeline(config, event_bus)
    await pipeline.initialize()

    # Single symbol
    features = await pipeline.compute_features("RELIANCE")

    # Batch (post-market)
    results = await pipeline.run_batch(["RELIANCE", "TCS", "INFY"])
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

import numpy as np
import pandas as pd

from brain.config import BrainConfig, get_brain_config
from brain.models.events import EventType, FeatureEvent

from .cross_sectional_features import compute_all_cross_sectional_features
from .feature_registry import FeatureRegistry
from .fundamental_features import compute_all_fundamental_features
from .macro_features import compute_all_macro_features
from .technical_features import compute_all_technical_features

logger = logging.getLogger(__name__)

# Type alias for async data fetcher callbacks
DataFetcher = Callable[..., Coroutine[Any, Any, Any]]


class FeaturePipeline:
    """
    Orchestrates feature engineering across all categories.

    The pipeline does NOT make database calls directly. Instead, it accepts
    data fetcher callbacks that are injected at initialization time. This
    keeps feature computation pure and testable.
    """

    def __init__(
        self,
        config: Optional[BrainConfig] = None,
        event_bus: Optional[Any] = None,
        price_fetcher: Optional[DataFetcher] = None,
        fundamental_fetcher: Optional[DataFetcher] = None,
        macro_fetcher: Optional[DataFetcher] = None,
        market_fetcher: Optional[DataFetcher] = None,
    ) -> None:
        """
        Args:
            config: Brain configuration (uses singleton if not provided).
            event_bus: EventBus instance for publishing FeatureEvents.
            price_fetcher: async fn(symbol) -> pd.DataFrame (OHLCV).
            fundamental_fetcher: async fn(symbol) -> Dict.
            macro_fetcher: async fn() -> Dict (market-wide macro data).
            market_fetcher: async fn(symbol) -> Dict (nifty prices, sector data).
        """
        self._config = config or get_brain_config()
        self._event_bus = event_bus
        self._price_fetcher = price_fetcher
        self._fundamental_fetcher = fundamental_fetcher
        self._macro_fetcher = macro_fetcher
        self._market_fetcher = market_fetcher

        self._registry = FeatureRegistry()
        self._feature_cache: Dict[str, Dict[str, float]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._initialized = False

        # Statistics
        self._total_computations = 0
        self._total_errors = 0
        self._last_batch_duration: Optional[float] = None

    @property
    def registry(self) -> FeatureRegistry:
        return self._registry

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """
        Initialize the pipeline and register all feature groups.
        """
        if self._initialized:
            return

        self._register_all_features()
        self._initialized = True

        logger.info(
            "FeaturePipeline initialized with %d features across %d categories",
            self._registry.feature_count,
            len(self._registry.categories),
        )

    def _register_all_features(self) -> None:
        """Register all feature groups in the registry."""

        # Technical features
        self._registry.register_feature_group(
            group_name="technical_indicators",
            category="technical",
            compute_fn=compute_all_technical_features,
            feature_names=[
                "atr_14", "obv", "obv_slope_10d",
                "vwap", "price_vs_vwap_pct",
                "adx_14", "plus_di", "minus_di",
                "stoch_k", "stoch_d",
                "williams_r",
                "cci_20",
                "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_price_vs_cloud",
                "roc_10", "roc_20",
                "mfi_14",
                "delivery_pct", "delivery_pct_20d_avg",
                "rsi_divergence",
            ],
            lookback_days=60,
            source="price",
            description="Extended technical indicators (ATR, OBV, ADX, Stochastic, "
                        "Ichimoku, CCI, Williams %R, ROC, MFI, RSI divergence)",
        )

        # Fundamental features
        self._registry.register_feature_group(
            group_name="fundamental_metrics",
            category="fundamental",
            compute_fn=compute_all_fundamental_features,
            feature_names=[
                "piotroski_f_score",
                "piotroski_positive_net_income", "piotroski_positive_roa",
                "piotroski_positive_cfo", "piotroski_cfo_gt_net_income",
                "piotroski_lower_leverage", "piotroski_higher_current_ratio",
                "piotroski_no_dilution", "piotroski_higher_gross_margin",
                "piotroski_higher_asset_turnover",
                "altman_z_score", "altman_z_zone",
                "earnings_quality",
                "margin_trajectory_pct", "margin_current", "margin_3yr_avg",
                "promoter_holding_current", "promoter_holding_change_qoq",
                "fii_holding_change_qoq", "dii_holding_change_qoq",
                "fii_holding_current", "dii_holding_current",
                "revenue_growth_consistency", "revenue_growth_mean",
                "roce_latest", "roce_3yr_avg", "roce_trend",
            ],
            lookback_days=0,
            source="fundamental",
            description="Fundamental analysis features (Piotroski, Altman Z, "
                        "earnings quality, margins, holdings, growth, ROCE)",
        )

        # Macro features
        self._registry.register_feature_group(
            group_name="macro_indicators",
            category="macro",
            compute_fn=compute_all_macro_features,
            feature_names=[
                "repo_rate_current", "repo_rate_change_6m",
                "inr_usd_roc_30d", "inr_usd_current",
                "crude_oil_roc_30d", "crude_oil_current",
                "vix_level", "vix_regime",
                "fii_net_flow_7d", "fii_net_flow_30d",
                "dii_net_flow_7d", "dii_net_flow_30d",
                "fii_dii_flow_ratio",
            ],
            lookback_days=0,
            source="macro",
            description="Macro-economic indicators (repo rate, INR/USD, crude, "
                        "VIX, FII/DII flows)",
        )

        # Cross-sectional features are handled specially because they
        # need both price_data and market_data. We register them but
        # compute via the dedicated function.
        self._registry.register_feature_group(
            group_name="cross_sectional",
            category="cross_sectional",
            compute_fn=lambda _: {},  # Placeholder; computed directly in pipeline
            feature_names=[
                "relative_strength_vs_nifty",
                "rolling_beta_60d",
                "sector_momentum_rank",
                "volume_ratio_vs_20d_avg",
                "price_distance_from_52w_high_pct",
                "price_distance_from_52w_low_pct",
                "delivery_pct_vs_sector_avg",
            ],
            lookback_days=252,
            source="market",
            description="Cross-sectional features (relative strength, beta, "
                        "sector rank, 52-week range, delivery vs sector)",
        )

    async def compute_features(self, symbol: str) -> Dict[str, float]:
        """
        Compute all features for a single symbol.

        Fetches required data via the injected data fetchers, runs all
        feature categories, and returns the combined feature vector.

        Args:
            symbol: Stock ticker symbol (e.g., "RELIANCE").

        Returns:
            Dict mapping feature name -> computed value.
        """
        if not self._initialized:
            await self.initialize()

        # Check cache
        cache_ttl = self._config.feature_cache_ttl_seconds
        cached_ts = self._cache_timestamps.get(symbol, 0)
        if time.time() - cached_ts < cache_ttl and symbol in self._feature_cache:
            logger.debug("Returning cached features for %s", symbol)
            return self._feature_cache[symbol]

        start_time = time.time()
        all_features: Dict[str, float] = {}

        # Fetch data concurrently
        price_data, fundamental_data, macro_data, market_data = await self._fetch_all_data(symbol)

        # 1. Technical features (from price data)
        if price_data is not None and len(price_data) > 0:
            try:
                tech_features = compute_all_technical_features(price_data)
                all_features.update(tech_features)
            except Exception:
                logger.exception("Error computing technical features for %s", symbol)
                self._total_errors += 1

        # 2. Fundamental features
        if fundamental_data:
            try:
                fund_features = compute_all_fundamental_features(fundamental_data)
                all_features.update(fund_features)
            except Exception:
                logger.exception("Error computing fundamental features for %s", symbol)
                self._total_errors += 1

        # 3. Macro features
        if macro_data:
            try:
                macro_features = compute_all_macro_features(macro_data)
                all_features.update(macro_features)
            except Exception:
                logger.exception("Error computing macro features for %s", symbol)
                self._total_errors += 1

        # 4. Cross-sectional features (need both price + market data)
        if price_data is not None and len(price_data) > 0 and market_data:
            try:
                cs_features = compute_all_cross_sectional_features(
                    price_data, market_data, symbol
                )
                all_features.update(cs_features)
            except Exception:
                logger.exception(
                    "Error computing cross-sectional features for %s", symbol
                )
                self._total_errors += 1

        # Update cache
        self._feature_cache[symbol] = all_features
        self._cache_timestamps[symbol] = time.time()
        self._total_computations += 1

        elapsed = time.time() - start_time
        logger.info(
            "Computed %d features for %s in %.3fs",
            len(all_features),
            symbol,
            elapsed,
        )

        # Publish event
        await self._publish_feature_event(symbol, all_features)

        return all_features

    async def compute_all_symbols(
        self, symbols: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute features for multiple symbols concurrently.

        Args:
            symbols: List of stock ticker symbols.

        Returns:
            Dict mapping symbol -> feature dict.
        """
        if not self._initialized:
            await self.initialize()

        batch_size = self._config.feature_computation_batch_size
        results: Dict[str, Dict[str, float]] = {}

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i: i + batch_size]
            tasks = [self.compute_features(sym) for sym in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(
                        "Error computing features for %s: %s", sym, result
                    )
                    results[sym] = {}
                    self._total_errors += 1
                else:
                    results[sym] = result

        return results

    async def run_batch(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """
        Run a full batch computation (post-market).

        Computes features for all symbols, logs timing, and returns results.

        Args:
            symbols: List of stock ticker symbols.

        Returns:
            Dict mapping symbol -> feature dict.
        """
        start_time = time.time()
        logger.info("Starting batch feature computation for %d symbols", len(symbols))

        results = await self.compute_all_symbols(symbols)

        elapsed = time.time() - start_time
        self._last_batch_duration = elapsed

        successful = sum(1 for v in results.values() if v)
        logger.info(
            "Batch complete: %d/%d symbols computed in %.2fs (%.1f symbols/sec)",
            successful,
            len(symbols),
            elapsed,
            len(symbols) / elapsed if elapsed > 0 else 0,
        )

        return results

    def get_latest_features(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Get the most recently computed features for a symbol from cache.

        Returns None if no cached features exist or if cache has expired.
        """
        cache_ttl = self._config.feature_cache_ttl_seconds
        cached_ts = self._cache_timestamps.get(symbol, 0)

        if time.time() - cached_ts < cache_ttl and symbol in self._feature_cache:
            return self._feature_cache[symbol]

        return None

    def invalidate_cache(self, symbol: Optional[str] = None) -> None:
        """
        Invalidate the feature cache.

        Args:
            symbol: If provided, only invalidate for this symbol.
                    If None, invalidate all cached features.
        """
        if symbol:
            self._feature_cache.pop(symbol, None)
            self._cache_timestamps.pop(symbol, None)
        else:
            self._feature_cache.clear()
            self._cache_timestamps.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "initialized": self._initialized,
            "total_computations": self._total_computations,
            "total_errors": self._total_errors,
            "cached_symbols": len(self._feature_cache),
            "registered_features": self._registry.feature_count,
            "categories": self._registry.categories,
            "last_batch_duration_s": self._last_batch_duration,
        }

    # ---- Private helpers ----

    async def _fetch_all_data(self, symbol: str):
        """Fetch all data sources concurrently."""
        price_data = None
        fundamental_data = None
        macro_data = None
        market_data = None

        tasks = []
        task_names = []

        if self._price_fetcher:
            tasks.append(self._price_fetcher(symbol))
            task_names.append("price")
        if self._fundamental_fetcher:
            tasks.append(self._fundamental_fetcher(symbol))
            task_names.append("fundamental")
        if self._macro_fetcher:
            tasks.append(self._macro_fetcher())
            task_names.append("macro")
        if self._market_fetcher:
            tasks.append(self._market_fetcher(symbol))
            task_names.append("market")

        if not tasks:
            logger.warning("No data fetchers configured for FeaturePipeline")
            return price_data, fundamental_data, macro_data, market_data

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                logger.error("Error fetching %s data for %s: %s", name, symbol, result)
                continue

            if name == "price":
                price_data = result
            elif name == "fundamental":
                fundamental_data = result
            elif name == "macro":
                macro_data = result
            elif name == "market":
                market_data = result

        return price_data, fundamental_data, macro_data, market_data

    async def _publish_feature_event(
        self, symbol: str, features: Dict[str, float]
    ) -> None:
        """Publish a FeatureEvent to the event bus."""
        if self._event_bus is None:
            return

        try:
            event = FeatureEvent(
                symbol=symbol,
                feature_count=len(features),
                features=features,
            )
            await self._event_bus.publish(
                EventType.FEATURE_COMPUTED.value, event
            )
        except Exception:
            logger.exception("Error publishing FeatureEvent for %s", symbol)
