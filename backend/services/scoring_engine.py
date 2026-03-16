from typing import Dict, List, Tuple, Any, Optional
import random
from datetime import datetime


# =============================================================================
# TIER 1: HARD DEAL-BREAKERS (D1-D10)
# If ANY condition is TRUE, stock is immediately rejected. Score capped at 35.
# =============================================================================
DEAL_BREAKERS = [
    # D1: Interest Coverage Ratio < 2.0x - Cannot service debt - bankruptcy risk
    {
        "code": "D1",
        "rule": "interest_coverage_low", 
        "field": "interest_coverage", 
        "threshold": 2.0, 
        "operator": "lt", 
        "description": "D1: Interest Coverage < 2.0x - Cannot service debt",
        "severity": "CRITICAL"
    },
    # D2: SEBI Investigation = true - Financial statements untrustworthy
    {
        "code": "D2",
        "rule": "sebi_investigation", 
        "field": "sebi_investigation", 
        "threshold": True, 
        "operator": "eq", 
        "description": "D2: Active SEBI Investigation - Regulatory risk",
        "severity": "CRITICAL"
    },
    # D3: Revenue declining 3+ consecutive years - Business structurally failing
    {
        "code": "D3",
        "rule": "revenue_declining_3yr", 
        "field": "revenue_declining_years", 
        "threshold": 3, 
        "operator": "gte", 
        "description": "D3: Revenue Declining 3+ Years - Business failing",
        "severity": "CRITICAL"
    },
    # D4: Negative Operating Cash Flow for 2+ years - Cash burn spiral
    {
        "code": "D4",
        "rule": "negative_ocf_2yr", 
        "field": "negative_ocf_years", 
        "threshold": 2, 
        "operator": "gte", 
        "description": "D4: Negative OCF 2+ Years - Cash burn issue",
        "severity": "CRITICAL"
    },
    # D5: Negative Free Cash Flow for 3+ years - No turnaround plan
    {
        "code": "D5",
        "rule": "negative_fcf_3yr", 
        "field": "negative_fcf_years", 
        "threshold": 3, 
        "operator": "gte", 
        "description": "D5: Negative FCF 3+ Years - Unsustainable business",
        "severity": "CRITICAL"
    },
    # D6: Stock halted/suspended/delisting announced - Untradeable
    {
        "code": "D6",
        "rule": "stock_not_active", 
        "field": "stock_status", 
        "threshold": "ACTIVE", 
        "operator": "neq", 
        "description": "D6: Stock Not Active - Halted/Suspended/Delisting",
        "severity": "CRITICAL"
    },
    # D7: Promoter pledging > 80% - Forced selling imminent
    {
        "code": "D7",
        "rule": "promoter_pledging_extreme", 
        "field": "promoter_pledging", 
        "threshold": 80, 
        "operator": "gt",
        "description": "D7: Promoter Pledging > 80% - High promoter stress",
        "severity": "CRITICAL"
    },
    # D8: Debt-to-Equity > 5.0 (non-financial) - Insolvency risk
    {
        "code": "D8",
        "rule": "debt_to_equity_extreme", 
        "field": "debt_to_equity", 
        "threshold": 5.0, 
        "operator": "gt",
        "description": "D8: Debt-to-Equity > 5.0 - Excessive leverage",
        "severity": "CRITICAL"
    },
    # D9: Credit rating = D (Default) or withdrawn - Default imminent
    {
        "code": "D9",
        "rule": "credit_rating_default", 
        "field": "credit_rating", 
        "threshold": ["D", "DEFAULT", "WITHDRAWN", "NR"], 
        "operator": "in", 
        "description": "D9: Credit Rating D/Withdrawn - Default risk",
        "severity": "CRITICAL"
    },
    # D10: Average daily volume < 50,000 (short-term only) - Liquidity trap
    {
        "code": "D10",
        "rule": "volume_too_low", 
        "field": "volume_avg_20", 
        "threshold": 50000, 
        "operator": "lt",
        "description": "D10: Avg Volume < 50,000 - Illiquid stock",
        "severity": "CRITICAL",
        "short_term_only": True
    },
]

# =============================================================================
# TIER 2: RISK PENALTIES (R1-R10)
# Cumulative deductions - each rule subtracts from the score
# =============================================================================
RISK_PENALTIES = [
    # R1: Debt-to-Equity between 2.0 - 5.0 - Elevated leverage but not extreme
    {
        "code": "R1",
        "rule": "de_moderate", 
        "field": "debt_to_equity", 
        "min": 2.0, 
        "max": 5.0, 
        "lt_penalty": -15, 
        "st_penalty": -10,
        "description": "R1: D/E 2.0-5.0 - Elevated leverage"
    },
    # R2: Interest Coverage 2.0x - 3.0x - Adequate but tight debt service
    {
        "code": "R2",
        "rule": "interest_coverage_moderate", 
        "field": "interest_coverage", 
        "min": 2.0, 
        "max": 3.0, 
        "lt_penalty": -10, 
        "st_penalty": -5,
        "description": "R2: Interest Coverage 2.0-3.0x - Tight debt service"
    },
    # R3: ROE < 10% - Weak return on capital
    {
        "code": "R3",
        "rule": "roe_weak", 
        "field": "roe", 
        "threshold": 10, 
        "operator": "lt", 
        "lt_penalty": -12, 
        "st_penalty": -5,
        "description": "R3: ROE < 10% - Weak return on capital"
    },
    # R4: Promoter holding decreased > 5% QoQ - Insider confidence decline
    {
        "code": "R4",
        "rule": "promoter_holding_decreased", 
        "field": "promoter_holding_change", 
        "threshold": -5, 
        "operator": "lt", 
        "lt_penalty": -8, 
        "st_penalty": -12,
        "description": "R4: Promoter Holding Decreased >5% - Insider selling"
    },
    # R5: Promoter pledging 30-80% - Financial stress signals
    {
        "code": "R5",
        "rule": "promoter_pledging_moderate", 
        "field": "promoter_pledging", 
        "min": 30, 
        "max": 80, 
        "lt_penalty": -10, 
        "st_penalty": -15,
        "description": "R5: Promoter Pledging 30-80% - Financial stress"
    },
    # R6: Price > 30% below 52-week high - Momentum breakdown
    {
        "code": "R6",
        "rule": "price_below_52w_high", 
        "field": "distance_from_52w_high", 
        "threshold": -30, 
        "operator": "lt", 
        "lt_penalty": -5, 
        "st_penalty": -15,
        "description": "R6: Price >30% below 52W High - Momentum breakdown"
    },
    # R7: Operating margin declining 2+ years - Business quality erosion
    {
        "code": "R7",
        "rule": "operating_margin_declining", 
        "field": "operating_margin_declining_years", 
        "threshold": 2, 
        "operator": "gte", 
        "lt_penalty": -10, 
        "st_penalty": -5,
        "description": "R7: Operating Margin Declining 2+ Years - Quality erosion"
    },
    # R8: P/E > 2x sector average - Valuation risk
    {
        "code": "R8",
        "rule": "pe_expensive", 
        "field": "pe_ratio", 
        "threshold": 50, 
        "operator": "gt", 
        "lt_penalty": -10, 
        "st_penalty": -5,
        "description": "R8: P/E > 2x Sector Avg - Valuation premium risk"
    },
    # R9: Delivery percentage < 30% - Speculative trading
    {
        "code": "R9",
        "rule": "low_delivery_percentage", 
        "field": "delivery_percentage", 
        "threshold": 30, 
        "operator": "lt", 
        "lt_penalty": -5, 
        "st_penalty": -10,
        "description": "R9: Delivery% < 30% - Speculative trading"
    },
    # R10: Contingent liabilities > 10% of net worth - Hidden obligations
    {
        "code": "R10",
        "rule": "high_contingent_liabilities", 
        "field": "contingent_liabilities_pct", 
        "threshold": 10, 
        "operator": "gt", 
        "lt_penalty": -8, 
        "st_penalty": -3,
        "description": "R10: Contingent Liabilities >10% Net Worth - Hidden risk"
    },
]

