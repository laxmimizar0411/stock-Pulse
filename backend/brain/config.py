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
    technical: float = 0.25
    sentiment: float = 0.15
    fundamental: float = 0.15
    volume: float = 0.10
    macro: float = 0.10
    ml_model: float = 0.25


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
class SentimentConfig:
    """Sentiment analysis pipeline parameters."""
    half_life_hours: float = 24.0            # Time-decay half-life for article weighting
    max_article_age_hours: int = 48          # Discard articles older than this
    max_articles_per_source: int = 30        # Limit per RSS source
    min_fetch_interval_minutes: int = 5      # Rate limit on RSS fetches
    finbert_enabled: bool = True             # Use FinBERT (needs transformers)
    vader_enabled: bool = True               # Use VADER (fast fallback)
    llm_enabled: bool = False                # Use LLM for contextual sentiment
    finbert_weight: float = 0.50             # Ensemble weight for FinBERT
    vader_weight: float = 0.20               # Ensemble weight for VADER
    llm_weight: float = 0.30                 # Ensemble weight for LLM
    cache_ttl_seconds: int = 300             # 5-minute cache TTL


@dataclass
class KafkaSettings:
    """Kafka connection settings."""
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    client_id: str = os.getenv("KAFKA_CLIENT_ID", "stockpulse-brain")
    group_id: str = os.getenv("KAFKA_GROUP_ID", "stockpulse-brain-group")
    enabled: bool = os.getenv("KAFKA_ENABLED", "true").lower() == "true"


