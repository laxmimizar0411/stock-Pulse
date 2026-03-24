"""
Brain Configuration — Central configuration for the Stock Pulse Brain.

Loads config from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


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
    """Risk management settings."""
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
class BrainConfig:
    """Root configuration for the Stock Pulse Brain."""
    kafka: KafkaSettings = field(default_factory=KafkaSettings)
    feature_store: FeatureStoreSettings = field(default_factory=FeatureStoreSettings)
    ml: MLSettings = field(default_factory=MLSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    market_hours: MarketHoursSettings = field(default_factory=MarketHoursSettings)

    # Signal thresholds
    signal_suppress_below: float = 40.0
    signal_watchlist_below: float = 60.0
    signal_actionable_below: float = 80.0  # 60-80 = actionable
    signal_high_conviction_above: float = 80.0

    # System
    debug: bool = os.getenv("BRAIN_DEBUG", "false").lower() == "true"
    version: str = "0.1.0"

    def to_dict(self) -> dict:
        """Serialize config to dict (for health endpoints)."""
        return {
            "version": self.version,
            "debug": self.debug,
            "kafka_enabled": self.kafka.enabled,
            "kafka_servers": self.kafka.bootstrap_servers,
            "ml_model_dir": self.ml.model_dir,
            "mlflow_uri": self.ml.mlflow_tracking_uri,
            "risk_max_dd": self.risk.max_portfolio_drawdown_pct,
            "risk_kelly": self.risk.kelly_fraction,
            "signal_thresholds": {
                "suppress": self.signal_suppress_below,
                "watchlist": self.signal_watchlist_below,
                "actionable": self.signal_actionable_below,
                "high_conviction": self.signal_high_conviction_above,
            },
        }


# Global singleton
brain_config = BrainConfig()
