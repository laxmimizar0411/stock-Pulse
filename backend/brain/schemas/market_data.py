"""
Market Data Schemas — Pydantic models for all market data messages.

These models define the canonical format for market data flowing through
Kafka topics. All data from different broker sources is normalized into
these schemas before being published to events.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Exchange(str, Enum):
    """Indian stock exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    CDS = "CDS"


class Segment(str, Enum):
    """Trading segments."""
    EQUITY = "EQUITY"
    FO = "FO"       # Futures & Options
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"


class SignalDirection(str, Enum):
    """Signal direction."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalTimeframe(str, Enum):
    """Signal timeframe."""
    INTRADAY = "INTRADAY"
    SWING = "SWING"           # 1-5 days
    POSITIONAL = "POSITIONAL"  # 1-4 weeks
    INVESTMENT = "INVESTMENT"  # 1-12 months


class RiskLevel(str, Enum):
    """Risk classification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertPriority(str, Enum):
    """Alert priority tiers."""
    P1_CRITICAL = "P1"    # Push + SMS + Email, <10s
    P2_IMPORTANT = "P2"   # Push + Dashboard
    P3_INFO = "P3"        # Dashboard only / daily digest


class OrderStatus(str, Enum):
    """Order lifecycle status."""
    PLACED = "PLACED"
    CONFIRMED = "CONFIRMED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class MarketRegime(str, Enum):
    """HMM-detected market regime."""
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


# ---------------------------------------------------------------------------
# Raw Market Data Messages
# ---------------------------------------------------------------------------

class TickData(BaseModel):
    """Single tick / LTP update from a broker feed."""
    symbol: str = Field(..., description="NSE/BSE symbol, e.g. RELIANCE")
    exchange: Exchange
    ltp: float = Field(..., description="Last traded price")
    volume: int = Field(0, description="Traded volume")
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_qty: Optional[int] = None
    ask_qty: Optional[int] = None
    oi: Optional[int] = Field(None, description="Open interest (F&O)")
    source: str = Field("unknown", description="Data source (zerodha, angel, dhan)")


class OHLCVBar(BaseModel):
    """Normalized OHLCV candle."""
    symbol: str
    exchange: Exchange
    timeframe: str = Field(..., description="1m, 5m, 15m, 1h, 1d")
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    delivery_volume: Optional[int] = Field(None, description="Delivery qty (India-specific)")
    delivery_pct: Optional[float] = Field(None, description="Delivery % (India-specific)")
    timestamp: datetime
    source: str = "unknown"

    def validate_ohlc(self) -> bool:
        """Validate OHLC integrity: L ≤ O,C ≤ H."""
        return (
            self.low <= self.open <= self.high
            and self.low <= self.close <= self.high
            and self.volume >= 0
        )


class OrderBookSnapshot(BaseModel):
    """Level 2 market depth snapshot."""
    symbol: str
    exchange: Exchange
    timestamp: datetime
    bids: list[dict] = Field(default_factory=list, description="[{price, qty}]")
    asks: list[dict] = Field(default_factory=list, description="[{price, qty}]")
    total_bid_qty: Optional[int] = None
    total_ask_qty: Optional[int] = None


# ---------------------------------------------------------------------------
# Feature Messages
# ---------------------------------------------------------------------------

class ComputedFeatures(BaseModel):
    """Computed technical/fundamental features for a symbol."""
    symbol: str
    exchange: Exchange
    timestamp: datetime
    timeframe: str = "1d"

    # Technical indicators
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = Field(None, description="Bollinger upper band")
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = Field(None, description="Bollinger lower band")
    vwap: Optional[float] = None
    atr_14: Optional[float] = None
    obv: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    rolling_volatility_20: Optional[float] = None

    # India-specific
    delivery_pct: Optional[float] = None
    advance_decline_ratio: Optional[float] = None

    # Metadata
    feature_version: str = "1.0"


# ---------------------------------------------------------------------------
# Signal Messages
# ---------------------------------------------------------------------------

class ContributingFactor(BaseModel):
    """A single contributing factor to a signal."""
    name: str
    score: float = Field(..., ge=-1.0, le=1.0, description="Normalized score [-1, +1]")
    weight: float = Field(..., ge=0.0, le=1.0, description="Weight in final score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Factor confidence [0, 1]")


class TradingSignal(BaseModel):
    """
    Unified trading signal — the primary output of the Brain.

    Every signal contains direction, confidence, targets, risk,
    contributing factors, and a human-readable explanation.
    """
    signal_id: str
    timestamp: datetime
    ticker: str
    company: Optional[str] = None
    sector: Optional[str] = None
    exchange: Exchange = Exchange.NSE

    # Core signal
    direction: SignalDirection
    confidence: float = Field(..., ge=0.0, le=100.0, description="Confidence 0-100%")
    timeframe: SignalTimeframe

    # Price targets
    entry_price: float
    target_price: float
    stop_loss: float
    risk_reward_ratio: Optional[float] = None

    # Risk assessment
    risk_level: RiskLevel
    regime: Optional[MarketRegime] = None

    # Contributing factors
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)

    # Explainability
    natural_language_explanation: Optional[str] = None
    shap_features: Optional[list[dict]] = Field(
        None, description="Top SHAP feature attributions [{feature, value, impact}]"
    )

    # Tax awareness (Phase 4)
    pre_tax_return: Optional[float] = None
    post_tax_return: Optional[float] = None
    tax_rate_applied: Optional[float] = None
    days_to_ltcg: Optional[int] = None

    def is_actionable(self) -> bool:
        """Signal is actionable if confidence >= 60%."""
        return self.confidence >= 60.0

    def is_high_conviction(self) -> bool:
        """Signal is high-conviction if confidence >= 80%."""
        return self.confidence >= 80.0


# ---------------------------------------------------------------------------
# Order Messages
# ---------------------------------------------------------------------------

class OrderEvent(BaseModel):
    """Order lifecycle event."""
    order_id: str
    timestamp: datetime
    ticker: str
    exchange: Exchange
    direction: SignalDirection
    status: OrderStatus
    quantity: int
    price: float
    filled_quantity: int = 0
    filled_price: Optional[float] = None
    broker: str = "unknown"
    signal_id: Optional[str] = Field(None, description="Originating signal ID")
    risk_check_passed: bool = True
    rejection_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Alert Messages
# ---------------------------------------------------------------------------

class AlertEvent(BaseModel):
    """Alert notification event."""
    alert_id: str
    timestamp: datetime
    priority: AlertPriority
    title: str
    message: str
    ticker: Optional[str] = None
    signal_id: Optional[str] = None
    category: str = "general"
    data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Agent Messages
# ---------------------------------------------------------------------------

class AgentResearchOutput(BaseModel):
    """Output from an LLM research agent."""
    research_id: str
    timestamp: datetime
    agent_name: str = Field(..., description="e.g. fundamental_analyst, bull_researcher")
    ticker: str
    analysis_type: str
    summary: str
    detailed_analysis: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    data_sources: list[str] = Field(default_factory=list)
    reasoning_chain: Optional[str] = None