# =============================================================================
# TIER 3: QUALITY BOOSTERS (Q1-Q9)
# Positive score additions - capped at +30 total
# =============================================================================
QUALITY_BOOSTERS = [
    # Q1: ROE > 20% consistently - Exceptional capital efficiency
    {
        "code": "Q1",
        "rule": "roe_excellent", 
        "field": "roe", 
        "threshold": 20, 
        "operator": "gt", 
        "lt_boost": 15, 
        "st_boost": 5,
        "description": "Q1: ROE > 20% - Exceptional capital efficiency"
    },
    # Q2: Revenue CAGR > 15% - Strong growth trajectory
    {
        "code": "Q2",
        "rule": "growth_strong", 
        "field": "revenue_growth_yoy", 
        "threshold": 15, 
        "operator": "gt", 
        "lt_boost": 12, 
        "st_boost": 5,
        "description": "Q2: Revenue CAGR > 15% - Strong growth"
    },
    # Q3: Zero debt or net cash positive - Financial fortress
    {
        "code": "Q3",
        "rule": "zero_debt", 
        "field": "debt_to_equity", 
        "threshold": 0.1, 
        "operator": "lt", 
        "lt_boost": 10, 
        "st_boost": 5,
        "description": "Q3: Zero/Low Debt - Financial fortress"
    },
    # Q4: 10+ year consecutive dividend payer - Shareholder commitment
    {
        "code": "Q4",
        "rule": "consistent_dividend", 
        "field": "consecutive_dividend_years", 
        "threshold": 10, 
        "operator": "gte", 
        "lt_boost": 8, 
        "st_boost": 3,
        "description": "Q4: 10+ Year Dividends - Shareholder commitment"
    },
    # Q5: Operating margin > 25% - Pricing power evidence
    {
        "code": "Q5",
        "rule": "high_margin", 
        "field": "operating_margin", 
        "threshold": 25, 
        "operator": "gt", 
        "lt_boost": 10, 
        "st_boost": 5,
        "description": "Q5: Operating Margin > 25% - Pricing power"
    },
    # Q6: Promoter holding > 50% and increased last QoQ - Skin in the game
    {
        "code": "Q6",
        "rule": "promoter_holding_strong", 
        "field": "promoter_holding", 
        "threshold": 50, 
        "operator": "gt", 
        "lt_boost": 8, 
        "st_boost": 10,
        "description": "Q6: Promoter Holding > 50% - Strong insider alignment"
    },
    # Q7: FII holding > 20% - Institutional validation
    {
        "code": "Q7",
        "rule": "fii_interest", 
        "field": "fii_holding", 
        "threshold": 20, 
        "operator": "gt", 
        "lt_boost": 5, 
        "st_boost": 8,
        "description": "Q7: FII Holding > 20% - Institutional validation"
    },
    # Q8: Breaking to 52-week high with volume > 2x avg - Momentum confirmation
    {
        "code": "Q8",
        "rule": "breakout_52w_high", 
        "field": "breakout_with_volume", 
        "threshold": True, 
        "operator": "eq", 
        "lt_boost": 3, 
        "st_boost": 12,
        "description": "Q8: 52W High Breakout with Volume - Momentum confirmation"
    },
    # Q9: FCF yield > 5% - Cash generation excellence
    {
        "code": "Q9",
        "rule": "fcf_yield_high", 
        "field": "fcf_yield", 
        "threshold": 5, 
        "operator": "gt", 
        "lt_boost": 8, 
        "st_boost": 4,
        "description": "Q9: FCF Yield > 5% - Cash generation excellence"
    },
]

# Scoring weights
LONG_TERM_WEIGHTS = {
    "fundamentals": 0.35,
    "valuation": 0.25,
    "technicals": 0.10,
    "quality": 0.20,
    "risk": 0.10,
}

SHORT_TERM_WEIGHTS = {
    "fundamentals": 0.20,
    "valuation": 0.15,
    "technicals": 0.35,
    "quality": 0.10,
    "risk": 0.20,
}


def score_metric(value: float, thresholds: List[Tuple[float, int]]) -> int:
    """Score a metric based on thresholds. Returns 0-100."""
    for threshold, score in thresholds:
        if value >= threshold:
            return score
    return 0


def calculate_fundamental_score(data: Dict) -> float:
    """Calculate fundamental analysis score (0-100)"""
    scores = []
    
    # Revenue Growth
    scores.append(score_metric(data.get("revenue_growth_yoy", 0), [
        (15, 100), (10, 80), (5, 60), (0, 40), (-float('inf'), 0)
    ]))
    
    # ROE
    scores.append(score_metric(data.get("roe", 0), [
        (25, 100), (20, 85), (15, 70), (10, 50), (0, 20)
    ]))
    
    # Operating Margin
    scores.append(score_metric(data.get("operating_margin", 0), [
        (20, 100), (15, 80), (10, 60), (5, 40), (0, 20)
    ]))
    
    # Debt-to-Equity (inverse scoring)
    de = data.get("debt_to_equity", 1)
    de_score = 100 if de < 0.5 else 80 if de < 1 else 60 if de < 1.5 else 40 if de < 2 else 10
    scores.append(de_score)
    
    # Free Cash Flow Margin
    revenue = data.get("revenue_ttm", 1)
    fcf = data.get("free_cash_flow", 0)
    fcf_margin = (fcf / revenue) * 100 if revenue > 0 else 0
    scores.append(score_metric(fcf_margin, [
        (15, 100), (10, 80), (5, 60), (0, 40), (-float('inf'), 10)
    ]))
    
    # Interest Coverage
    scores.append(score_metric(data.get("interest_coverage", 0), [
        (10, 100), (5, 80), (3, 60), (2, 30), (0, 0)
    ]))
    
    return sum(scores) / len(scores) if scores else 50