@dataclass
class FeatureStoreSettings:
    """Feast feature store settings."""
    redis_host: str = os.getenv("FEAST_REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("FEAST_REDIS_PORT", "6379"))
    offline_store_dsn: str = os.getenv(
        "FEAST_OFFLINE_DSN",
        "postgresql://stockpulse:stockpulse@localhost:5432/stockpulse_ts"
    )
    repo_path: str = os.getenv("FEAST_REPO_PATH", "./feature_store/feature_repo")


@dataclass
class MLSettings:
    """ML model settings."""
    model_dir: str = os.getenv("ML_MODEL_DIR", "./models/brain")
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    onnx_runtime_enabled: bool = os.getenv("ONNX_RUNTIME_ENABLED", "true").lower() == "true"
    inference_timeout_ms: int = int(os.getenv("ML_INFERENCE_TIMEOUT_MS", "20"))


@dataclass
class LLMSettings:
    """LLM agent settings."""
    # Tier 1 — Deep reasoning
    tier1_provider: str = os.getenv("LLM_TIER1_PROVIDER", "anthropic")
    tier1_model: str = os.getenv("LLM_TIER1_MODEL", "claude-sonnet-4-20250514")

    # Tier 2 — Quick thinking
    tier2_provider: str = os.getenv("LLM_TIER2_PROVIDER", "openai")
    tier2_model: str = os.getenv("LLM_TIER2_MODEL", "gpt-4.1-mini")

    # Tier 3 — Local / open-source
    tier3_provider: str = os.getenv("LLM_TIER3_PROVIDER", "local")
    tier3_model: str = os.getenv("LLM_TIER3_MODEL", "finbert")

    # Cost controls
    max_monthly_spend_usd: float = float(os.getenv("LLM_MAX_MONTHLY_SPEND", "5000"))
    semantic_cache_enabled: bool = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"


@dataclass
class RiskSettings:
    """Risk management settings (infrastructure-level)."""
    max_portfolio_drawdown_pct: float = float(os.getenv("RISK_MAX_DD_PCT", "20.0"))
    half_position_drawdown_pct: float = float(os.getenv("RISK_HALF_DD_PCT", "10.0"))
    halt_new_entries_drawdown_pct: float = float(os.getenv("RISK_HALT_DD_PCT", "15.0"))
    daily_loss_cap_pct: float = float(os.getenv("RISK_DAILY_LOSS_CAP_PCT", "3.0"))
    max_single_position_pct: float = float(os.getenv("RISK_MAX_POSITION_PCT", "15.0"))
    max_sector_exposure_pct: float = float(os.getenv("RISK_MAX_SECTOR_PCT", "30.0"))
    kelly_fraction: float = float(os.getenv("RISK_KELLY_FRACTION", "0.5"))  # Half Kelly
    atr_multiplier: float = float(os.getenv("RISK_ATR_MULTIPLIER", "2.0"))


@dataclass
class MarketHoursSettings:
    """Indian market hours configuration."""
    pre_open_start: str = "09:00"
    pre_open_end: str = "09:15"
    market_open: str = "09:15"
    market_close: str = "15:30"
    post_close_end: str = "16:00"
    pre_market_warmup: str = "07:00"
    timezone: str = "Asia/Kolkata"


@dataclass
class ModuleFlags:
    """Feature flags to enable/disable Brain modules."""
    features_enabled: bool = True
    regime_enabled: bool = True
    ml_models_enabled: bool = True
    signal_fusion_enabled: bool = True
    sentiment_enabled: bool = True           # Phase 4 implemented
    agents_enabled: bool = False             # Disabled until Phase 5
    risk_engine_enabled: bool = False        # Disabled until Phase 6
    options_enabled: bool = False            # Disabled until Phase 8
    tax_enabled: bool = False                # Disabled until Phase 8
    rag_enabled: bool = False                # Disabled until Phase 5
    deep_learning_enabled: bool = False      # Disabled until Phase 7


@dataclass
class BrainConfig:
    """Master Brain configuration."""
    # Phase 0-3 core config
    fusion_weights: SignalFusionWeights = field(default_factory=SignalFusionWeights)
    confidence_thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    modules: ModuleFlags = field(default_factory=ModuleFlags)

    # Infrastructure settings
    kafka: KafkaSettings = field(default_factory=KafkaSettings)
    feature_store: FeatureStoreSettings = field(default_factory=FeatureStoreSettings)
    ml: MLSettings = field(default_factory=MLSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    risk_infra: RiskSettings = field(default_factory=RiskSettings)
    market_hours: MarketHoursSettings = field(default_factory=MarketHoursSettings)

    # Event bus settings
    event_bus_max_queue_size: int = 10000
    event_bus_consumer_timeout: float = 1.0

    # Model settings
    model_storage_path: str = "backend/data/brain_models"
    model_retrain_hour_ist: int = 16  # 4 PM IST, post-market

    # Feature settings
    feature_computation_batch_size: int = 50
    feature_cache_ttl_seconds: int = 300  # 5 minutes

    # Signal thresholds (aliases for confidence_thresholds)
    signal_suppress_below: float = 40.0
    signal_watchlist_below: float = 60.0
    signal_actionable_below: float = 80.0
    signal_high_conviction_above: float = 80.0

    # System
    debug: bool = os.getenv("BRAIN_DEBUG", "false").lower() == "true"
    version: str = "0.1.0"

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

        # Override sentiment params from env
        config.sentiment.half_life_hours = _env_float("SENTIMENT_HALF_LIFE_HOURS", config.sentiment.half_life_hours)
        config.sentiment.finbert_enabled = _env_bool("SENTIMENT_FINBERT_ENABLED", config.sentiment.finbert_enabled)
        config.sentiment.vader_enabled = _env_bool("SENTIMENT_VADER_ENABLED", config.sentiment.vader_enabled)
        config.sentiment.llm_enabled = _env_bool("SENTIMENT_LLM_ENABLED", config.sentiment.llm_enabled)

        return config

    def to_dict(self) -> dict:
        """Serialize config to dict (for health endpoints)."""
        return {
            "version": self.version,
            "debug": self.debug,
            "kafka_enabled": self.kafka.enabled,
            "kafka_servers": self.kafka.bootstrap_servers,
            "ml_model_dir": self.ml.model_dir,
            "mlflow_uri": self.ml.mlflow_tracking_uri,
            "risk_max_dd": self.risk_infra.max_portfolio_drawdown_pct,
            "risk_kelly": self.risk_infra.kelly_fraction,
            "signal_thresholds": {
                "suppress": self.signal_suppress_below,
                "watchlist": self.signal_watchlist_below,
                "actionable": self.signal_actionable_below,
                "high_conviction": self.signal_high_conviction_above,
            },
        }


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


# Global singleton alias (used by newer code)
brain_config = get_brain_config()
