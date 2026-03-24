"""
Signal Generator

Produces individual normalized signals from each data source:
technical, fundamental, ML model, volume, macro, and sentiment.
Each signal is normalized to [-1, +1] with confidence [0, 1].
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RawSignal:
    """A single signal from one source."""
    source: str          # "technical", "fundamental", "ml_model", "volume", "macro", "sentiment"
    score: float         # [-1, +1] where -1 = strong sell, +1 = strong buy
    confidence: float    # [0, 1]
    details: Dict[str, Any] = None

    def __post_init__(self):
        self.score = max(-1.0, min(1.0, self.score))
        self.confidence = max(0.0, min(1.0, self.confidence))
        if self.details is None:
            self.details = {}


def _sigmoid(x: float) -> float:
    """Sigmoid function for score normalization."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _normalize_to_signal(value: float, center: float, scale: float) -> float:
    """Normalize a value to [-1, +1] using sigmoid around a center point."""
    z = (value - center) / scale if scale != 0 else 0
    return 2 * _sigmoid(z) - 1


def generate_technical_signal(
    technicals: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
) -> RawSignal:
    """
    Generate a technical signal from indicator values.

    Combines RSI, MACD, moving average alignment, Bollinger Band position,
    and ADX into a single directional score.
    """
    if weights is None:
        weights = {
            "rsi": 0.25,
            "macd": 0.25,
            "ma_alignment": 0.20,
            "bollinger": 0.15,
            "momentum": 0.15,
        }

    signals = []
    details = {}

    # RSI signal: oversold (<30) = buy, overbought (>70) = sell
    rsi = technicals.get("rsi_14") or technicals.get("rsi")
    if rsi is not None and not math.isnan(rsi):
        rsi_score = _normalize_to_signal(rsi, center=50, scale=-25)  # inverted: low RSI = buy
        signals.append(("rsi", rsi_score, weights.get("rsi", 0.25)))
        details["rsi"] = {"value": rsi, "score": rsi_score}

    # MACD signal: histogram positive = buy, negative = sell
    macd_hist = technicals.get("macd_histogram") or technicals.get("macd_hist")
    if macd_hist is not None and not math.isnan(macd_hist):
        macd_score = _normalize_to_signal(macd_hist, center=0, scale=2)
        signals.append(("macd", macd_score, weights.get("macd", 0.25)))
        details["macd"] = {"histogram": macd_hist, "score": macd_score}

    # Moving average alignment: price vs SMA50 and SMA200
    price_vs_sma50 = technicals.get("price_vs_sma50_pct") or technicals.get("price_vs_sma_50")
    price_vs_sma200 = technicals.get("price_vs_sma200_pct") or technicals.get("price_vs_sma_200")
    if price_vs_sma50 is not None and not math.isnan(price_vs_sma50):
        ma_score = _normalize_to_signal(price_vs_sma50, center=0, scale=10)
        if price_vs_sma200 is not None and not math.isnan(price_vs_sma200):
            ma200_score = _normalize_to_signal(price_vs_sma200, center=0, scale=15)
            ma_score = 0.6 * ma_score + 0.4 * ma200_score
        signals.append(("ma_alignment", ma_score, weights.get("ma_alignment", 0.20)))
        details["ma_alignment"] = {"vs_sma50": price_vs_sma50, "score": ma_score}

    # Bollinger Band position: below lower = buy, above upper = sell
    bb_pct = technicals.get("bollinger_pct_b") or technicals.get("bb_percent_b")
    if bb_pct is not None and not math.isnan(bb_pct):
        # bb_pct: 0 = at lower band, 1 = at upper band
        bb_score = _normalize_to_signal(bb_pct, center=0.5, scale=-0.3)  # inverted
        signals.append(("bollinger", bb_score, weights.get("bollinger", 0.15)))
        details["bollinger"] = {"pct_b": bb_pct, "score": bb_score}

    # Momentum (ROC)
    roc = technicals.get("roc_10") or technicals.get("rate_of_change_10")
    if roc is not None and not math.isnan(roc):
        mom_score = _normalize_to_signal(roc, center=0, scale=5)
        signals.append(("momentum", mom_score, weights.get("momentum", 0.15)))
        details["momentum"] = {"roc_10": roc, "score": mom_score}

    if not signals:
        return RawSignal(source="technical", score=0.0, confidence=0.0, details={"error": "no data"})

    # Weighted combination
    total_weight = sum(w for _, _, w in signals)
    weighted_score = sum(s * w for _, s, w in signals) / total_weight if total_weight > 0 else 0

    # Confidence based on agreement: if all signals point the same way, high confidence
    sign_agreement = sum(1 for _, s, _ in signals if s * weighted_score > 0) / len(signals)
    confidence = sign_agreement * (len(signals) / 5.0)  # scale by data completeness
    confidence = min(1.0, confidence)

    return RawSignal(
        source="technical",
        score=weighted_score,
        confidence=confidence,
        details=details,
    )