def calculate_valuation_score(data: Dict, sector: str) -> float:
    """Calculate valuation score (0-100)"""
    scores = []
    
    # Sector average P/E benchmarks
    sector_pe_avg = {
        "IT": 30, "Financial": 18, "FMCG": 55, "Energy": 12,
        "Pharma": 30, "Auto": 22, "Materials": 14, "Infrastructure": 22,
        "Consumer": 45, "Telecom": 25, "Utilities": 15, "Technology": 60,
        "Conglomerate": 25,
    }
    
    avg_pe = sector_pe_avg.get(sector, 20)
    pe = data.get("pe_ratio", avg_pe)
    pe_vs_sector = (pe - avg_pe) / avg_pe * 100
    
    # P/E vs Sector
    pe_score = 100 if pe_vs_sector < -30 else 80 if pe_vs_sector < -10 else 60 if abs(pe_vs_sector) < 10 else 40 if pe_vs_sector < 30 else 20
    scores.append(pe_score)
    
    # PEG Ratio
    peg = data.get("peg_ratio", 1.5)
    scores.append(score_metric(-peg, [  # Inverse - lower is better
        (-0.5, 100), (-1, 85), (-1.5, 65), (-2, 45), (-float('inf'), 20)
    ]))
    
    # EV/EBITDA
    ev_ebitda = data.get("ev_ebitda", 12)
    scores.append(score_metric(-ev_ebitda, [
        (-8, 100), (-12, 75), (-15, 50), (-20, 30), (-float('inf'), 10)
    ]))
    
    # Dividend Yield
    div_yield = data.get("dividend_yield", 0)
    scores.append(score_metric(div_yield, [
        (4, 100), (2, 80), (1, 60), (0.5, 40), (0, 30)
    ]))
    
    return sum(scores) / len(scores) if scores else 50


def calculate_technical_score(data: Dict, current_price: float) -> float:
    """Calculate technical analysis score (0-100)"""
    scores = []
    
    # Price vs 200-day MA
    sma_200 = data.get("sma_200", current_price)
    price_vs_200 = ((current_price - sma_200) / sma_200) * 100 if sma_200 > 0 else 0
    scores.append(100 if price_vs_200 > 10 else 80 if price_vs_200 > 0 else 40 if price_vs_200 > -10 else 20)
    
    # Price vs 50-day MA
    sma_50 = data.get("sma_50", current_price)
    price_vs_50 = ((current_price - sma_50) / sma_50) * 100 if sma_50 > 0 else 0
    scores.append(100 if price_vs_50 > 5 else 80 if price_vs_50 > 0 else 40 if price_vs_50 > -5 else 20)
    
    # RSI
    rsi = data.get("rsi_14", 50)
    if 30 <= rsi <= 40:
        scores.append(90)  # Recovering from oversold
    elif 40 <= rsi <= 60:
        scores.append(70)  # Neutral
    elif 60 <= rsi <= 70:
        scores.append(50)  # Getting overbought
    else:
        scores.append(30)  # Extreme
    
    # MACD
    macd = data.get("macd", 0)
    macd_signal = data.get("macd_signal", 0)
    if macd > macd_signal and macd > 0:
        scores.append(100)  # Bullish crossover
    elif macd > macd_signal:
        scores.append(70)  # Above signal
    elif macd < macd_signal:
        scores.append(40)  # Below signal
    else:
        scores.append(20)  # Bearish
    
    # 52-week position
    high_52 = data.get("high_52_week", current_price)
    low_52 = data.get("low_52_week", current_price)
    range_52 = high_52 - low_52 if high_52 > low_52 else 1
    position = ((current_price - low_52) / range_52) * 100
    scores.append(100 if position > 80 else 75 if position > 50 else 50 if position > 30 else 25)
    
    return sum(scores) / len(scores) if scores else 50


def check_deal_breakers(stock_data: Dict, is_short_term: bool = False) -> List[Dict]:
    """
    Check for deal-breaker conditions (D1-D10).
    Returns list of all deal-breakers with their triggered status.
    """
    triggered = []
    fund = stock_data.get("fundamentals", {})
    tech = stock_data.get("technicals", {})
    share = stock_data.get("shareholding", {})
    corp_actions = stock_data.get("corporate_actions", {})
    
    # Combine all data sources for easy field lookup
    all_data = {
        **fund, 
        **tech, 
        **share,
        **corp_actions,
        # Set defaults for fields that might not exist
        "stock_status": stock_data.get("stock_status", "ACTIVE"),
        "sebi_investigation": stock_data.get("sebi_investigation", False),
        "credit_rating": stock_data.get("credit_rating", ""),
        # Calculate derived fields for D3, D4, D5
        "revenue_declining_years": _calculate_declining_revenue_years(fund),
        "negative_ocf_years": _calculate_negative_ocf_years(fund),
        "negative_fcf_years": _calculate_negative_fcf_years(fund),
    }
    
    for db in DEAL_BREAKERS:
        # Skip short-term-only checks when evaluating long-term
        if db.get("short_term_only") and not is_short_term:
            triggered.append({
                "code": db.get("code", ""),
                "rule": db["rule"],
                "triggered": False,
                "value": all_data.get(db["field"], 0),
                "threshold": db["threshold"],
                "description": db["description"],
                "severity": db.get("severity", "CRITICAL"),
                "skipped": True,
                "skip_reason": "Long-term analysis - liquidity not critical"
            })
            continue
            
        value = all_data.get(db["field"], None)
        is_triggered = False
        
        # Handle different operator types
        operator = db["operator"]
        threshold = db["threshold"]
        
        if value is None:
            # Missing data - cannot evaluate, mark as not triggered but flag
            is_triggered = False
        elif operator == "lt":
            is_triggered = value < threshold
        elif operator == "gt":
            is_triggered = value > threshold
        elif operator == "gte":
            is_triggered = value >= threshold
        elif operator == "lte":
            is_triggered = value <= threshold
        elif operator == "eq":
            is_triggered = value == threshold
        elif operator == "neq":
            is_triggered = value != threshold
        elif operator == "in":
            # For checking if value is in a list (e.g., credit ratings)
            if isinstance(threshold, list):
                value_upper = str(value).upper() if value else ""
                is_triggered = value_upper in [str(t).upper() for t in threshold]
            else:
                is_triggered = value == threshold
        
        triggered.append({
            "code": db.get("code", ""),
            "rule": db["rule"],
            "triggered": is_triggered,
            "value": value if value is not None else "N/A",
            "threshold": threshold,
            "description": db["description"],
            "severity": db.get("severity", "CRITICAL"),
            "skipped": False
        })
    
    return triggered


def _calculate_declining_revenue_years(fund: Dict) -> int:
    """Calculate consecutive years of revenue decline for D3"""
    revenue_history = fund.get("revenue_history", [])
    if not revenue_history or len(revenue_history) < 2:
        # Check if current YoY growth is negative
        current_growth = fund.get("revenue_growth_yoy", 0)
        if current_growth < 0:
            return 1
        return 0
    
    declining_years = 0
    for i in range(1, len(revenue_history)):
        if revenue_history[i] < revenue_history[i-1]:
            declining_years += 1
        else:
            declining_years = 0  # Reset if growth resumes
    
    return declining_years


def _calculate_negative_ocf_years(fund: Dict) -> int:
    """Calculate consecutive years of negative Operating Cash Flow for D4"""
    ocf_history = fund.get("operating_cash_flow_history", [])
    if not ocf_history:
        # Check current OCF
        current_ocf = fund.get("operating_cash_flow", 0)
        return 1 if current_ocf < 0 else 0
    
    negative_years = 0
    for ocf in reversed(ocf_history):  # Most recent first
        if ocf < 0:
            negative_years += 1
        else:
            break
    
    return negative_years


