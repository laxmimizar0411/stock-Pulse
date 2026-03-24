"""
Kafka Topic Definitions for Stock Pulse Brain.

All Kafka topics are defined here as constants with their configurations.
Topics are partitioned by symbol for per-symbol ordering where applicable.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TopicConfig:
    """Configuration for a single Kafka topic."""

    name: str
    partitions: int = 6
    replication_factor: int = 1  # Set to 3 in production (multi-AZ)
    retention_ms: int = 7 * 24 * 60 * 60 * 1000  # 7 days default
    compression: str = "lz4"
    cleanup_policy: str = "delete"
    description: str = ""
    # Extra topic-level configs
    extra_config: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Raw Market Data Topics
# ---------------------------------------------------------------------------

RAW_TICKS = TopicConfig(
    name="stockpulse.raw-ticks",
    partitions=12,
    retention_ms=7 * 24 * 60 * 60 * 1000,  # 7 days, then archive to S3/Parquet
    compression="lz4",
    description="Raw tick data from broker WebSocket feeds (LTP, bid/ask, volume)",
    extra_config={"acks": "1"},  # Speed over durability for ticks
)

NORMALIZED_OHLCV = TopicConfig(
    name="stockpulse.normalized-ohlcv",
    partitions=12,
    retention_ms=30 * 24 * 60 * 60 * 1000,  # 30 days
    compression="lz4",
    description="Normalized OHLCV candles (1min, 5min, 15min, 1hr, daily)",
)

ORDER_BOOK_UPDATES = TopicConfig(
    name="stockpulse.order-book-updates",
    partitions=6,
    retention_ms=24 * 60 * 60 * 1000,  # 1 day
    compression="lz4",
    description="Market depth / order book L2 snapshots",
)

# ---------------------------------------------------------------------------
# Feature Topics
# ---------------------------------------------------------------------------

COMPUTED_FEATURES = TopicConfig(
    name="stockpulse.computed-features",
    partitions=6,
    retention_ms=7 * 24 * 60 * 60 * 1000,
    description="Real-time computed features (RSI, MACD, Bollinger, VWAP, etc.)",
)

# ---------------------------------------------------------------------------
# Signal Topics
# ---------------------------------------------------------------------------

SIGNALS = TopicConfig(
    name="stockpulse.signals",
    partitions=6,
    retention_ms=30 * 24 * 60 * 60 * 1000,  # 30 days
    compression="lz4",
    description="Unified Buy/Sell/Hold signals with confidence scores",
)

SIGNAL_RAW_TECHNICAL = TopicConfig(
    name="stockpulse.signals.raw.technical",
    partitions=6,
    retention_ms=7 * 24 * 60 * 60 * 1000,
    description="Raw technical indicator signals before fusion",
)

SIGNAL_RAW_SENTIMENT = TopicConfig(
    name="stockpulse.signals.raw.sentiment",
    partitions=6,
    retention_ms=7 * 24 * 60 * 60 * 1000,
    description="Raw sentiment signals from FinBERT/VADER/LLM pipeline",
)

SIGNAL_RAW_FUNDAMENTAL = TopicConfig(
    name="stockpulse.signals.raw.fundamental",
    partitions=6,
    retention_ms=7 * 24 * 60 * 60 * 1000,
    description="Raw fundamental analysis signals",
)

# ---------------------------------------------------------------------------
# Order & Execution Topics
# ---------------------------------------------------------------------------

ORDERS = TopicConfig(
    name="stockpulse.orders",
    partitions=6,
    retention_ms=-1,  # Indefinite retention (SEBI compliance — 5 year)
    compression="lz4",
    description="Order lifecycle events (placed, confirmed, filled, rejected)",
    extra_config={"acks": "all"},  # Full durability for orders
)

ORDER_RISK_CHECKS = TopicConfig(
    name="stockpulse.orders.risk-checks",
    partitions=3,
    retention_ms=90 * 24 * 60 * 60 * 1000,  # 90 days
    description="Pre-trade risk check results (pass/fail with reasons)",
)

# ---------------------------------------------------------------------------
# Alert & Notification Topics
# ---------------------------------------------------------------------------

ALERTS = TopicConfig(
    name="stockpulse.alerts",
    partitions=3,
    retention_ms=30 * 24 * 60 * 60 * 1000,
    description="Alert events tiered by priority (P1/P2/P3)",
)

# ---------------------------------------------------------------------------
# Agent & Research Topics
# ---------------------------------------------------------------------------

AGENT_RESEARCH = TopicConfig(
    name="stockpulse.agent.research",
    partitions=3,
    retention_ms=30 * 24 * 60 * 60 * 1000,
    description="LLM agent research outputs (bull/bear analysis, synthesis)",
)

AGENT_REPORTS = TopicConfig(
    name="stockpulse.agent.reports",
    partitions=3,
    retention_ms=90 * 24 * 60 * 60 * 1000,
    description="Generated reports (morning brief, market wrap, weekly analysis)",
)

# ---------------------------------------------------------------------------
# System Topics
# ---------------------------------------------------------------------------

DEAD_LETTER_QUEUE = TopicConfig(
    name="stockpulse.dlq",
    partitions=3,
    retention_ms=30 * 24 * 60 * 60 * 1000,
    compression="lz4",
    description="Dead letter queue for failed message processing",
)

SYSTEM_HEALTH = TopicConfig(
    name="stockpulse.system.health",
    partitions=1,
    retention_ms=7 * 24 * 60 * 60 * 1000,
    description="Service health heartbeats and status updates",
)

# ---------------------------------------------------------------------------
# Registry — All topics in one place for admin operations
# ---------------------------------------------------------------------------

ALL_TOPICS: list[TopicConfig] = [
    RAW_TICKS,
    NORMALIZED_OHLCV,
    ORDER_BOOK_UPDATES,
    COMPUTED_FEATURES,
    SIGNALS,
    SIGNAL_RAW_TECHNICAL,
    SIGNAL_RAW_SENTIMENT,
    SIGNAL_RAW_FUNDAMENTAL,
    ORDERS,
    ORDER_RISK_CHECKS,
    ALERTS,
    AGENT_RESEARCH,
    AGENT_REPORTS,
    DEAD_LETTER_QUEUE,
    SYSTEM_HEALTH,
]


def get_topic_names() -> list[str]:
    """Return all topic names."""
    return [t.name for t in ALL_TOPICS]
