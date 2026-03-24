"""
Tests for Stock Pulse Brain core modules.

Tests event bus, config, signal generation, signal fusion,
confidence scoring, and risk management.
"""

import asyncio
import math
import sys
import os
import numpy as np
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


# ==================== Config Tests ====================

class TestBrainConfig:
    def test_default_config(self):
        from brain.config import BrainConfig
        config = BrainConfig()
        assert config.fusion_weights.technical == 0.30
        assert config.fusion_weights.sentiment == 0.25
        assert config.fusion_weights.fundamental == 0.20
        assert config.fusion_weights.volume == 0.15
        assert config.fusion_weights.macro == 0.10
        # Weights sum to 1
        total = (config.fusion_weights.technical + config.fusion_weights.sentiment +
                 config.fusion_weights.fundamental + config.fusion_weights.volume +
                 config.fusion_weights.macro)
        assert abs(total - 1.0) < 0.001

    def test_confidence_thresholds(self):
        from brain.config import BrainConfig
        config = BrainConfig()
        assert config.confidence_thresholds.suppress == 40.0
        assert config.confidence_thresholds.watchlist == 60.0
        assert config.confidence_thresholds.actionable == 80.0

    def test_risk_config(self):
        from brain.config import BrainConfig
        config = BrainConfig()
        assert config.risk.kelly_fraction == 0.5
        assert config.risk.kelly_fraction_bear == 0.25
        assert config.risk.drawdown_kill_pct == 20.0

    def test_module_flags_defaults(self):
        from brain.config import BrainConfig
        config = BrainConfig()
        assert config.modules.features_enabled is True
        assert config.modules.regime_enabled is True
        assert config.modules.sentiment_enabled is False  # Phase 4
        assert config.modules.agents_enabled is False     # Phase 5


# ==================== Event Bus Tests ====================

class TestEventBus:
    def test_event_bus_creation(self):
        from brain.event_bus import EventBus
        bus = EventBus(max_queue_size=100)
        assert not bus.is_running
        assert bus.event_count == 0

    @pytest.mark.asyncio
    async def test_event_bus_start_stop(self):
        from brain.event_bus import EventBus
        bus = EventBus()
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        from brain.event_bus import EventBus
        from brain.models.events import BrainEvent, EventType
        bus = EventBus()
        await bus.start()

        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test.topic", handler)

        event = BrainEvent(event_type=EventType.TICK, source="test")
        await bus.publish("test.topic", event)
        await asyncio.sleep(0.1)  # Let consumer process

        assert len(received) == 1
        assert received[0].source == "test"

        await bus.stop()

    def test_event_bus_stats(self):
        from brain.event_bus import EventBus
        bus = EventBus()
        stats = bus.get_stats()
        assert stats["running"] is False
        assert stats["total_events"] == 0


# ==================== Event Models Tests ====================

class TestEventModels:
    def test_signal_event(self):
        from brain.models.events import SignalEvent, SignalDirection, MarketRegime
        signal = SignalEvent(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            confidence=75.5,
        )
        assert signal.symbol == "RELIANCE"
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 75.5
        assert signal.event_id  # auto-generated

    def test_regime_event(self):
        from brain.models.events import RegimeEvent, MarketRegime
        event = RegimeEvent(
            regime=MarketRegime.BULL,
            bull_probability=0.7,
            bear_probability=0.1,
            sideways_probability=0.2,
        )
        assert event.regime == MarketRegime.BULL
        assert event.bull_probability == 0.7


# ==================== Signal Generator Tests ====================