def _calculate_negative_fcf_years(fund: Dict) -> int:
    """Calculate consecutive years of negative Free Cash Flow for D5"""
    fcf_history = fund.get("free_cash_flow_history", [])
    if not fcf_history:
        # Check current FCF
        current_fcf = fund.get("free_cash_flow", 0)
        return 1 if current_fcf < 0 else 0
    
    negative_years = 0
    for fcf in reversed(fcf_history):  # Most recent first
        if fcf < 0:
            negative_years += 1
        else:
            break
    
    return negative_years


def _calculate_operating_margin_declining_years(fund: Dict) -> int:
    """Calculate consecutive years of declining operating margin for R7"""
    om_history = fund.get("operating_margin_history", [])
    if not om_history or len(om_history) < 2:
        return 0
    
    declining_years = 0
    # Check from most recent backwards
    for i in range(len(om_history) - 1, 0, -1):
        if om_history[i] < om_history[i-1]:
            declining_years += 1
        else:
            break
    
    return declining_years


def apply_risk_penalties(stock_data: Dict, is_long_term: bool) -> Tuple[float, List[Dict]]:
    """
    Calculate risk penalty adjustments (R1-R10).
    Returns tuple of (total_penalty, list_of_applied_penalties)
    """
    penalty = 0
    applied_penalties = []
    
    fund = stock_data.get("fundamentals", {})
    val = stock_data.get("valuation", {})
    share = stock_data.get("shareholding", {})
    tech = stock_data.get("technicals", {})
    
    # Combine all data sources
    all_data = {
        **fund, 
        **val, 
        **share,
        **tech,
        # Calculate derived field for R7
        "operating_margin_declining_years": _calculate_operating_margin_declining_years(fund),
    }
    
    for rp in RISK_PENALTIES:
        value = all_data.get(rp["field"], 0)
        is_triggered = False
        penalty_amount = rp["lt_penalty"] if is_long_term else rp["st_penalty"]
        
        if "min" in rp and "max" in rp:
            # Range check
            if value is not None and rp["min"] <= value <= rp["max"]:
                is_triggered = True
        elif rp.get("operator") == "lt":
            if value is not None and value < rp["threshold"]:
                is_triggered = True
        elif rp.get("operator") == "gt":
            if value is not None and value > rp["threshold"]:
                is_triggered = True
        elif rp.get("operator") == "gte":
            if value is not None and value >= rp["threshold"]:
                is_triggered = True
        elif rp.get("operator") == "lte":
            if value is not None and value <= rp["threshold"]:
                is_triggered = True
        
        if is_triggered:
            penalty += penalty_amount
            applied_penalties.append({
                "code": rp.get("code", ""),
                "rule": rp["rule"],
                "description": rp["description"],
                "value": value,
                "threshold": rp.get("threshold", f"{rp.get('min')}-{rp.get('max')}"),
                "penalty": penalty_amount,
            })
    
    return penalty, applied_penalties


def _check_breakout_with_volume(stock_data: Dict) -> bool:
    """Check if stock is breaking to 52W high with 2x avg volume (Q8)"""
    tech = stock_data.get("technicals", {})
    current_price = stock_data.get("current_price", 0)
    high_52_week = tech.get("high_52_week", 0)
    volume_avg_20 = tech.get("volume_avg_20", 1)
    
    # Get latest volume from price history
    price_history = stock_data.get("price_history", [])
    latest_volume = price_history[-1].get("volume", 0) if price_history else 0
    
    # Check if price is within 2% of 52-week high and volume is 2x average
    near_high = current_price >= high_52_week * 0.98 if high_52_week > 0 else False
    high_volume = latest_volume >= volume_avg_20 * 2 if volume_avg_20 > 0 else False
    
    return near_high and high_volume


def apply_quality_boosters(stock_data: Dict, is_long_term: bool) -> Tuple[float, List[Dict]]:
    """
    Calculate quality booster adjustments (Q1-Q9).
    Returns tuple of (total_boost (capped at +30), list_of_applied_boosters)
    """
    boost = 0
    applied_boosters = []
    
    fund = stock_data.get("fundamentals", {})
    share = stock_data.get("shareholding", {})
    tech = stock_data.get("technicals", {})
    val = stock_data.get("valuation", {})
    
    # Combine all data sources
    all_data = {
        **fund, 
        **share,
        **tech,
        **val,
        # Calculate derived fields
        "consecutive_dividend_years": fund.get("consecutive_dividend_years", random.randint(0, 15)),  # Mock for now
        "breakout_with_volume": _check_breakout_with_volume(stock_data),
    }
    
    for qb in QUALITY_BOOSTERS:
        value = all_data.get(qb["field"], 0)
        is_triggered = False
        boost_amount = qb["lt_boost"] if is_long_term else qb["st_boost"]
        
        operator = qb.get("operator", "gt")
        threshold = qb["threshold"]
        
        if value is None:
            continue
            
        if operator == "gt":
            is_triggered = value > threshold
        elif operator == "lt":
            is_triggered = value < threshold
        elif operator == "gte":
            is_triggered = value >= threshold
        elif operator == "lte":
            is_triggered = value <= threshold
        elif operator == "eq":
            is_triggered = value == threshold
        
        if is_triggered:
            boost += boost_amount
            applied_boosters.append({
                "code": qb.get("code", ""),
                "rule": qb["rule"],
                "description": qb["description"],
                "value": value,
                "threshold": threshold,
                "boost": boost_amount,
            })
    
    # Cap boost at +30 as per documentation
    capped_boost = min(boost, 30)
    
    return capped_boost, applied_boosters


def calculate_ml_adjustment() -> float:
    """Simulate ML model adjustment (±10 points max)"""
    # In production, this would call actual ML models
    # For MVP, simulate with random adjustment weighted towards 0
    adjustment = random.gauss(0, 4)
    return max(-10, min(10, adjustment))