def generate_fundamental_signal(
    fundamentals: Dict[str, Any],
    sector_averages: Optional[Dict[str, float]] = None,
) -> RawSignal:
    """
    Generate a fundamental signal from financial metrics.

    Considers ROE, revenue growth, debt levels, margins, and valuation.
    """
    signals = []
    details = {}

    # ROE signal: higher is better, >15% is good
    roe = fundamentals.get("roe")
    if roe is not None:
        roe_score = _normalize_to_signal(float(roe), center=12, scale=10)
        signals.append(("roe", roe_score, 0.20))
        details["roe"] = {"value": roe, "score": roe_score}

    # Revenue growth: positive is good
    rev_growth = fundamentals.get("revenue_growth_yoy")
    if rev_growth is not None:
        rg_score = _normalize_to_signal(float(rev_growth), center=10, scale=15)
        signals.append(("revenue_growth", rg_score, 0.20))
        details["revenue_growth"] = {"value": rev_growth, "score": rg_score}

    # Debt to equity: lower is better
    de = fundamentals.get("debt_to_equity")
    if de is not None:
        de_score = _normalize_to_signal(float(de), center=1.0, scale=-0.8)  # inverted
        signals.append(("debt", de_score, 0.15))
        details["debt_to_equity"] = {"value": de, "score": de_score}

    # P/E ratio: relative to sector — lower is better
    pe = fundamentals.get("pe_ratio")
    sector_pe = (sector_averages or {}).get("pe_ratio", 25)
    if pe is not None and pe > 0:
        pe_score = _normalize_to_signal(float(pe), center=float(sector_pe), scale=-10)
        signals.append(("valuation", pe_score, 0.20))
        details["pe_ratio"] = {"value": pe, "sector_avg": sector_pe, "score": pe_score}

    # Net profit margin
    npm = fundamentals.get("net_profit_margin")
    if npm is not None:
        npm_score = _normalize_to_signal(float(npm), center=8, scale=10)
        signals.append(("margin", npm_score, 0.10))
        details["net_profit_margin"] = {"value": npm, "score": npm_score}

    # Promoter holding (India-specific): higher is better
    promoter = fundamentals.get("promoter_holding")
    if promoter is not None:
        promo_score = _normalize_to_signal(float(promoter), center=50, scale=20)
        signals.append(("promoter", promo_score, 0.15))
        details["promoter_holding"] = {"value": promoter, "score": promo_score}

    if not signals:
        return RawSignal(source="fundamental", score=0.0, confidence=0.0, details={"error": "no data"})

    total_weight = sum(w for _, _, w in signals)
    weighted_score = sum(s * w for _, s, w in signals) / total_weight if total_weight > 0 else 0
    confidence = len(signals) / 6.0  # completeness-based confidence

    return RawSignal(
        source="fundamental",
        score=weighted_score,
        confidence=min(1.0, confidence),
        details=details,
    )


def generate_volume_signal(
    volume_data: Dict[str, float],
) -> RawSignal:
    """
    Generate a volume confirmation signal.

    Volume confirms or denies price moves. Above-average volume
    on up moves is bullish; above-average volume on down moves is bearish.
    """
    details = {}

    volume_ratio = volume_data.get("volume_ratio_vs_20d_avg", 1.0)
    price_change = volume_data.get("price_change_pct", 0.0)
    delivery_pct = volume_data.get("delivery_pct")

    # Volume confirms direction of price move
    if volume_ratio > 1.5 and abs(price_change) > 0.5:
        # High volume: amplify the price direction
        score = 1.0 if price_change > 0 else -1.0
        score *= min(volume_ratio / 3.0, 1.0)
        confidence = min(volume_ratio / 2.0, 1.0) * 0.8
    elif volume_ratio < 0.5:
        # Low volume: weak signal, reduce confidence
        score = 0.1 if price_change > 0 else -0.1
        confidence = 0.2
    else:
        # Normal volume: moderate signal in direction of price
        score = _normalize_to_signal(price_change, center=0, scale=2)
        confidence = 0.5

    details["volume_ratio"] = volume_ratio
    details["price_change_pct"] = price_change

    # Delivery percentage (India-specific): high delivery = genuine buying
    if delivery_pct is not None:
        if delivery_pct > 60:
            score = score * 1.2  # boost
            details["delivery_boost"] = True
        elif delivery_pct < 25:
            score = score * 0.7  # reduce (speculative)
            details["delivery_speculative"] = True
        details["delivery_pct"] = delivery_pct

    score = max(-1.0, min(1.0, score))

    return RawSignal(
        source="volume",
        score=score,
        confidence=confidence,
        details=details,
    )