class TestSignalGenerator:
    def test_technical_signal_bullish(self):
        from brain.signals.signal_generator import generate_technical_signal
        technicals = {
            "rsi_14": 30,           # oversold = bullish
            "macd_histogram": 0.5,  # positive = bullish
            "price_vs_sma50_pct": 5,  # above SMA = bullish
            "roc_10": 3,
        }
        signal = generate_technical_signal(technicals)
        assert signal.source == "technical"
        assert signal.score > 0  # bullish
        assert signal.confidence > 0

    def test_technical_signal_bearish(self):
        from brain.signals.signal_generator import generate_technical_signal
        technicals = {
            "rsi_14": 80,           # overbought = bearish
            "macd_histogram": -1.0, # negative = bearish
            "price_vs_sma50_pct": -10,  # below SMA = bearish
            "roc_10": -5,
        }
        signal = generate_technical_signal(technicals)
        assert signal.score < 0  # bearish

    def test_technical_signal_no_data(self):
        from brain.signals.signal_generator import generate_technical_signal
        signal = generate_technical_signal({})
        assert signal.confidence == 0

    def test_fundamental_signal(self):
        from brain.signals.signal_generator import generate_fundamental_signal
        fundamentals = {
            "roe": 20,
            "revenue_growth_yoy": 15,
            "debt_to_equity": 0.3,
            "pe_ratio": 20,
            "net_profit_margin": 12,
            "promoter_holding": 65,
        }
        signal = generate_fundamental_signal(fundamentals)
        assert signal.source == "fundamental"
        assert signal.score > 0  # good fundamentals = bullish

    def test_volume_signal_high_volume_up(self):
        from brain.signals.signal_generator import generate_volume_signal
        signal = generate_volume_signal({
            "volume_ratio_vs_20d_avg": 2.5,
            "price_change_pct": 3.0,
        })
        assert signal.score > 0  # high volume + up = bullish

    def test_macro_signal(self):
        from brain.signals.signal_generator import generate_macro_signal
        signal = generate_macro_signal({
            "vix_level": 12,       # low VIX = bullish
            "fii_net_flow_7d": 5000,  # positive FII = bullish
        })
        assert signal.score > 0

    def test_sentiment_stub(self):
        from brain.signals.signal_generator import generate_sentiment_signal
        signal = generate_sentiment_signal(None)
        assert signal.confidence == 0  # stubbed


# ==================== Signal Fusion Tests ====================

class TestSignalFusion:
    def test_fusion_all_bullish(self):
        from brain.signals.signal_fusion import SignalFusionEngine
        from brain.signals.signal_generator import RawSignal
        engine = SignalFusionEngine()
        signals = [
            RawSignal(source="technical", score=0.7, confidence=0.8),
            RawSignal(source="fundamental", score=0.5, confidence=0.7),
            RawSignal(source="volume", score=0.6, confidence=0.6),
            RawSignal(source="macro", score=0.3, confidence=0.5),
        ]
        result = engine.fuse_signals("RELIANCE", signals, current_price=2500)
        assert result.direction.value == "BUY"
        assert result.confidence > 40

    def test_fusion_mixed_signals(self):
        from brain.signals.signal_fusion import SignalFusionEngine
        from brain.signals.signal_generator import RawSignal
        engine = SignalFusionEngine()
        signals = [
            RawSignal(source="technical", score=0.6, confidence=0.8),
            RawSignal(source="fundamental", score=-0.4, confidence=0.7),
            RawSignal(source="volume", score=0.1, confidence=0.3),
        ]
        result = engine.fuse_signals("TCS", signals, current_price=3800)
        # Mixed signals should have lower confidence
        assert result.confidence < 80

    def test_fusion_regime_adjustment(self):
        from brain.signals.signal_fusion import SignalFusionEngine
        from brain.signals.signal_generator import RawSignal
        from brain.models.events import MarketRegime
        engine = SignalFusionEngine()
        signals = [
            RawSignal(source="technical", score=0.5, confidence=0.7),
            RawSignal(source="fundamental", score=0.3, confidence=0.6),
        ]
        # Buy signal in bear market should have lower confidence
        bear_result = engine.fuse_signals("INFY", signals, regime=MarketRegime.BEAR, current_price=1500)
        bull_result = engine.fuse_signals("INFY", signals, regime=MarketRegime.BULL, current_price=1500)
        # Confidence should generally be lower in bear for buy signals
        assert bear_result.confidence <= bull_result.confidence + 10  # some tolerance


# ==================== Risk Management Tests ====================