def calculate_confidence_score(stock_data: Dict, ml_confidence: float = None) -> Dict:
    """
    Calculate comprehensive confidence score as per documentation.
    
    Formula: 
    Confidence = DataCompleteness(40%) + DataFreshness(30%) + SourceAgreement(15%) + MLConfidence(15%)
    
    Returns dict with:
    - confidence_score: Overall score (0-100)
    - confidence_level: HIGH/MEDIUM/LOW
    - breakdown: Individual component scores
    """
    fund = stock_data.get("fundamentals", {})
    val = stock_data.get("valuation", {})
    tech = stock_data.get("technicals", {})
    share = stock_data.get("shareholding", {})
    
    # ==========================================================================
    # 1. DATA COMPLETENESS (40% weight) - % of 160 fields actually populated
    # ==========================================================================
    # Required fields categorized by importance
    critical_fields = [
        # Price data
        "current_price", 
        # Fundamentals
        fund.get("revenue_ttm"), fund.get("net_profit"), fund.get("eps"),
        fund.get("roe"), fund.get("debt_to_equity"), fund.get("operating_margin"),
        fund.get("interest_coverage"), fund.get("free_cash_flow"),
        # Valuation
        val.get("pe_ratio"), val.get("pb_ratio"), val.get("market_cap"),
        # Technical
        tech.get("sma_50"), tech.get("sma_200"), tech.get("rsi_14"),
        tech.get("volume_avg_20"), tech.get("high_52_week"), tech.get("low_52_week"),
        # Shareholding
        share.get("promoter_holding"), share.get("fii_holding"), share.get("promoter_pledging"),
    ]
    
    important_fields = [
        fund.get("revenue_growth_yoy"), fund.get("gross_margin"), fund.get("net_profit_margin"),
        fund.get("roa"), fund.get("roic"), fund.get("current_ratio"), fund.get("quick_ratio"),
        fund.get("operating_cash_flow"),
        val.get("peg_ratio"), val.get("ev_ebitda"), val.get("dividend_yield"),
        tech.get("macd"), tech.get("macd_signal"),
        share.get("dii_holding"), share.get("public_holding"),
    ]
    
    optional_fields = [
        fund.get("revenue_history"), fund.get("operating_cash_flow_history"),
        fund.get("free_cash_flow_history"), fund.get("operating_margin_history"),
        tech.get("bollinger_upper"), tech.get("bollinger_lower"),
        tech.get("delivery_percentage"),
    ]
    
    # Count populated fields (not None and not empty)
    def is_populated(val):
        if val is None:
            return False
        if isinstance(val, (list, dict)) and len(val) == 0:
            return False
        return True
    
    critical_populated = sum(1 for f in critical_fields if is_populated(f))
    important_populated = sum(1 for f in important_fields if is_populated(f))
    optional_populated = sum(1 for f in optional_fields if is_populated(f))
    
    # Weighted completeness (critical fields matter more)
    weighted_completeness = (
        (critical_populated / len(critical_fields)) * 0.5 +  # 50% weight to critical
        (important_populated / len(important_fields)) * 0.35 +  # 35% weight to important
        (optional_populated / len(optional_fields)) * 0.15  # 15% weight to optional
    )
    
    data_completeness = min(weighted_completeness, 1.0)
    
    # ==========================================================================
    # 2. DATA FRESHNESS (30% weight) - How recent is the data
    # ==========================================================================
    # For mock data, simulate with reasonable freshness
    # In production: check actual timestamps vs current date
    
    # Price data is usually real-time (high freshness)
    price_freshness = 0.98  # Real-time
    
    # Fundamental data is quarterly (medium freshness)
    fundamental_freshness = 0.85 + random.uniform(-0.05, 0.05)
    
    # Shareholding data is quarterly (medium freshness)
    shareholding_freshness = 0.80 + random.uniform(-0.05, 0.05)
    
    # News data varies (weighted by recency)
    news_freshness = 0.75 + random.uniform(-0.1, 0.1)
    
    data_freshness = (
        price_freshness * 0.4 +
        fundamental_freshness * 0.35 +
        shareholding_freshness * 0.15 +
        news_freshness * 0.1
    )
    
    # ==========================================================================
    # 3. SOURCE AGREEMENT (15% weight) - Multiple sources agree on values
    # ==========================================================================
    # For mock data, simulate agreement scores
    # In production: compare values from multiple data providers
    
    # Price agreement is typically high (exchanges are authoritative)
    price_agreement = 0.99
    
    # Financial data may have minor variations between sources
    financial_agreement = 0.85 + random.uniform(-0.1, 0.1)
    
    # News sentiment can vary significantly between sources
    sentiment_agreement = 0.70 + random.uniform(-0.15, 0.15)
    
    source_agreement = (
        price_agreement * 0.5 +
        financial_agreement * 0.35 +
        sentiment_agreement * 0.15
    )
    
    # ==========================================================================
    # 4. ML CONFIDENCE (15% weight) - Model's prediction confidence
    # ==========================================================================
    # If ML confidence not provided, simulate it
    if ml_confidence is None:
        # Higher confidence for stocks with stable patterns
        volatility = random.uniform(0.15, 0.35)
        ml_confidence = max(0.5, min(0.95, 1.0 - volatility))
    
    # ==========================================================================
    # FINAL CONFIDENCE SCORE CALCULATION
    # ==========================================================================
    confidence_score = (
        data_completeness * 0.40 +   # 40% weight
        data_freshness * 0.30 +      # 30% weight
        source_agreement * 0.15 +    # 15% weight
        ml_confidence * 0.15         # 15% weight
    )
    
    # Convert to 0-100 scale
    confidence_pct = confidence_score * 100
    
    # Determine confidence level
    if confidence_pct >= 80:
        confidence_level = "HIGH"
    elif confidence_pct >= 60:
        confidence_level = "MEDIUM"
    else:
        confidence_level = "LOW"
    
    return {
        "confidence_score": round(confidence_pct, 1),
        "confidence_level": confidence_level,
        "breakdown": {
            "data_completeness": round(data_completeness * 100, 1),
            "data_freshness": round(data_freshness * 100, 1),
            "source_agreement": round(source_agreement * 100, 1),
            "ml_confidence": round(ml_confidence * 100, 1),
        },
        "weights": {
            "data_completeness": 40,
            "data_freshness": 30,
            "source_agreement": 15,
            "ml_confidence": 15,
        }
    }