def generate_macro_signal(
    macro_data: Dict[str, float],
    sector: str = "",
) -> RawSignal:
    """
    Generate a macro environment signal.

    Considers VIX, FII/DII flows, crude oil, and INR/USD
    with sector-specific impact mapping.
    """
    signals = []
    details = {}

    # VIX: low = bullish, high = bearish
    vix = macro_data.get("vix_level") or macro_data.get("india_vix")
    if vix is not None:
        vix_score = _normalize_to_signal(float(vix), center=18, scale=-8)  # inverted
        signals.append(("vix", vix_score, 0.30))
        details["vix"] = {"value": vix, "score": vix_score}

    # FII net flow: positive = bullish
    fii_flow = macro_data.get("fii_net_flow_7d")
    if fii_flow is not None:
        fii_score = _normalize_to_signal(float(fii_flow), center=0, scale=5000)
        signals.append(("fii_flow", fii_score, 0.30))
        details["fii_flow_7d"] = {"value": fii_flow, "score": fii_score}

    # Crude oil impact (sector-dependent)
    crude_roc = macro_data.get("crude_oil_roc_30d")
    if crude_roc is not None:
        # Inverse for most sectors, positive for oil companies
        oil_sectors = {"energy", "oil_gas", "oil & gas"}
        inverse_oil_sectors = {"airlines", "paints", "fmcg", "auto"}
        if sector.lower() in oil_sectors:
            crude_score = _normalize_to_signal(float(crude_roc), center=0, scale=10)
        elif sector.lower() in inverse_oil_sectors:
            crude_score = _normalize_to_signal(float(crude_roc), center=0, scale=-10)
        else:
            crude_score = _normalize_to_signal(float(crude_roc), center=0, scale=-15)  # mild negative
        signals.append(("crude", crude_score, 0.20))
        details["crude_oil"] = {"roc_30d": crude_roc, "score": crude_score}

    # INR/USD: depreciation helps IT, hurts importers
    inr_roc = macro_data.get("inr_usd_roc_30d")
    if inr_roc is not None:
        it_sectors = {"it", "technology", "information technology"}
        if sector.lower() in it_sectors:
            inr_score = _normalize_to_signal(float(inr_roc), center=0, scale=3)
        else:
            inr_score = _normalize_to_signal(float(inr_roc), center=0, scale=-3)
        signals.append(("inr_usd", inr_score, 0.20))
        details["inr_usd"] = {"roc_30d": inr_roc, "score": inr_score}

    if not signals:
        return RawSignal(source="macro", score=0.0, confidence=0.0, details={"error": "no data"})

    total_weight = sum(w for _, _, w in signals)
    weighted_score = sum(s * w for _, s, w in signals) / total_weight if total_weight > 0 else 0
    confidence = len(signals) / 4.0 * 0.8

    return RawSignal(
        source="macro",
        score=weighted_score,
        confidence=min(1.0, confidence),
        details=details,
    )


def generate_sentiment_signal(
    sentiment_data: Optional[Dict[str, float]] = None,
) -> RawSignal:
    """
    Generate a sentiment signal.

    Stub until Phase 4 (Sentiment Pipeline) is implemented.
    Returns neutral signal with zero confidence.
    """
    if sentiment_data is None:
        return RawSignal(
            source="sentiment",
            score=0.0,
            confidence=0.0,
            details={"status": "not_implemented"},
        )

    score = sentiment_data.get("sentiment_score", 0.0)
    article_count = sentiment_data.get("article_count", 0)
    confidence = min(article_count / 10.0, 1.0) * 0.8  # more articles = more confidence

    return RawSignal(
        source="sentiment",
        score=score,
        confidence=confidence,
        details=sentiment_data,
    )


def generate_ml_signal(
    ml_prediction: Optional[Dict[str, float]] = None,
) -> RawSignal:
    """
    Generate a signal from ML model predictions.

    Takes the output from the gradient boosting ensemble (Phase 3)
    and converts it to a normalized signal.
    """
    if ml_prediction is None:
        return RawSignal(
            source="ml_model",
            score=0.0,
            confidence=0.0,
            details={"status": "no_prediction"},
        )

    direction = ml_prediction.get("direction", "HOLD")
    probability = ml_prediction.get("probability", 0.5)
    predicted_return = ml_prediction.get("predicted_return_pct", 0.0)

    if direction == "BUY":
        score = probability
    elif direction == "SELL":
        score = -probability
    else:
        score = 0.0

    # Blend with return magnitude
    if predicted_return != 0:
        return_signal = _normalize_to_signal(predicted_return, center=0, scale=3)
        score = 0.7 * score + 0.3 * return_signal

    confidence = abs(probability - 0.5) * 2  # 0.5 = no confidence, 1.0 = full

    return RawSignal(
        source="ml_model",
        score=max(-1.0, min(1.0, score)),
        confidence=confidence,
        details=ml_prediction,
    )