class TestStopLossEngine:
    def test_atr_stop_loss_buy(self):
        from brain.risk.stop_loss_engine import StopLossEngine
        engine = StopLossEngine()
        result = engine.compute_stop_loss(
            entry_price=1000,
            atr=25,
            direction="BUY",
            timeframe="swing",
        )
        assert result["stop_loss"] < 1000
        assert result["risk_pct"] > 0
        assert result["method"] == "atr_hybrid"

    def test_atr_stop_loss_sell(self):
        from brain.risk.stop_loss_engine import StopLossEngine
        engine = StopLossEngine()
        result = engine.compute_stop_loss(
            entry_price=1000,
            atr=25,
            direction="SELL",
            timeframe="swing",
        )
        assert result["stop_loss"] > 1000

    def test_trailing_stop(self):
        from brain.risk.stop_loss_engine import StopLossEngine
        engine = StopLossEngine()
        trailing = engine.compute_trailing_stop(
            highest_price_since_entry=1100,
            atr=25,
            direction="BUY",
        )
        assert trailing < 1100
        assert trailing > 0


class TestPositionSizer:
    def test_position_sizing(self):
        from brain.risk.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.compute_position_size(
            portfolio_value=1000000,
            entry_price=500,
            stop_loss=475,
            win_probability=0.55,
            avg_win_loss_ratio=1.5,
        )
        assert result["shares"] > 0
        assert result["position_pct"] <= 15  # max position limit

    def test_zero_risk(self):
        from brain.risk.position_sizer import PositionSizer
        sizer = PositionSizer()
        result = sizer.compute_position_size(
            portfolio_value=1000000,
            entry_price=500,
            stop_loss=500,  # no risk
        )
        assert "error" in result


class TestCapitalProtection:
    def test_normal_state(self):
        from brain.risk.capital_protection import CapitalProtectionEngine, ProtectionLevel
        engine = CapitalProtectionEngine()
        result = engine.update(portfolio_value=1000000)
        assert result["protection_level"] == "NORMAL"
        assert engine.new_entries_allowed

    def test_drawdown_escalation(self):
        from brain.risk.capital_protection import CapitalProtectionEngine, ProtectionLevel
        engine = CapitalProtectionEngine()

        # Set peak
        engine.update(portfolio_value=1000000)

        # 10% drawdown -> REDUCED
        result = engine.update(portfolio_value=890000)
        assert result["protection_level"] == "REDUCED"
        assert engine.position_size_multiplier == 0.5

        # 15% drawdown -> HALTED
        result = engine.update(portfolio_value=840000)
        assert result["protection_level"] == "HALTED"
        assert not engine.new_entries_allowed

        # 20% drawdown -> EMERGENCY
        result = engine.update(portfolio_value=790000)
        assert result["protection_level"] == "EMERGENCY"


class TestIndianCosts:
    def test_delivery_costs(self):
        from brain.risk.indian_costs import IndianTransactionCosts, TradeType
        costs = IndianTransactionCosts()
        result = costs.compute_costs(100000, TradeType.DELIVERY, "buy")
        assert result["stt"] == 100.0  # 0.1% of 100000
        assert result["total"] > 0

    def test_round_trip_costs(self):
        from brain.risk.indian_costs import IndianTransactionCosts, TradeType
        costs = IndianTransactionCosts()
        result = costs.compute_round_trip_costs(100000, TradeType.DELIVERY)
        assert result["total_round_trip"] > 0
        assert result["breakeven_move_pct"] > 0

    def test_ltcg_tax(self):
        from brain.risk.indian_costs import IndianTransactionCosts
        costs = IndianTransactionCosts()
        result = costs.compute_tax_impact(profit=200000, holding_days=400)
        assert result["tax_type"] == "LTCG"
        assert result["tax_rate_pct"] == 12.5
        assert result["exemption"] == 125000

    def test_stcg_tax(self):
        from brain.risk.indian_costs import IndianTransactionCosts
        costs = IndianTransactionCosts()
        result = costs.compute_tax_impact(profit=50000, holding_days=180)
        assert result["tax_type"] == "STCG"
        assert result["tax_rate_pct"] == 20.0


# ==================== Brain Registry Tests ====================

class TestBrainRegistry:
    def test_registry_creation(self):
        from brain.registry import BrainRegistry
        registry = BrainRegistry()
        assert not registry.is_started

    @pytest.mark.asyncio
    async def test_registry_startup_shutdown(self):
        from brain.registry import BrainRegistry
        registry = BrainRegistry()
        await registry.startup()
        assert registry.is_started
        status = registry.get_status()
        assert status.status == "operational"
        await registry.shutdown()
        assert not registry.is_started


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