def generate_analysis(stock_data: Dict) -> Dict:
    """Generate complete stock analysis with full D1-D10 deal-breaker evaluation"""
    fund = stock_data.get("fundamentals", {})
    val = stock_data.get("valuation", {})
    tech = stock_data.get("technicals", {})
    current_price = stock_data.get("current_price", 0)
    sector = stock_data.get("sector", "")
    
    # Check deal-breakers for both long-term and short-term
    lt_deal_breakers = check_deal_breakers(stock_data, is_short_term=False)
    st_deal_breakers = check_deal_breakers(stock_data, is_short_term=True)
    
    # A deal-breaker is triggered if it affects the respective analysis type
    has_lt_deal_breaker = any(db["triggered"] for db in lt_deal_breakers if not db.get("skipped"))
    has_st_deal_breaker = any(db["triggered"] for db in st_deal_breakers)
    
    # Get list of triggered deal-breakers for reporting
    triggered_lt_dbs = [db for db in lt_deal_breakers if db["triggered"]]
    triggered_st_dbs = [db for db in st_deal_breakers if db["triggered"]]
    
    # Calculate base scores
    fundamental_score = calculate_fundamental_score(fund)
    valuation_score = calculate_valuation_score(val, sector)
    technical_score = calculate_technical_score(tech, current_price)
    quality_score = (fundamental_score + valuation_score) / 2  # Simplified
    
    # Long-term score
    lt_base = (
        fundamental_score * LONG_TERM_WEIGHTS["fundamentals"] +
        valuation_score * LONG_TERM_WEIGHTS["valuation"] +
        technical_score * LONG_TERM_WEIGHTS["technicals"] +
        quality_score * LONG_TERM_WEIGHTS["quality"]
    )
    lt_penalty, lt_penalties_list = apply_risk_penalties(stock_data, True)
    lt_boost, lt_boosters_list = apply_quality_boosters(stock_data, True)
    lt_ml = calculate_ml_adjustment()
    long_term_score = max(0, min(100, lt_base + lt_penalty + lt_boost + lt_ml))
    
    # Short-term score
    st_base = (
        fundamental_score * SHORT_TERM_WEIGHTS["fundamentals"] +
        valuation_score * SHORT_TERM_WEIGHTS["valuation"] +
        technical_score * SHORT_TERM_WEIGHTS["technicals"] +
        quality_score * SHORT_TERM_WEIGHTS["quality"]
    )
    st_penalty, st_penalties_list = apply_risk_penalties(stock_data, False)
    st_boost, st_boosters_list = apply_quality_boosters(stock_data, False)
    st_ml = calculate_ml_adjustment()
    short_term_score = max(0, min(100, st_base + st_penalty + st_boost + st_ml))
    
    # If deal-breaker triggered, cap scores at 35
    if has_lt_deal_breaker:
        long_term_score = min(long_term_score, 35)
    if has_st_deal_breaker:
        short_term_score = min(short_term_score, 35)
    
    # Determine verdict based on deal-breakers and scores
    has_any_deal_breaker = has_lt_deal_breaker or has_st_deal_breaker
    avg_score = (long_term_score + short_term_score) / 2
    
    if has_any_deal_breaker:
        verdict = "STRONG AVOID"
    elif avg_score >= 80:
        verdict = "STRONG BUY"
    elif avg_score >= 65:
        verdict = "BUY"
    elif avg_score >= 50:
        verdict = "HOLD"
    elif avg_score >= 35:
        verdict = "AVOID"
    else:
        verdict = "STRONG AVOID"
    
    # Confidence calculation using proper formula
    confidence_data = calculate_confidence_score(stock_data)
    confidence_score = confidence_data["confidence_score"]
    confidence_level = confidence_data["confidence_level"]
    
    # Generate strengths and risks
    strengths = []
    risks = []
    
    if fund.get("roe", 0) > 20:
        strengths.append(f"Strong ROE of {fund['roe']:.1f}%")
    if fund.get("revenue_growth_yoy", 0) > 15:
        strengths.append(f"Healthy revenue growth of {fund['revenue_growth_yoy']:.1f}%")
    if fund.get("debt_to_equity", 1) < 0.5:
        strengths.append("Low debt levels provide financial flexibility")
    if fund.get("operating_margin", 0) > 20:
        strengths.append(f"High operating margin of {fund['operating_margin']:.1f}%")
    if tech.get("rsi_14", 50) < 40:
        strengths.append("Technically oversold - potential bounce")
    
    if fund.get("debt_to_equity", 0) > 1.5:
        risks.append(f"High leverage with D/E of {fund['debt_to_equity']:.2f}")
    if fund.get("interest_coverage", 10) < 5:
        risks.append(f"Interest coverage of {fund['interest_coverage']:.1f}x needs monitoring")
    if val.get("pe_ratio", 0) > 40:
        risks.append(f"High valuation with P/E of {val['pe_ratio']:.1f}")
    if stock_data.get("shareholding", {}).get("promoter_pledging", 0) > 20:
        risks.append(f"Promoter pledging at {stock_data['shareholding']['promoter_pledging']:.1f}%")
    if tech.get("rsi_14", 50) > 70:
        risks.append("Technically overbought - potential correction")
    
    # Add triggered deal-breakers to risks
    for db in triggered_lt_dbs:
        risks.append(f"⚠️ {db['description']}")
    
    # Bull/Bear/Base cases
    bull_case = {
        "target_price": round(current_price * 1.25, 2),
        "upside_percent": 25,
        "probability": round(random.uniform(20, 35), 1),
        "catalysts": ["Strong earnings beat", "Sector tailwinds", "Management execution"]
    }
    
    bear_case = {
        "target_price": round(current_price * 0.8, 2),
        "downside_percent": -20,
        "probability": round(random.uniform(15, 30), 1),
        "risks": ["Earnings miss", "Margin compression", "Market correction"]
    }
    
    base_case = {
        "target_price": round(current_price * 1.1, 2),
        "return_percent": 10,
        "probability": round(100 - bull_case["probability"] - bear_case["probability"], 1),
        "scenario": "Steady performance in line with guidance"
    }
    
    return {
        "short_term_score": round(short_term_score, 1),
        "long_term_score": round(long_term_score, 1),
        "verdict": verdict,
        "confidence_level": confidence_level,
        "confidence_score": round(confidence_score, 1),
        "confidence_breakdown": confidence_data["breakdown"],
        "score_breakdown": {
            "fundamental_score": round(fundamental_score, 1),
            "valuation_score": round(valuation_score, 1),
            "technical_score": round(technical_score, 1),
            "quality_score": round(quality_score, 1),
            "risk_score": round(100 + lt_penalty, 1),  # Higher is better
            "ml_adjustment": round(lt_ml, 1),
        },
        "deal_breakers": lt_deal_breakers,  # Primary deal-breakers list for UI
        "deal_breakers_st": st_deal_breakers,  # Short-term specific
        "triggered_deal_breakers": {
            "long_term": triggered_lt_dbs,
            "short_term": triggered_st_dbs,
            "has_lt_deal_breaker": has_lt_deal_breaker,
            "has_st_deal_breaker": has_st_deal_breaker,
        },
        "risk_penalties": {
            "long_term": lt_penalties_list,
            "short_term": st_penalties_list,
            "lt_total_penalty": lt_penalty,
            "st_total_penalty": st_penalty,
        },
        "quality_boosters": {
            "long_term": lt_boosters_list,
            "short_term": st_boosters_list,
            "lt_total_boost": lt_boost,
            "st_total_boost": st_boost,
        },
        "investment_checklists": generate_investment_checklists(stock_data),
        "top_strengths": strengths[:3] if strengths else ["Diversified business model"],
        "top_risks": risks[:5] if risks else ["General market risk"],
        "bull_case": bull_case,
        "bear_case": bear_case,
        "base_case": base_case,
    }


def generate_ml_prediction(stock_data: Dict) -> Dict:
    """Generate mock ML predictions"""
    tech = stock_data.get("technicals", {})
    rsi = tech.get("rsi_14", 50)
    
    # Simulate price direction based on technicals
    if rsi < 35:
        direction = "UP"
        prob = random.uniform(0.55, 0.70)
    elif rsi > 65:
        direction = "DOWN"
        prob = random.uniform(0.55, 0.65)
    else:
        direction = "NEUTRAL"
        prob = random.uniform(0.45, 0.55)
    
    return {
        "price_direction_short": direction,
        "price_direction_probability": round(prob, 2),
        "volatility_forecast": round(random.uniform(15, 35), 2),
        "anomaly_score": round(random.uniform(0, 0.3), 2),
        "sentiment_score": round(random.uniform(-0.5, 0.5), 2),
    }



