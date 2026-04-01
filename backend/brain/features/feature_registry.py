"""
Feature Registry

Central registry for all Brain features. Each registered feature carries
metadata (name, category, computation function, lookback period, data source)
and can be computed individually or as a batch.

Usage:
    registry = FeatureRegistry()
    registry.register_feature(
        name="atr_14",
        category="technical",
        compute_fn=compute_atr,
        lookback_days=20,
        source="price",
    )
    features = registry.compute_all_features(symbol, price_data, fundamental_data, macro_data)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FeatureDefinition:
    """Metadata for a single registered feature."""
    name: str
    category: str  # technical, fundamental, macro, cross_sectional, volume_price
    compute_fn: Callable[..., Dict[str, float]]
    lookback_days: int
    source: str  # price, fundamental, macro, market
    description: str = ""
    enabled: bool = True


class FeatureRegistry:
    """
    Central registry that holds all feature definitions and orchestrates
    their computation.

    Features are grouped by category. Each category's compute function
    receives the relevant data slice and returns a dict of feature
    name -> value pairs.
    """

    def __init__(self) -> None:
        self._features: Dict[str, FeatureDefinition] = {}
        self._category_fns: Dict[str, List[FeatureDefinition]] = {}

    @property
    def feature_count(self) -> int:
        return len(self._features)

    @property
    def categories(self) -> List[str]:
        return list(self._category_fns.keys())

    def register_feature(
        self,
        name: str,
        category: str,
        compute_fn: Callable[..., Dict[str, float]],
        lookback_days: int = 30,
        source: str = "price",
        description: str = "",
        enabled: bool = True,
    ) -> None:
        """
        Register a single feature (or a group computed by the same function).

        Args:
            name: Unique feature name (or group name if compute_fn returns
                  multiple features).
            category: One of technical, fundamental, macro, cross_sectional.
            compute_fn: Callable that returns Dict[str, float].
            lookback_days: Minimum calendar days of history required.
            source: Data source type (price, fundamental, macro, market).
            description: Human-readable description.
            enabled: Whether the feature is active.
        """
        defn = FeatureDefinition(
            name=name,
            category=category,
            compute_fn=compute_fn,
            lookback_days=lookback_days,
            source=source,
            description=description,
            enabled=enabled,
        )
        self._features[name] = defn

        if category not in self._category_fns:
            self._category_fns[category] = []
        self._category_fns[category].append(defn)

        logger.debug("Registered feature '%s' in category '%s'", name, category)

    def register_feature_group(
        self,
        group_name: str,
        category: str,
        compute_fn: Callable[..., Dict[str, float]],
        feature_names: List[str],
        lookback_days: int = 30,
        source: str = "price",
        description: str = "",
        enabled: bool = True,
    ) -> None:
        """
        Register a group of features computed by a single function.

        The compute_fn returns a dict with keys matching feature_names.
        This is stored once so the function is only called once during
        computation.
        """
        defn = FeatureDefinition(
            name=group_name,
            category=category,
            compute_fn=compute_fn,
            lookback_days=lookback_days,
            source=source,
            description=description,
            enabled=enabled,
        )
        for fname in feature_names:
            self._features[fname] = defn

        if category not in self._category_fns:
            self._category_fns[category] = []
        self._category_fns[category].append(defn)

        logger.debug(
            "Registered feature group '%s' (%d features) in category '%s'",
            group_name,
            len(feature_names),
            category,
        )

    def compute_all_features(
        self,
        symbol: str,
        price_data: Optional[pd.DataFrame] = None,
        fundamental_data: Optional[Dict[str, Any]] = None,
        macro_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """
        Compute all registered and enabled features for a symbol.

        Args:
            symbol: Stock ticker symbol.
            price_data: OHLCV DataFrame (columns: date, open, high, low,
                        close, volume). Sorted by date ascending.
            fundamental_data: Dict of fundamental metrics.
            macro_data: Dict of macro indicators.
            market_data: Dict with market-wide data (e.g. nifty prices,
                         sector data).

        Returns:
            Dict mapping feature name -> computed value (float or NaN).
        """
        all_features: Dict[str, float] = {}
        seen_fns: set = set()

        source_map = {
            "price": price_data,
            "fundamental": fundamental_data,
            "macro": macro_data,
            "market": market_data,
        }

        for category, definitions in self._category_fns.items():
            for defn in definitions:
                if not defn.enabled:
                    continue

                fn_id = id(defn.compute_fn)
                if fn_id in seen_fns:
                    continue
                seen_fns.add(fn_id)

                data = source_map.get(defn.source)
                if data is None:
                    logger.debug(
                        "Skipping feature '%s': no %s data for %s",
                        defn.name,
                        defn.source,
                        symbol,
                    )
                    continue

                try:
                    if defn.category == "cross_sectional":
                        if price_data is None or market_data is None:
                            continue
                        result = defn.compute_fn(price_data, market_data, symbol)
                    else:
                        result = defn.compute_fn(data)
                    if isinstance(result, dict):
                        all_features.update(result)
                    else:
                        logger.warning(
                            "Feature '%s' returned non-dict: %s",
                            defn.name,
                            type(result),
                        )
                except Exception:
                    logger.exception(
                        "Error computing feature '%s' for %s",
                        defn.name,
                        symbol,
                    )

        logger.info(
            "Computed %d features for %s across %d categories",
            len(all_features),
            symbol,
            len(self._category_fns),
        )
        return all_features

    def get_feature_metadata(self) -> List[Dict[str, Any]]:
        """
        Return metadata for all registered features.

        Returns:
            List of dicts with keys: name, category, lookback_days, source,
            description, enabled.
        """
        seen: set = set()
        metadata: List[Dict[str, Any]] = []

        for name, defn in self._features.items():
            if name in seen:
                continue
            seen.add(name)
            metadata.append({
                "name": name,
                "category": defn.category,
                "lookback_days": defn.lookback_days,
                "source": defn.source,
                "description": defn.description,
                "enabled": defn.enabled,
            })

        return metadata

    def get_features_by_category(self, category: str) -> List[str]:
        """Get all feature names in a category."""
        names: List[str] = []
        for name, defn in self._features.items():
            if defn.category == category:
                names.append(name)
        return names

    def enable_feature(self, name: str) -> None:
        """Enable a feature by name."""
        if name in self._features:
            self._features[name].enabled = True

    def disable_feature(self, name: str) -> None:
        """Disable a feature by name."""
        if name in self._features:
            self._features[name].enabled = False
