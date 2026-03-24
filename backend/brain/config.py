"""
Brain Configuration

Central configuration for all Brain modules with feature flags,
weights, thresholds, and model parameters. All values can be
overridden via environment variables prefixed with BRAIN_.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional


def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(f"BRAIN_{key}", default))


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(f"BRAIN_{key}", default))


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(f"BRAIN_{key}")
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


@dataclass
class SignalFusionWeights:
    """Weights for multi-signal fusion. Must sum to 1.0."""
    technical: float = 0.30
    sentiment: float = 0.25
    fundamental: float = 0.20
    volume: float = 0.15
    macro: float = 0.10


@dataclass
class ConfidenceThresholds:
    """Confidence score thresholds for signal actions."""
    suppress: float = 40.0       # Below: signal suppressed
    watchlist: float = 60.0      # 40-60: add to watchlist
    actionable: float = 80.0     # 60-80: actionable with moderate sizing
    high_conviction: float = 80.0  # Above: high-conviction allocation


@dataclass
class RegimeConfig:
    """HMM regime detection parameters."""
    n_states: int = 3              # bull, bear, sideways
    retrain_frequency_days: int = 7
    lookback_years: int = 2
    features: tuple = ("daily_returns", "rolling_volatility_20d", "vix", "fii_dii_flow_momentum")


@dataclass
class RiskConfig:
    """Risk management parameters."""
    max_single_position_pct: float = 15.0   # Max % of portfolio in one stock
    max_sector_concentration_pct: float = 30.0
    daily_loss_cap_pct: float = 3.0
    drawdown_halve_pct: float = 10.0        # Halve positions at this drawdown
    drawdown_halt_pct: float = 15.0         # Halt new entries
    drawdown_kill_pct: float = 20.0         # Close all positions
    kelly_fraction: float = 0.5             # Half Kelly default
    kelly_fraction_bear: float = 0.25       # Quarter Kelly in bear regime
    atr_multiplier_day: float = 2.0
    atr_multiplier_swing: float = 2.5
    atr_multiplier_positional: float = 3.5


@dataclass
class ModuleFlags:
    """Feature flags to enable/disable Brain modules."""
    features_enabled: bool = True
    regime_enabled: bool = True
    ml_models_enabled: bool = True
    signal_fusion_enabled: bool = True
    sentiment_enabled: bool = False      # Disabled until Phase 4
    agents_enabled: bool = False         # Disabled until Phase 5
    risk_engine_enabled: bool = False    # Disabled until Phase 6
    options_enabled: bool = False        # Disabled until Phase 8
    tax_enabled: bool = False            # Disabled until Phase 8
    rag_enabled: bool = False            # Disabled until Phase 5
    deep_learning_enabled: bool = False  # Disabled until Phase 7


@dataclass
class BrainConfig:
    """Master Brain configuration."""
    fusion_weights: SignalFusionWeights = field(default_factory=SignalFusionWeights)
    confidence_thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    modules: ModuleFlags = field(default_factory=ModuleFlags)

    # Event bus settings
    event_bus_max_queue_size: int = 10000
    event_bus_consumer_timeout: float = 1.0

    # Model settings
    model_storage_path: str = "backend/data/brain_models"
    model_retrain_hour_ist: int = 16  # 4 PM IST, post-market

    # Feature settings
    feature_computation_batch_size: int = 50
    feature_cache_ttl_seconds: int = 300  # 5 minutes

    @classmethod
    def from_env(cls) -> "BrainConfig":
        """Load configuration with environment variable overrides."""
        config = cls()

        # Override fusion weights from env
        config.fusion_weights.technical = _env_float("FUSION_TECHNICAL_WEIGHT", 0.30)
        config.fusion_weights.sentiment = _env_float("FUSION_SENTIMENT_WEIGHT", 0.25)
        config.fusion_weights.fundamental = _env_float("FUSION_FUNDAMENTAL_WEIGHT", 0.20)
        config.fusion_weights.volume = _env_float("FUSION_VOLUME_WEIGHT", 0.15)
        config.fusion_weights.macro = _env_float("FUSION_MACRO_WEIGHT", 0.10)

        # Override module flags from env
        config.modules.features_enabled = _env_bool("FEATURES_ENABLED", config.modules.features_enabled)
        config.modules.regime_enabled = _env_bool("REGIME_ENABLED", config.modules.regime_enabled)
        config.modules.ml_models_enabled = _env_bool("ML_MODELS_ENABLED", config.modules.ml_models_enabled)
        config.modules.sentiment_enabled = _env_bool("SENTIMENT_ENABLED", config.modules.sentiment_enabled)
        config.modules.agents_enabled = _env_bool("AGENTS_ENABLED", config.modules.agents_enabled)
        config.modules.risk_engine_enabled = _env_bool("RISK_ENGINE_ENABLED", config.modules.risk_engine_enabled)

        # Override risk params from env
        config.risk.kelly_fraction = _env_float("KELLY_FRACTION", config.risk.kelly_fraction)
        config.risk.daily_loss_cap_pct = _env_float("DAILY_LOSS_CAP_PCT", config.risk.daily_loss_cap_pct)

        return config


# Singleton instance
_config: Optional[BrainConfig] = None


def get_brain_config() -> BrainConfig:
    """Get or create the Brain configuration singleton."""
    global _config
    if _config is None:
        _config = BrainConfig.from_env()
    return _config


def reset_brain_config():
    """Reset config singleton (useful for testing)."""
    global _config
    _config = None