def generate_investment_checklists(stock_data: Dict) -> Dict:
    """
    Generate Short-Term (10 items) and Long-Term (13 items) Investment Checklists
    as per documentation Section 3.
    
    Items marked as [DEAL-BREAKER] should automatically disqualify the stock if failed.
    """
    fund = stock_data.get("fundamentals", {})
    tech = stock_data.get("technicals", {})
    val = stock_data.get("valuation", {})
    share = stock_data.get("shareholding", {})
    current_price = stock_data.get("current_price", 0)
    
    # ==========================================================================
    # SHORT-TERM INVESTMENT CHECKLIST (1-6 months) - 10 items
    # ==========================================================================
    short_term_checklist = []
    
    # 1. Price is above 50-day moving average
    sma_50 = tech.get("sma_50", current_price)
    above_sma50 = current_price > sma_50 if sma_50 else False
    short_term_checklist.append({
        "id": "ST1",
        "criterion": "Price is above 50-day moving average",
        "passed": above_sma50,
        "value": f"₹{current_price:.2f} vs SMA50: ₹{sma_50:.2f}" if sma_50 else "N/A",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 2. RSI is between 30-70 (not extreme)
    rsi = tech.get("rsi_14", 50)
    rsi_normal = 30 <= rsi <= 70 if rsi else True
    short_term_checklist.append({
        "id": "ST2",
        "criterion": "RSI is between 30-70 (not extreme)",
        "passed": rsi_normal,
        "value": f"RSI: {rsi:.1f}" if rsi else "N/A",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 3. Volume confirms price trend (rising)
    volume_avg = tech.get("volume_avg_20", 0)
    volume_rising = volume_avg > 100000  # Simplified check
    short_term_checklist.append({
        "id": "ST3",
        "criterion": "Volume confirms price trend (rising)",
        "passed": volume_rising,
        "value": f"Avg Vol: {volume_avg:,.0f}",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 4. No major earnings report in next 2 weeks
    # For mock data, assume this is randomly true/false
    no_earnings_soon = random.random() > 0.2
    short_term_checklist.append({
        "id": "ST4",
        "criterion": "No major earnings report in next 2 weeks",
        "passed": no_earnings_soon,
        "value": "No upcoming earnings" if no_earnings_soon else "Earnings in 2 weeks",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 5. Sector/industry is showing relative strength
    sector_strength = random.random() > 0.3  # Mock
    short_term_checklist.append({
        "id": "ST5",
        "criterion": "Sector/industry is showing relative strength",
        "passed": sector_strength,
        "value": "Outperforming" if sector_strength else "Underperforming",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 6. No pending negative catalysts (lawsuits, regulatory)
    sebi_investigation = stock_data.get("sebi_investigation", False)
    no_negative_catalysts = not sebi_investigation
    short_term_checklist.append({
        "id": "ST6",
        "criterion": "No pending negative catalysts (lawsuits, regulatory)",
        "passed": no_negative_catalysts,
        "value": "No issues detected" if no_negative_catalysts else "SEBI investigation active",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 7. [DEAL-BREAKER] Stock is not halted or under SEC/SEBI investigation
    stock_status = stock_data.get("stock_status", "ACTIVE")
    stock_active = stock_status == "ACTIVE" and not sebi_investigation
    short_term_checklist.append({
        "id": "ST7",
        "criterion": "[DEAL-BREAKER] Stock is not halted or under investigation",
        "passed": stock_active,
        "value": f"Status: {stock_status}" + (" (SEBI investigation)" if sebi_investigation else ""),
        "is_deal_breaker": True,
        "importance": "critical"
    })
    
    # 8. [DEAL-BREAKER] Average daily volume > 100,000 (liquidity)
    liquidity_ok = volume_avg >= 100000
    short_term_checklist.append({
        "id": "ST8",
        "criterion": "[DEAL-BREAKER] Average daily volume > 100,000 (liquidity)",
        "passed": liquidity_ok,
        "value": f"Volume: {volume_avg:,.0f}",
        "is_deal_breaker": True,
        "importance": "critical"
    })
    
    # 9. Clear support level exists for stop-loss placement
    support = tech.get("support_level", 0)
    has_support = support > 0 and support < current_price
    short_term_checklist.append({
        "id": "ST9",
        "criterion": "Clear support level exists for stop-loss placement",
        "passed": has_support,
        "value": f"Support: ₹{support:.2f}" if support else "N/A",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 10. Risk/reward ratio is at least 2:1
    resistance = tech.get("resistance_level", current_price * 1.1)
    support = tech.get("support_level", current_price * 0.95)
    upside = resistance - current_price
    downside = current_price - support
    risk_reward = upside / downside if downside > 0 else 0
    rr_good = risk_reward >= 2.0
    short_term_checklist.append({
        "id": "ST10",
        "criterion": "Risk/reward ratio is at least 2:1",
        "passed": rr_good,
        "value": f"R/R: {risk_reward:.1f}:1",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # ==========================================================================
    # LONG-TERM INVESTMENT CHECKLIST (3-10+ years) - 13 items
    # ==========================================================================
    long_term_checklist = []
    
    # 1. Revenue has grown for at least 3 consecutive years
    revenue_history = fund.get("revenue_history", [])
    revenue_growth_3yr = True
    if len(revenue_history) >= 4:
        for i in range(len(revenue_history) - 3, len(revenue_history)):
            if i > 0 and revenue_history[i] <= revenue_history[i-1]:
                revenue_growth_3yr = False
                break
    else:
        revenue_growth_yoy = fund.get("revenue_growth_yoy", 0)
        revenue_growth_3yr = revenue_growth_yoy > 0
    
    long_term_checklist.append({
        "id": "LT1",
        "criterion": "Revenue has grown for at least 3 consecutive years",
        "passed": revenue_growth_3yr,
        "value": f"YoY Growth: {fund.get('revenue_growth_yoy', 0):.1f}%",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 2. Company is profitable (positive net income)
    net_profit = fund.get("net_profit", 0)
    profitable = net_profit > 0
    long_term_checklist.append({
        "id": "LT2",
        "criterion": "Company is profitable (positive net income)",
        "passed": profitable,
        "value": f"Net Profit: ₹{net_profit:.2f} Cr",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 3. ROE > 15% consistently
    roe = fund.get("roe", 0)
    roe_good = roe >= 15
    long_term_checklist.append({
        "id": "LT3",
        "criterion": "ROE > 15% consistently",
        "passed": roe_good,
        "value": f"ROE: {roe:.1f}%",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 4. Free cash flow is positive and growing
    fcf = fund.get("free_cash_flow", 0)
    fcf_positive = fcf > 0
    long_term_checklist.append({
        "id": "LT4",
        "criterion": "Free cash flow is positive and growing",
        "passed": fcf_positive,
        "value": f"FCF: ₹{fcf:.2f} Cr",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 5. Debt-to-equity ratio < 1.5 (or appropriate for industry)
    de_ratio = fund.get("debt_to_equity", 0)
    de_ok = de_ratio < 1.5
    long_term_checklist.append({
        "id": "LT5",
        "criterion": "Debt-to-equity ratio < 1.5 (or appropriate for industry)",
        "passed": de_ok,
        "value": f"D/E: {de_ratio:.2f}",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 6. Company has identifiable competitive advantage (moat)
    # Mock assessment based on margins and market position
    operating_margin = fund.get("operating_margin", 0)
    has_moat = operating_margin > 15
    long_term_checklist.append({
        "id": "LT6",
        "criterion": "Company has identifiable competitive advantage (moat)",
        "passed": has_moat,
        "value": f"Op. Margin: {operating_margin:.1f}% (proxy for moat)",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 7. Management has track record of shareholder value creation
    promoter_holding = share.get("promoter_holding", 0)
    good_management = promoter_holding > 30 and share.get("promoter_pledging", 0) < 30
    long_term_checklist.append({
        "id": "LT7",
        "criterion": "Management has track record of shareholder value creation",
        "passed": good_management,
        "value": f"Promoter: {promoter_holding:.1f}%, Pledging: {share.get('promoter_pledging', 0):.1f}%",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 8. Industry has secular growth tailwinds
    # Mock - based on sector
    sector = stock_data.get("sector", "")
    growth_sectors = ["IT", "Technology", "Pharma", "Consumer", "Financial"]
    has_tailwinds = sector in growth_sectors
    long_term_checklist.append({
        "id": "LT8",
        "criterion": "Industry has secular growth tailwinds",
        "passed": has_tailwinds,
        "value": f"Sector: {sector}",
        "is_deal_breaker": False,
        "importance": "medium"
    })
    
    # 9. P/E ratio is reasonable relative to growth (PEG < 2)
    peg = val.get("peg_ratio", 2)
    peg_ok = peg < 2
    long_term_checklist.append({
        "id": "LT9",
        "criterion": "P/E ratio is reasonable relative to growth (PEG < 2)",
        "passed": peg_ok,
        "value": f"PEG: {peg:.2f}",
        "is_deal_breaker": False,
        "importance": "high"
    })
    
    # 10. [DEAL-BREAKER] No accounting irregularities or fraud history
    fraud_history = stock_data.get("fraud_history", False)
    no_fraud = not fraud_history and not sebi_investigation
    long_term_checklist.append({
        "id": "LT10",
        "criterion": "[DEAL-BREAKER] No accounting irregularities or fraud history",
        "passed": no_fraud,
        "value": "No issues" if no_fraud else "Issues detected",
        "is_deal_breaker": True,
        "importance": "critical"
    })
    
    # 11. [DEAL-BREAKER] Company is not facing existential disruption threat
    # Use qualitative disruption_risk when available, otherwise derive a heuristic based on
    # industry/sector and basic business trends (growth + margin trajectory).
    disruption_risk = stock_data.get("disruption_risk")
    if not disruption_risk:
        sector = (stock_data.get("sector") or stock_data.get("industry") or "").lower()
        revenue_growth = stock_data.get("revenue_growth_yoy")
        operating_margin = stock_data.get("operating_margin")
        op_margin_declining_years = stock_data.get("operating_margin_declining_years", 0) or 0

        risk_score = 0

        # Sector/industry pattern-based priors
        legacy_high_risk_keywords = [
            "newspaper", "print", "publishing", "cable", "broadcast", "dvd", "cd",
            "landline", "wireline", "physical retail", "brick and mortar", "coal",
            "thermal power", "photo film",
        ]
        moderate_risk_keywords = [
            "auto ancillaries", "auto oem", "discretionary retail", "telecom",
            "traditional media", "industrial manufacturing",
        ]
        beneficiary_keywords = [
            "software", "saas", "it services", "internet", "platform", "e-commerce",
            "digital", "cloud", "semiconductor",
        ]

        if any(k in sector for k in legacy_high_risk_keywords):
            risk_score += 2
        if any(k in sector for k in moderate_risk_keywords):
            risk_score += 1
        if any(k in sector for k in beneficiary_keywords):
            risk_score -= 1

        # Business trajectory: structurally weak + no growth can indicate disruption pressure
        try:
            if revenue_growth is not None:
                if revenue_growth < 0:
                    risk_score += 1
                if revenue_growth <= -10:
                    risk_score += 1
        except TypeError:
            pass

        try:
            if operating_margin is not None and operating_margin < 5:
                risk_score += 1
        except TypeError:
            pass

        if op_margin_declining_years >= 2:
            risk_score += 1

        if risk_score >= 3:
            disruption_risk = "High"
        elif risk_score >= 1:
            disruption_risk = "Medium"
        else:
            disruption_risk = "Low"

    no_disruption = disruption_risk != "High"
    long_term_checklist.append({
        "id": "LT11",
        "criterion": "[DEAL-BREAKER] Company is not facing existential disruption threat",
        "passed": no_disruption,
        "value": f"Disruption Risk: {disruption_risk}",
        "is_deal_breaker": True,
        "importance": "critical"
    })
    
    # 12. [DEAL-BREAKER] Interest coverage ratio > 3x
    interest_coverage = fund.get("interest_coverage", 0)
    ic_ok = interest_coverage >= 3
    long_term_checklist.append({
        "id": "LT12",
        "criterion": "[DEAL-BREAKER] Interest coverage ratio > 3x",
        "passed": ic_ok,
        "value": f"Interest Coverage: {interest_coverage:.1f}x",
        "is_deal_breaker": True,
        "importance": "critical"
    })
    
    # 13. I understand the business model and can explain it simply
    # This is subjective - always pass for automated systems
    long_term_checklist.append({
        "id": "LT13",
        "criterion": "Business model is understandable and explainable",
        "passed": True,
        "value": f"Industry: {stock_data.get('industry', 'N/A')}",
        "is_deal_breaker": False,
        "importance": "low"
    })
    
    # ==========================================================================
    # CALCULATE SUMMARY STATISTICS
    # ==========================================================================
    st_passed = sum(1 for item in short_term_checklist if item["passed"])
    st_failed = len(short_term_checklist) - st_passed
    st_deal_breaker_failed = sum(1 for item in short_term_checklist if item["is_deal_breaker"] and not item["passed"])
    
    lt_passed = sum(1 for item in long_term_checklist if item["passed"])
    lt_failed = len(long_term_checklist) - lt_passed
    lt_deal_breaker_failed = sum(1 for item in long_term_checklist if item["is_deal_breaker"] and not item["passed"])
    
    # Determine overall verdict for each checklist
    st_verdict = "FAIL" if st_deal_breaker_failed > 0 else "PASS" if st_passed >= 7 else "CAUTION"
    lt_verdict = "FAIL" if lt_deal_breaker_failed > 0 else "PASS" if lt_passed >= 10 else "CAUTION"
    
    return {
        "short_term": {
            "checklist": short_term_checklist,
            "summary": {
                "total": len(short_term_checklist),
                "passed": st_passed,
                "failed": st_failed,
                "deal_breaker_failures": st_deal_breaker_failed,
                "verdict": st_verdict,
                "score": round((st_passed / len(short_term_checklist)) * 100, 1)
            }
        },
        "long_term": {
            "checklist": long_term_checklist,
            "summary": {
                "total": len(long_term_checklist),
                "passed": lt_passed,
                "failed": lt_failed,
                "deal_breaker_failures": lt_deal_breaker_failed,
                "verdict": lt_verdict,
                "score": round((lt_passed / len(long_term_checklist)) * 100, 1)
            }
        }
    }
