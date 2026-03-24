"""
Indian Market Transaction Cost Model

Precise transaction cost computation for Indian stock markets
including STT, exchange charges, GST, stamp duty, SEBI fees, and DP charges.

These costs are critical for accurate backtesting P&L — failing to model
them leads to significantly overestimated returns.
"""

import logging
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)


class TradeType(str, Enum):
    DELIVERY = "delivery"      # CNC / cash and carry
    INTRADAY = "intraday"      # MIS / intraday square-off
    FNO_FUTURES = "fno_futures"
    FNO_OPTIONS = "fno_options"


class IndianTransactionCosts:
    """
    Computes all applicable transaction costs for Indian stock market trades.

    Cost components (as of FY 2025-26):
    - STT (Securities Transaction Tax)
    - Exchange Transaction Charges (NSE/BSE)
    - GST (18% on brokerage + exchange charges)
    - Stamp Duty (state-level, applied on buy side)
    - SEBI Turnover Fees
    - DP Charges (on sell delivery)
    - Brokerage (configurable, default: discount broker rates)
    """

    # STT rates
    STT_RATES = {
        TradeType.DELIVERY: {"buy": 0.001, "sell": 0.001},      # 0.1% on both sides
        TradeType.INTRADAY: {"buy": 0.0, "sell": 0.00025},      # 0.025% on sell only
        TradeType.FNO_FUTURES: {"buy": 0.0, "sell": 0.000125},  # 0.0125% on sell
        TradeType.FNO_OPTIONS: {"buy": 0.0, "sell": 0.000625},  # 0.0625% on sell (on premium)
    }

    # Exchange transaction charges (NSE)
    EXCHANGE_CHARGES = {
        TradeType.DELIVERY: 0.0000307,      # 0.00307%
        TradeType.INTRADAY: 0.0000307,
        TradeType.FNO_FUTURES: 0.000002,    # 0.0002%
        TradeType.FNO_OPTIONS: 0.00005,     # 0.005%
    }

    # Stamp duty (on buy side only)
    STAMP_DUTY = {
        TradeType.DELIVERY: 0.00015,        # 0.015%
        TradeType.INTRADAY: 0.00003,        # 0.003%
        TradeType.FNO_FUTURES: 0.00002,     # 0.002%
        TradeType.FNO_OPTIONS: 0.00003,     # 0.003%
    }

    GST_RATE = 0.18                         # 18% on brokerage + exchange charges
    SEBI_FEES = 10 / 10_000_000             # Rs 10 per crore (0.000001)
    DP_CHARGES = 15.34                      # Per scrip, sell side delivery only

    # Default discount broker rates (Zerodha-style)
    DEFAULT_BROKERAGE = {
        TradeType.DELIVERY: 0.0,            # Zero for delivery
        TradeType.INTRADAY: 20.0,           # Rs 20 flat per order
        TradeType.FNO_FUTURES: 20.0,
        TradeType.FNO_OPTIONS: 20.0,
    }

    def compute_costs(
        self,
        trade_value: float,
        trade_type: TradeType = TradeType.DELIVERY,
        side: str = "buy",
        brokerage_per_order: float = None,
    ) -> Dict[str, float]:
        """
        Compute all transaction costs for a trade.

        Args:
            trade_value: Total trade value in INR (price * quantity)
            trade_type: Type of trade
            side: "buy" or "sell"
            brokerage_per_order: Override brokerage (None = use default)

        Returns:
            Dict with each cost component and total
        """
        side = side.lower()

        # Brokerage
        if brokerage_per_order is not None:
            brokerage = brokerage_per_order
        else:
            brokerage = self.DEFAULT_BROKERAGE.get(trade_type, 0)

        # STT
        stt_rate = self.STT_RATES.get(trade_type, {}).get(side, 0)
        stt = trade_value * stt_rate

        # Exchange charges
        exchange_rate = self.EXCHANGE_CHARGES.get(trade_type, 0)
        exchange_charges = trade_value * exchange_rate

        # GST (18% on brokerage + exchange charges)
        gst = (brokerage + exchange_charges) * self.GST_RATE

        # Stamp duty (buy side only)
        stamp_duty = 0.0
        if side == "buy":
            stamp_rate = self.STAMP_DUTY.get(trade_type, 0)
            stamp_duty = trade_value * stamp_rate

        # SEBI fees
        sebi_fees = trade_value * self.SEBI_FEES

        # DP charges (sell delivery only)
        dp_charges = 0.0
        if side == "sell" and trade_type == TradeType.DELIVERY:
            dp_charges = self.DP_CHARGES

        total = brokerage + stt + exchange_charges + gst + stamp_duty + sebi_fees + dp_charges

        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "exchange_charges": round(exchange_charges, 2),
            "gst": round(gst, 2),
            "stamp_duty": round(stamp_duty, 2),
            "sebi_fees": round(sebi_fees, 4),
            "dp_charges": round(dp_charges, 2),
            "total": round(total, 2),
            "total_pct": round((total / trade_value) * 100, 4) if trade_value > 0 else 0,
        }

    def compute_round_trip_costs(
        self,
        trade_value: float,
        trade_type: TradeType = TradeType.DELIVERY,
    ) -> Dict[str, float]:
        """Compute total costs for a buy + sell round trip."""
        buy_costs = self.compute_costs(trade_value, trade_type, "buy")
        sell_costs = self.compute_costs(trade_value, trade_type, "sell")

        total = buy_costs["total"] + sell_costs["total"]

        return {
            "buy_costs": buy_costs,
            "sell_costs": sell_costs,
            "total_round_trip": round(total, 2),
            "total_round_trip_pct": round((total / trade_value) * 100, 4) if trade_value > 0 else 0,
            "breakeven_move_pct": round((total / trade_value) * 100, 4) if trade_value > 0 else 0,
        }

    def compute_tax_impact(
        self,
        profit: float,
        holding_days: int,
        is_fno: bool = False,
    ) -> Dict[str, float]:
        """
        Compute capital gains tax on profit.

        FY 2025-26 rates:
        - STCG (< 12 months equity): 20%
        - LTCG (>= 12 months equity): 12.5% on gains > 1.25 lakh
        - Intraday/F&O: Business income (slab rate, use 30% as estimate)
        """
        if is_fno or holding_days == 0:
            # Business/speculative income
            tax_rate = 0.30
            tax = profit * tax_rate if profit > 0 else 0
            return {
                "tax_type": "business_income",
                "tax_rate_pct": 30.0,
                "taxable_amount": round(max(profit, 0), 2),
                "tax_amount": round(tax, 2),
                "post_tax_profit": round(profit - tax, 2),
            }

        if holding_days < 365:
            # STCG
            tax_rate = 0.20
            tax = profit * tax_rate if profit > 0 else 0
            return {
                "tax_type": "STCG",
                "tax_rate_pct": 20.0,
                "taxable_amount": round(max(profit, 0), 2),
                "tax_amount": round(tax, 2),
                "post_tax_profit": round(profit - tax, 2),
                "days_to_ltcg": 365 - holding_days,
            }

        # LTCG
        ltcg_exemption = 125000  # 1.25 lakh
        taxable = max(profit - ltcg_exemption, 0)
        tax_rate = 0.125
        tax = taxable * tax_rate

        return {
            "tax_type": "LTCG",
            "tax_rate_pct": 12.5,
            "exemption": ltcg_exemption,
            "taxable_amount": round(taxable, 2),
            "tax_amount": round(tax, 2),
            "post_tax_profit": round(profit - tax, 2),
        }
