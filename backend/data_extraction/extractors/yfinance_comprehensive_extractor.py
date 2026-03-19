"""
Comprehensive yfinance data extractor.

Maximizes data extraction from the yfinance Python API to cover as many of the
215 V2 data requirement fields as possible. This module sits alongside the
existing yfinance_extractor.py (which remains untouched) and can be used as a
standalone data loader or integrated into the pipeline.

yfinance API endpoints used:
    - .info              → Stock master, valuation, financial ratios, fundamentals
    - .history()         → OHLCV + adjusted close (up to 10yr)
    - .financials        → Annual income statement
    - .quarterly_financials → Quarterly income statement
    - .balance_sheet     → Annual balance sheet
    - .quarterly_balance_sheet → Quarterly balance sheet
    - .cashflow          → Annual cash flow
    - .quarterly_cashflow → Quarterly cash flow
    - .dividends         → Dividend history
    - .actions           → Splits + dividends combined
    - .calendar          → Next earnings date
    - .analyst_price_targets → Analyst consensus
    - .recommendations   → Analyst ratings
    - .major_holders     → Promoter/institutional %
    - .institutional_holders → Top institutional holders

Coverage: ~80+ fields from V2 data requirements across 10 categories.
"""

import logging
import math
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_extractor import BaseExtractor
from ..config.source_config import YFINANCE_CONFIG
from ..models.extraction_models import ExtractionRecord, ExtractionStatus, StockDataRecord

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed — YFinanceComprehensiveExtractor will not work")


# ──────────────────────────────────────────────────────────────────────────────
# Symbol resolution
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_ticker(symbol: str) -> str:
    """Convert an Indian stock symbol to its Yahoo Finance .NS ticker."""
    if symbol.endswith((".NS", ".BO")):
        return symbol
    return f"{symbol}.NS"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely convert any value to float."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely convert any value to int."""
    f = _safe_float(val)
    if f is None:
        return default
    return int(f)


def _inr_to_crores(value: Any) -> Optional[float]:
    """Convert raw INR value to Crores (÷ 1e7) for platform consistency."""
    f = _safe_float(value)
    if f is None:
        return None
    return round(f / 1e7, 2)


def _safe_pct(value: Any) -> Optional[float]:
    """Convert a ratio (0.25) to percentage (25.0) safely."""
    f = _safe_float(value)
    if f is None:
        return None
    return round(f * 100, 2)


def _get_df_value(df: pd.DataFrame, row_labels: List[str],
                  col_index: int = 0) -> Optional[float]:
    """
    Get a value from a yfinance financial DataFrame by trying multiple
    possible row label names. yfinance label names vary by company
    (e.g., 'Total Revenue' vs 'Revenue' vs 'Net Revenue').

    Args:
        df: DataFrame from .financials / .balance_sheet / .cashflow
        row_labels: List of possible row label names to try (order = priority)
        col_index: Column index (0 = most recent period)

    Returns:
        Float value or None
    """
    if df is None or df.empty:
        return None
    for label in row_labels:
        if label in df.index:
            try:
                val = df.iloc[df.index.get_loc(label), col_index]
                return _safe_float(val)
            except (IndexError, KeyError):
                continue
    return None


def _get_all_periods(df: pd.DataFrame, row_labels: List[str]) -> List[Dict[str, Any]]:
    """
    Get values for all available periods from a financial DataFrame.

    Returns list of {period: date_str, value: float} dicts.
    """
    if df is None or df.empty:
        return []
    for label in row_labels:
        if label in df.index:
            results = []
            for col in df.columns:
                val = _safe_float(df.loc[label, col])
                if val is not None:
                    period_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                    results.append({"period": period_str, "value": val})
            return results
    return []


# ──────────────────────────────────────────────────────────────────────────────
# Global market tickers
# ──────────────────────────────────────────────────────────────────────────────

GLOBAL_TICKERS = {
    "sp500":       "^GSPC",
    "nasdaq":      "^IXIC",
    "usdinr":      "USDINR=X",
    "crude_brent": "BZ=F",
    "gold":        "GC=F",
    "copper":      "HG=F",
    "india_vix":   "^INDIAVIX",
    "nifty_50":    "^NSEI",
    "sensex":      "^BSESN",
    "nifty_bank":  "^NSEBANK",
}


# ──────────────────────────────────────────────────────────────────────────────
# Main extractor class
# ──────────────────────────────────────────────────────────────────────────────

class YFinanceComprehensiveExtractor(BaseExtractor):
    """
    Comprehensive yfinance extractor that maximizes field coverage.

    Extracts data across 10 V2 categories:
        1. Stock Master Data
        2. Price & Volume (10yr OHLCV history)
        4. Income Statement (annual + quarterly)
        5. Balance Sheet (annual + quarterly)
        6. Cash Flow Statement (annual + quarterly)
        7. Financial Ratios
        8. Valuation Metrics
        9. Shareholding Pattern (approximated)
       10. Corporate Actions & Events
       Extended: Global market data (S&P500, Nasdaq, commodities, FX)
    """

    def __init__(self):
        super().__init__(YFINANCE_CONFIG)

    def get_source_name(self) -> str:
        return "yfinance_comprehensive"

    def get_provided_fields(self) -> List[str]:
        """All V2 fields this extractor can potentially provide."""
        return [
            # Cat 1: Stock Master
            "company_name", "sector", "industry", "website",
            "shares_outstanding", "market_cap_category", "face_value",
            "listing_date", "free_float_shares",
            # Cat 2: Price & Volume
            "date", "open", "high", "low", "close", "adjusted_close",
            "volume", "prev_close",
            # Cat 3: Derived Price Metrics
            "daily_return_pct", "return_5d_pct", "return_20d_pct",
            "return_60d_pct", "day_range_pct", "gap_percentage",
            "week_52_high", "week_52_low", "distance_from_52w_high",
            "volume_ratio", "avg_volume_20d",
            # Cat 4: Income Statement
            "revenue", "operating_profit", "gross_profit", "net_profit",
            "ebitda", "ebit", "interest_expense", "tax_expense", "eps",
            "operating_margin", "gross_margin", "net_profit_margin",
            # Cat 5: Balance Sheet
            "total_assets", "total_equity", "total_debt", "long_term_debt",
            "short_term_debt", "cash_and_equivalents", "current_assets",
            "current_liabilities", "inventory", "receivables", "payables",
            "intangible_assets", "book_value_per_share",
            # Cat 6: Cash Flow
            "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
            "capital_expenditure", "free_cash_flow", "dividends_paid",
            "debt_repayment",
            # Cat 7: Financial Ratios
            "roe", "roa", "debt_to_equity", "current_ratio",
            # Cat 8: Valuation
            "market_cap", "enterprise_value", "pe_ratio", "pe_ratio_forward",
            "peg_ratio", "pb_ratio", "ps_ratio", "ev_to_ebitda", "ev_to_sales",
            "dividend_yield", "earnings_yield",
            # Cat 9: Shareholding (approximated)
            "promoter_holding", "fii_holding",
            # Cat 10: Corporate Actions
            "dividend_per_share", "ex_dividend_date", "stock_split_ratio",
            "next_earnings_date",
            # Extended: Risk Metrics (calculated from price history)
            "beta_1y", "max_drawdown_1y", "sharpe_ratio_1y",
            "sortino_ratio_1y", "rolling_volatility_30d",
            "downside_deviation_1y",
            # Extended: Analyst Data
            "analyst_rating_consensus", "target_price_consensus",
            "num_analysts",
        ]

    # ──────────────────────────────────────────────────────────────────────
    # Main extraction entry point
    # ──────────────────────────────────────────────────────────────────────

    async def extract(self, symbol: str, record: StockDataRecord) -> ExtractionRecord:
        """Extract all available data from yfinance for a single symbol."""
        if not YFINANCE_AVAILABLE:
            return self._create_extraction_record(
                symbol, datetime.utcnow(), [], self.get_provided_fields(),
                "yfinance library not installed"
            )

        started_at = datetime.utcnow()
        all_extracted: List[str] = []
        errors: List[str] = []

        try:
            ticker_symbol = _resolve_ticker(symbol)
            ticker = yf.Ticker(ticker_symbol)

            # Fetch .info with retry for 429 rate limits
            info = self._fetch_info_with_retry(ticker, symbol)

            # --- Extract each category ---
            extractors = [
                ("stock_master",     lambda: self._extract_stock_master(ticker, info, symbol, record)),
                ("price_volume",     lambda: self._extract_price_history(ticker, symbol, record)),
                ("derived_metrics",  lambda: self._calculate_derived_metrics(record)),
                ("income_statement", lambda: self._extract_income_statement(ticker, info, symbol, record)),
                ("balance_sheet",    lambda: self._extract_balance_sheet(ticker, info, symbol, record)),
                ("cash_flow",        lambda: self._extract_cash_flow(ticker, symbol, record)),
                ("financial_ratios", lambda: self._extract_financial_ratios(ticker, info, record)),
                ("valuation",        lambda: self._extract_valuation(ticker, info, symbol, record)),
                ("corporate_actions", lambda: self._extract_corporate_actions(ticker, symbol, record)),
                ("shareholding",     lambda: self._extract_shareholding(ticker, symbol, record)),
                ("risk_metrics",     lambda: self._calculate_risk_metrics(ticker, record)),
                ("analyst_data",     lambda: self._extract_analyst_data(ticker, info, record)),
            ]

            for cat_name, extractor_fn in extractors:
                try:
                    fields = extractor_fn()
                    all_extracted.extend(fields)
                    if fields:
                        logger.info(f"[{symbol}] {cat_name}: {len(fields)} fields extracted")
                    else:
                        logger.debug(f"[{symbol}] {cat_name}: no fields extracted")
                except Exception as e:
                    logger.warning(f"[{symbol}] {cat_name} extraction failed: {e}")
                    errors.append(f"{cat_name}: {str(e)}")

        except Exception as e:
            logger.error(f"[{symbol}] Fatal extraction error: {e}")
            return self._create_extraction_record(
                symbol, started_at, all_extracted,
                [f for f in self.get_provided_fields() if f not in all_extracted],
                str(e)
            )

        # Deduplicate
        all_extracted = list(dict.fromkeys(all_extracted))
        fields_failed = [f for f in self.get_provided_fields() if f not in all_extracted]
        error_msg = "; ".join(errors) if errors else None

        logger.info(
            f"[{symbol}] Extraction complete: {len(all_extracted)}/{len(self.get_provided_fields())} "
            f"fields, {len(errors)} errors"
        )

        return self._create_extraction_record(
            symbol, started_at, all_extracted, fields_failed, error_msg
        )

    # ──────────────────────────────────────────────────────────────────────
    # .info fetch with 429 retry
    # ──────────────────────────────────────────────────────────────────────

    def _fetch_info_with_retry(self, ticker: Any, symbol: str,
                                max_retries: int = 3) -> Dict:
        """Fetch ticker.info with exponential backoff for 429 rate limits."""
        for attempt in range(max_retries):
            try:
                info = ticker.info
                if info:
                    return info
                return {}
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Too Many Requests" in err_str:
                    wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    logger.warning(
                        f"[{symbol}] .info 429 rate limited, retry {attempt+1}/{max_retries} "
                        f"in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"[{symbol}] Failed to fetch .info: {e}")
                    return {}
        logger.warning(f"[{symbol}] .info exhausted retries")
        return {}

    # ──────────────────────────────────────────────────────────────────────
    # Category 1: Stock Master Data
    # ──────────────────────────────────────────────────────────────────────

    def _extract_stock_master(self, ticker: Any, info: Dict, symbol: str,
                              record: StockDataRecord) -> List[str]:
        """Extract stock master data from ticker.info."""
        fields = []

        info_mapping = {
            "company_name":       ("longName", "shortName"),
            "sector":             ("sector",),
            "industry":           ("industry",),
            "website":            ("website",),
            "shares_outstanding": ("sharesOutstanding",),
            "face_value":         ("faceValue",),
            "free_float_shares":  ("floatShares",),
        }

        for field_name, keys in info_mapping.items():
            for key in keys:
                val = info.get(key)
                if val is not None:
                    if field_name in ("shares_outstanding", "free_float_shares"):
                        val = _safe_int(val)
                    record.set_field(field_name, val, self.get_source_name())
                    fields.append(field_name)
                    break

        # listing_date from .info (firstTradeDateEpochUtc)
        epoch = info.get("firstTradeDateEpochUtc")
        if epoch is not None:
            try:
                listing_dt = datetime.utcfromtimestamp(int(epoch))
                record.set_field("listing_date", listing_dt.strftime("%Y-%m-%d"),
                                 self.get_source_name())
                fields.append("listing_date")
            except Exception:
                pass

        # Derive market_cap_category from market cap
        mcap = _safe_float(info.get("marketCap"))
        if mcap is not None:
            mcap_cr = mcap / 1e7
            if mcap_cr >= 20000:
                category = "Large Cap"
            elif mcap_cr >= 5000:
                category = "Mid Cap"
            else:
                category = "Small Cap"
            record.set_field("market_cap_category", category, self.get_source_name())
            fields.append("market_cap_category")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 2: Price & Volume
    # ──────────────────────────────────────────────────────────────────────

    def _extract_price_history(self, ticker: Any, symbol: str,
                               record: StockDataRecord,
                               period: str = "10y") -> List[str]:
        """Extract OHLCV history (up to 10 years) and set latest-day fields."""
        fields = []

        try:
            hist = ticker.history(period=period, auto_adjust=False)
            if hist is None or hist.empty:
                return fields
        except Exception as e:
            logger.warning(f"[{symbol}] Price history fetch failed: {e}")
            return fields

        # Build price_history array (newest first)
        price_history = []
        for idx in reversed(hist.index):
            row = hist.loc[idx]
            price_history.append({
                "date":           idx.strftime("%Y-%m-%d"),
                "open":           round(float(row.get("Open", 0)), 2),
                "high":           round(float(row.get("High", 0)), 2),
                "low":            round(float(row.get("Low", 0)), 2),
                "close":          round(float(row.get("Close", 0)), 2),
                "adjusted_close": round(float(row.get("Adj Close", row.get("Close", 0))), 2),
                "volume":         int(row.get("Volume", 0)),
            })

        record.price_history = price_history

        # Set latest day's fields on the record
        if price_history:
            latest = price_history[0]
            for field_name in ("date", "open", "high", "low", "close",
                               "adjusted_close", "volume"):
                val = latest.get(field_name)
                if val is not None:
                    record.set_field(field_name, val, self.get_source_name())
                    if field_name not in fields:
                        fields.append(field_name)

            # prev_close from second most recent day
            if len(price_history) > 1:
                record.set_field("prev_close", price_history[1]["close"], self.get_source_name())
                fields.append("prev_close")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 4: Income Statement
    # ──────────────────────────────────────────────────────────────────────

    def _extract_income_statement(self, ticker: Any, info: Dict, symbol: str,
                                   record: StockDataRecord) -> List[str]:
        """Extract income statement from .financials and .quarterly_financials."""
        fields = []

        # --- Annual financials ---
        try:
            annual = ticker.financials
        except Exception:
            annual = None

        # --- Quarterly financials ---
        try:
            quarterly = ticker.quarterly_financials
        except Exception:
            quarterly = None

        # Use most recent data available (prefer quarterly for latest, annual for history)
        primary = quarterly if (quarterly is not None and not quarterly.empty) else annual

        if primary is None or primary.empty:
            return fields

        # Row label mappings — yfinance uses varying labels across companies
        label_map = {
            "revenue":          ["Total Revenue", "Revenue", "Net Revenue",
                                 "Operating Revenue"],
            "operating_profit": ["Operating Income", "Operating Profit",
                                 "EBIT"],
            "gross_profit":     ["Gross Profit"],
            "net_profit":       ["Net Income", "Net Income Common Stockholders",
                                 "Net Income From Continuing Operations"],
            "ebitda":           ["EBITDA", "Normalized EBITDA"],
            "ebit":             ["EBIT", "Operating Income"],
            "interest_expense": ["Interest Expense", "Interest Expense Non Operating",
                                 "Net Interest Income"],
            "tax_expense":      ["Tax Provision", "Income Tax Expense",
                                 "Tax Effect Of Unusual Items"],
        }

        for field_name, labels in label_map.items():
            val = _get_df_value(primary, labels, col_index=0)
            if val is not None:
                record.set_field(field_name, _inr_to_crores(val), self.get_source_name())
                fields.append(field_name)

        # EPS from .info (already fetched once, no extra API call)
        eps_val = _safe_float(info.get("trailingEps"))
        if eps_val is not None:
            record.set_field("eps", eps_val, self.get_source_name())
            fields.append("eps")

        # Derived margins
        revenue = _get_df_value(primary, label_map["revenue"], 0)
        if revenue and revenue != 0:
            op_profit = _get_df_value(primary, label_map["operating_profit"], 0)
            gross_profit = _get_df_value(primary, label_map["gross_profit"], 0)
            net_profit = _get_df_value(primary, label_map["net_profit"], 0)

            if op_profit is not None:
                record.set_field("operating_margin", round(op_profit / revenue * 100, 2),
                                 self.get_source_name())
                fields.append("operating_margin")
            if gross_profit is not None:
                record.set_field("gross_margin", round(gross_profit / revenue * 100, 2),
                                 self.get_source_name())
                fields.append("gross_margin")
            if net_profit is not None:
                record.set_field("net_profit_margin", round(net_profit / revenue * 100, 2),
                                 self.get_source_name())
                fields.append("net_profit_margin")

        # Store full quarterly results history
        if quarterly is not None and not quarterly.empty:
            qr_list = []
            for col_idx, col in enumerate(quarterly.columns):
                period_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                entry = {"period": period_str}
                for field_name, labels in label_map.items():
                    val = _get_df_value(quarterly, labels, col_idx)
                    if val is not None:
                        entry[field_name] = _inr_to_crores(val)
                qr_list.append(entry)
            record.quarterly_results = qr_list

        # Store full annual results history
        if annual is not None and not annual.empty:
            ar_list = []
            for col_idx, col in enumerate(annual.columns):
                period_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                entry = {"period": period_str}
                for field_name, labels in label_map.items():
                    val = _get_df_value(annual, labels, col_idx)
                    if val is not None:
                        entry[field_name] = _inr_to_crores(val)
                ar_list.append(entry)
            record.annual_results = ar_list

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 5: Balance Sheet
    # ──────────────────────────────────────────────────────────────────────

    def _extract_balance_sheet(self, ticker: Any, info: Dict, symbol: str,
                                record: StockDataRecord) -> List[str]:
        """Extract balance sheet data from .balance_sheet, .quarterly_balance_sheet,
        and .info (fallback for Indian stocks where DataFrames are often empty)."""
        fields = []

        try:
            annual_bs = ticker.balance_sheet
        except Exception:
            annual_bs = None

        try:
            quarterly_bs = ticker.quarterly_balance_sheet
        except Exception:
            quarterly_bs = None

        primary = quarterly_bs if (quarterly_bs is not None and not quarterly_bs.empty) else annual_bs

        # --- DataFrame-based extraction (works for US stocks, sometimes for Indian) ---
        if primary is not None and not primary.empty:
            label_map = {
                "total_assets":         ["Total Assets"],
                "total_equity":         ["Stockholders Equity", "Total Equity Gross Minority Interest",
                                         "Total Stockholders Equity", "Ordinary Shares Number",
                                         "Common Stock Equity"],
                "total_debt":           ["Total Debt", "Net Debt"],
                "long_term_debt":       ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
                "short_term_debt":      ["Current Debt", "Current Debt And Capital Lease Obligation",
                                         "Short Long Term Debt"],
                "cash_and_equivalents": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments",
                                         "Cash Financial", "Cash And Short Term Investments"],
                "current_assets":       ["Current Assets", "Total Current Assets"],
                "current_liabilities":  ["Current Liabilities", "Total Current Liabilities"],
                "inventory":            ["Inventory", "Raw Materials", "Finished Goods"],
                "receivables":          ["Accounts Receivable", "Receivables", "Net Receivables",
                                         "Other Receivables"],
                "payables":             ["Accounts Payable", "Payables And Accrued Expenses",
                                         "Current Accrued Expenses", "Payables"],
                "intangible_assets":    ["Intangible Assets", "Goodwill And Other Intangible Assets",
                                         "Goodwill"],
            }

            for field_name, labels in label_map.items():
                val = _get_df_value(primary, labels, col_index=0)
                if val is not None:
                    record.set_field(field_name, _inr_to_crores(val), self.get_source_name())
                    fields.append(field_name)

            # Derived: net_debt = total_debt - cash
            total_debt = _get_df_value(primary, label_map["total_debt"], 0)
            cash = _get_df_value(primary, label_map["cash_and_equivalents"], 0)
            if total_debt is not None and cash is not None:
                net_debt = total_debt - cash
                record.set_field("net_debt", _inr_to_crores(net_debt), self.get_source_name())

        # --- .info-based fallback (crucial for Indian stocks where DataFrames are empty) ---
        info_bs_map = {
            "total_debt":           ("totalDebt",),
            "total_equity":         ("totalStockholderEquity",),
            "cash_and_equivalents": ("totalCash",),
            "current_assets":       ("totalCurrentAssets",),
            "current_liabilities":  ("totalCurrentLiabilities",),
            "total_assets":         ("totalAssets",),
            "long_term_debt":       ("longTermDebt",),
            "short_term_debt":      ("shortTermDebt",),
        }

        for field_name, keys in info_bs_map.items():
            if field_name not in fields:  # Only fill if not already from DataFrame
                for key in keys:
                    val = _safe_float(info.get(key))
                    if val is not None:
                        record.set_field(field_name, _inr_to_crores(val),
                                         self.get_source_name())
                        fields.append(field_name)
                        break

        # book_value_per_share from .info
        bvps = _safe_float(info.get("bookValue"))
        if bvps is not None:
            record.set_field("book_value_per_share", bvps, self.get_source_name())
            fields.append("book_value_per_share")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 6: Cash Flow Statement
    # ──────────────────────────────────────────────────────────────────────

    def _extract_cash_flow(self, ticker: Any, symbol: str,
                            record: StockDataRecord) -> List[str]:
        """Extract cash flow data from .cashflow and .quarterly_cashflow."""
        fields = []

        try:
            annual_cf = ticker.cashflow
        except Exception:
            annual_cf = None

        try:
            quarterly_cf = ticker.quarterly_cashflow
        except Exception:
            quarterly_cf = None

        primary = annual_cf  # Cash flow is typically best at annual level

        if primary is None or primary.empty:
            return fields

        label_map = {
            "operating_cash_flow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
                                    "Total Cash From Operating Activities"],
            "investing_cash_flow": ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities",
                                    "Total Cashflows From Investing Activities"],
            "financing_cash_flow": ["Financing Cash Flow", "Cash Flow From Continuing Financing Activities",
                                    "Total Cash From Financing Activities"],
            "capital_expenditure": ["Capital Expenditure", "Purchase Of PPE",
                                    "Capital Expenditures"],
            "free_cash_flow":      ["Free Cash Flow"],
            "dividends_paid":      ["Common Stock Dividend Paid", "Cash Dividends Paid",
                                    "Payment Of Dividends"],
            "debt_repayment":      ["Repayment Of Debt", "Long Term Debt Payments",
                                    "Net Long Term Debt Issuance"],
        }

        for field_name, labels in label_map.items():
            val = _get_df_value(primary, labels, col_index=0)
            if val is not None:
                # CapEx is typically negative in yfinance — store as positive
                if field_name == "capital_expenditure":
                    val = abs(val)
                # Dividends paid is typically negative — store as positive
                if field_name == "dividends_paid":
                    val = abs(val)
                record.set_field(field_name, _inr_to_crores(val), self.get_source_name())
                fields.append(field_name)

        # If FCF not directly available, derive: OCF - CapEx
        if "free_cash_flow" not in fields:
            ocf = _get_df_value(primary, label_map["operating_cash_flow"], 0)
            capex = _get_df_value(primary, label_map["capital_expenditure"], 0)
            if ocf is not None and capex is not None:
                fcf = ocf - abs(capex)
                record.set_field("free_cash_flow", _inr_to_crores(fcf), self.get_source_name())
                fields.append("free_cash_flow")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 7: Financial Ratios
    # ──────────────────────────────────────────────────────────────────────

    def _extract_financial_ratios(self, ticker: Any, info: Dict,
                                   record: StockDataRecord) -> List[str]:
        """Extract financial ratios from .info and derived calculations."""
        fields = []

        ratio_map = {
            "roe":            ("returnOnEquity",),    # ratio, needs ×100
            "roa":            ("returnOnAssets",),     # ratio, needs ×100
            "debt_to_equity": ("debtToEquity",),      # already a ratio (e.g. 0.5 or 50)
            "current_ratio":  ("currentRatio",),
        }

        for field_name, keys in ratio_map.items():
            for key in keys:
                val = _safe_float(info.get(key))
                if val is not None:
                    # yfinance returns ROE/ROA as decimals (0.25 = 25%)
                    if field_name in ("roe", "roa"):
                        val = round(val * 100, 2)
                    # debtToEquity from yfinance is already percentage-like
                    # (e.g. 50.5 meaning D/E = 0.505)
                    if field_name == "debt_to_equity":
                        val = round(val / 100, 2) if val > 10 else round(val, 2)
                    record.set_field(field_name, val, self.get_source_name())
                    fields.append(field_name)
                    break

        # --- Derived fallbacks when .info ratios are missing ---
        # ROE = Net Income / Total Equity
        if "roe" not in fields:
            net_income = _safe_float(info.get("netIncomeToCommon"))
            equity = _safe_float(info.get("totalStockholderEquity"))
            if net_income and equity and equity != 0:
                val = round(net_income / equity * 100, 2)
                record.set_field("roe", val, self.get_source_name())
                fields.append("roe")

        # ROA = Net Income / Total Assets
        if "roa" not in fields:
            net_income = _safe_float(info.get("netIncomeToCommon"))
            total_assets = _safe_float(info.get("totalAssets"))
            if net_income and total_assets and total_assets != 0:
                val = round(net_income / total_assets * 100, 2)
                record.set_field("roa", val, self.get_source_name())
                fields.append("roa")

        # Current Ratio = Current Assets / Current Liabilities
        if "current_ratio" not in fields:
            ca = _safe_float(info.get("totalCurrentAssets"))
            cl = _safe_float(info.get("totalCurrentLiabilities"))
            if ca and cl and cl != 0:
                val = round(ca / cl, 2)
                record.set_field("current_ratio", val, self.get_source_name())
                fields.append("current_ratio")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 8: Valuation Metrics
    # ──────────────────────────────────────────────────────────────────────

    def _extract_valuation(self, ticker: Any, info: Dict, symbol: str,
                            record: StockDataRecord) -> List[str]:
        """Extract valuation metrics from .info."""
        fields = []

        # Direct from .info
        val_map = {
            "market_cap":       ("marketCap",),
            "enterprise_value": ("enterpriseValue",),
            "pe_ratio":         ("trailingPE",),
            "pe_ratio_forward": ("forwardPE",),
            "peg_ratio":        ("pegRatio",),
            "pb_ratio":         ("priceToBook",),
            "ps_ratio":         ("priceToSalesTrailing12Months",),
            "ev_to_ebitda":     ("enterpriseToEbitda",),
            "ev_to_sales":      ("enterpriseToRevenue",),
            "dividend_yield":   ("dividendYield",),
        }

        for field_name, keys in val_map.items():
            for key in keys:
                val = _safe_float(info.get(key))
                if val is not None:
                    # Convert market cap and EV to crores
                    if field_name in ("market_cap", "enterprise_value"):
                        val = round(val / 1e7, 2)
                    # Dividend yield: yfinance USUALLY gives decimal (0.015 = 1.5%)
                    # but sometimes returns already as percentage (1.5 = 1.5%)
                    elif field_name == "dividend_yield":
                        # If > 1, it's already a percentage; if < 1, multiply
                        val = round(val * 100, 2) if val < 1 else round(val, 2)
                    else:
                        val = round(val, 2)
                    record.set_field(field_name, val, self.get_source_name())
                    fields.append(field_name)
                    break

        # Derived: earnings_yield = EPS / price × 100
        eps = _safe_float(info.get("trailingEps"))
        price = _safe_float(info.get("currentPrice",
                            info.get("regularMarketPrice",
                            info.get("previousClose"))))
        if eps is not None and price is not None and price > 0:
            ey = round(eps / price * 100, 2)
            record.set_field("earnings_yield", ey, self.get_source_name())
            fields.append("earnings_yield")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 9: Shareholding (approximated from major_holders)
    # ──────────────────────────────────────────────────────────────────────

    def _extract_shareholding(self, ticker: Any, symbol: str,
                               record: StockDataRecord) -> List[str]:
        """
        Extract shareholding data from .major_holders and .institutional_holders.

        Note: yfinance major_holders gives institutional vs insider percentages,
        which roughly map to FII/DII and promoter holdings for Indian stocks.
        This is an approximation — BSE filings are the authoritative source.
        """
        fields = []

        try:
            major = ticker.major_holders
            if major is not None and not major.empty:
                # major_holders can have different column structures:
                # Format A: columns=["Value", "Breakdown"] with values like "50.30%"
                # Format B: columns=[0, 1] with numeric index
                # We iterate rows and match patterns in any text column
                for idx in range(len(major)):
                    try:
                        row = major.iloc[idx]
                        row_values = [str(v) for v in row.values]
                        # Find the percentage value and description
                        pct_val = None
                        description = ""
                        for v in row_values:
                            v_clean = v.replace("%", "").strip()
                            f_try = _safe_float(v_clean)
                            if f_try is not None and 0 < f_try <= 100:
                                pct_val = f_try
                            elif len(v) > 5:  # Likely description text
                                description = v.lower()

                        if pct_val is None or not description:
                            continue

                        if "insider" in description or "promoter" in description:
                            record.set_field("promoter_holding", pct_val, self.get_source_name())
                            fields.append("promoter_holding")
                        elif "institution" in description:
                            record.set_field("fii_holding", pct_val, self.get_source_name())
                            fields.append("fii_holding")
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"[{symbol}] major_holders extraction: {e}")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Category 10: Corporate Actions & Events
    # ──────────────────────────────────────────────────────────────────────

    def _extract_corporate_actions(self, ticker: Any, symbol: str,
                                    record: StockDataRecord) -> List[str]:
        """Extract dividends, splits, and earnings dates."""
        fields = []

        # --- Dividends ---
        try:
            dividends = ticker.dividends
            if dividends is not None and not dividends.empty:
                # Most recent dividend
                last_div = dividends.iloc[-1]
                last_div_date = dividends.index[-1]

                record.set_field("dividend_per_share", round(float(last_div), 2),
                                 self.get_source_name())
                fields.append("dividend_per_share")

                ex_date = last_div_date.strftime("%Y-%m-%d") if hasattr(last_div_date, "strftime") else str(last_div_date)
                record.set_field("ex_dividend_date", ex_date, self.get_source_name())
                fields.append("ex_dividend_date")
        except Exception as e:
            logger.debug(f"[{symbol}] Dividends extraction: {e}")

        # --- Stock Splits ---
        try:
            actions = ticker.actions
            if actions is not None and not actions.empty and "Stock Splits" in actions.columns:
                splits = actions[actions["Stock Splits"] != 0]
                if not splits.empty:
                    last_split = splits.iloc[-1]
                    split_ratio = last_split["Stock Splits"]
                    split_date = splits.index[-1].strftime("%Y-%m-%d")
                    record.set_field("stock_split_ratio",
                                     f"1:{int(split_ratio)} on {split_date}",
                                     self.get_source_name())
                    fields.append("stock_split_ratio")
        except Exception as e:
            logger.debug(f"[{symbol}] Splits extraction: {e}")

        # --- Next Earnings Date ---
        try:
            calendar = ticker.calendar
            if calendar is not None:
                # calendar can be a dict or DataFrame depending on yfinance version
                if isinstance(calendar, dict):
                    earnings_dates = calendar.get("Earnings Date", [])
                    if earnings_dates:
                        next_date = earnings_dates[0]
                        if hasattr(next_date, "strftime"):
                            next_date = next_date.strftime("%Y-%m-%d")
                        record.set_field("next_earnings_date", str(next_date),
                                         self.get_source_name())
                        fields.append("next_earnings_date")
                elif isinstance(calendar, pd.DataFrame) and not calendar.empty:
                    # Some versions return a DataFrame
                    if "Earnings Date" in calendar.columns:
                        val = calendar["Earnings Date"].iloc[0]
                        if hasattr(val, "strftime"):
                            val = val.strftime("%Y-%m-%d")
                        record.set_field("next_earnings_date", str(val),
                                         self.get_source_name())
                        fields.append("next_earnings_date")
        except Exception as e:
            logger.debug(f"[{symbol}] Calendar extraction: {e}")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Derived Price Metrics (calculated from price history)
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_derived_metrics(self, record: StockDataRecord) -> List[str]:
        """Calculate all derived price metrics from the price_history already in record."""
        fields = []
        ph = record.price_history
        if not ph or len(ph) < 2:
            return fields

        # price_history is newest-first
        closes = [entry["close"] for entry in ph if entry.get("close")]
        highs = [entry["high"] for entry in ph if entry.get("high")]
        lows = [entry["low"] for entry in ph if entry.get("low")]
        opens = [entry["open"] for entry in ph if entry.get("open")]
        volumes = [entry["volume"] for entry in ph if entry.get("volume")]

        if len(closes) < 2:
            return fields

        latest = closes[0]
        prev = closes[1]

        # daily_return_pct
        if prev and prev > 0:
            ret = round((latest - prev) / prev * 100, 4)
            record.set_field("daily_return_pct", ret, self.get_source_name())
            fields.append("daily_return_pct")

        # return_5d_pct, return_20d_pct, return_60d_pct
        for n, field in [(5, "return_5d_pct"), (20, "return_20d_pct"), (60, "return_60d_pct")]:
            if len(closes) > n and closes[n] and closes[n] > 0:
                ret = round((latest - closes[n]) / closes[n] * 100, 4)
                record.set_field(field, ret, self.get_source_name())
                fields.append(field)

        # day_range_pct = (high - low) / low * 100
        if highs and lows and lows[0] and lows[0] > 0:
            dr = round((highs[0] - lows[0]) / lows[0] * 100, 2)
            record.set_field("day_range_pct", dr, self.get_source_name())
            fields.append("day_range_pct")

        # gap_percentage = (today open - yesterday close) / yesterday close * 100
        if opens and len(closes) > 1 and closes[1] and closes[1] > 0:
            gap = round((opens[0] - closes[1]) / closes[1] * 100, 4)
            record.set_field("gap_percentage", gap, self.get_source_name())
            fields.append("gap_percentage")

        # week_52_high, week_52_low (252 trading days)
        lookback_252 = min(len(highs), 252)
        if lookback_252 > 0:
            w52h = max(highs[:lookback_252])
            w52l = min(lows[:lookback_252])
            record.set_field("week_52_high", round(w52h, 2), self.get_source_name())
            record.set_field("week_52_low", round(w52l, 2), self.get_source_name())
            fields.extend(["week_52_high", "week_52_low"])

            # distance_from_52w_high = (price - 52wH) / 52wH * 100
            if w52h > 0:
                dist = round((latest - w52h) / w52h * 100, 2)
                record.set_field("distance_from_52w_high", dist, self.get_source_name())
                fields.append("distance_from_52w_high")

        # avg_volume_20d and volume_ratio
        if len(volumes) >= 20:
            avg_vol_20 = sum(volumes[:20]) / 20
            record.set_field("avg_volume_20d", round(avg_vol_20), self.get_source_name())
            fields.append("avg_volume_20d")
            if avg_vol_20 > 0:
                vr = round(volumes[0] / avg_vol_20, 2)
                record.set_field("volume_ratio", vr, self.get_source_name())
                fields.append("volume_ratio")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Risk Metrics (beta, sharpe, sortino, drawdown, volatility)
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_risk_metrics(self, ticker: Any,
                                 record: StockDataRecord) -> List[str]:
        """Calculate risk metrics from price history + benchmark (Nifty 50).

        Uses 1-year daily returns. All metrics are annualized.
        Risk-free rate: 6.5% (India 10yr gov bond approximate).
        """
        fields = []
        ph = record.price_history
        if not ph or len(ph) < 60:  # Need at least ~3 months
            return fields

        # Build return series from price history (newest first → reverse)
        closes = [entry["close"] for entry in reversed(ph) if entry.get("close")]
        if len(closes) < 60:
            return fields

        # Use last 252 trading days (1 year) or whatever is available
        lookback = min(len(closes), 252)
        closes_1y = closes[-lookback:]
        returns_1y = np.diff(closes_1y) / closes_1y[:-1]
        returns_1y = returns_1y[np.isfinite(returns_1y)]  # remove inf/nan

        if len(returns_1y) < 30:
            return fields

        rf_daily = 0.065 / 252  # Risk-free rate (daily)
        trading_days = 252

        # rolling_volatility_30d = annualized std of last 30 daily returns
        if len(returns_1y) >= 30:
            vol_30d = np.std(returns_1y[-30:]) * np.sqrt(trading_days)
            record.set_field("rolling_volatility_30d", round(float(vol_30d) * 100, 2),
                             self.get_source_name())
            fields.append("rolling_volatility_30d")

        # sharpe_ratio_1y = (annualized return - rf) / annualized vol
        ann_return = np.mean(returns_1y) * trading_days
        ann_vol = np.std(returns_1y) * np.sqrt(trading_days)
        if ann_vol > 0:
            sharpe = (ann_return - 0.065) / ann_vol
            record.set_field("sharpe_ratio_1y", round(float(sharpe), 4),
                             self.get_source_name())
            fields.append("sharpe_ratio_1y")

        # sortino_ratio_1y = (annualized return - rf) / downside deviation
        downside_returns = returns_1y[returns_1y < rf_daily]
        if len(downside_returns) > 0:
            dd = np.std(downside_returns) * np.sqrt(trading_days)
            record.set_field("downside_deviation_1y", round(float(dd) * 100, 2),
                             self.get_source_name())
            fields.append("downside_deviation_1y")
            if dd > 0:
                sortino = (ann_return - 0.065) / dd
                record.set_field("sortino_ratio_1y", round(float(sortino), 4),
                                 self.get_source_name())
                fields.append("sortino_ratio_1y")

        # max_drawdown_1y = max peak-to-trough fall
        cumulative = np.cumprod(1 + returns_1y)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_dd = float(np.min(drawdowns))
        record.set_field("max_drawdown_1y", round(max_dd * 100, 2),
                         self.get_source_name())
        fields.append("max_drawdown_1y")

        # beta_1y = Cov(stock, benchmark) / Var(benchmark)
        # Fetch Nifty 50 history for beta calculation
        try:
            nifty = yf.Ticker("^NSEI")
            nifty_hist = nifty.history(period="1y", auto_adjust=True)
            if nifty_hist is not None and len(nifty_hist) >= 30:
                nifty_closes = nifty_hist["Close"].values
                nifty_returns = np.diff(nifty_closes) / nifty_closes[:-1]
                nifty_returns = nifty_returns[np.isfinite(nifty_returns)]

                # Align lengths
                min_len = min(len(returns_1y), len(nifty_returns))
                if min_len >= 30:
                    stock_r = returns_1y[-min_len:]
                    bench_r = nifty_returns[-min_len:]
                    covariance = np.cov(stock_r, bench_r)[0][1]
                    bench_var = np.var(bench_r)
                    if bench_var > 0:
                        beta = covariance / bench_var
                        record.set_field("beta_1y", round(float(beta), 4),
                                         self.get_source_name())
                        fields.append("beta_1y")
        except Exception as e:
            logger.debug(f"Beta calculation failed: {e}")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Analyst Data
    # ──────────────────────────────────────────────────────────────────────

    def _extract_analyst_data(self, ticker: Any, info: Dict,
                               record: StockDataRecord) -> List[str]:
        """Extract analyst ratings, target prices, and coverage from yfinance."""
        fields = []

        # Target price from .info (most reliable)
        target = _safe_float(info.get("targetMeanPrice",
                             info.get("targetMedianPrice")))
        if target is not None:
            record.set_field("target_price_consensus", round(target, 2),
                             self.get_source_name())
            fields.append("target_price_consensus")

        # Number of analysts from .info
        num = _safe_int(info.get("numberOfAnalystOpinions"))
        if num is not None:
            record.set_field("num_analysts", num, self.get_source_name())
            fields.append("num_analysts")

        # Recommendation from .info
        rec_key = info.get("recommendationKey")  # e.g. "buy", "hold", "strong_buy"
        if rec_key:
            record.set_field("analyst_rating_consensus", rec_key,
                             self.get_source_name())
            fields.append("analyst_rating_consensus")

        # If .info didn't have it, try .analyst_price_targets
        if "target_price_consensus" not in fields:
            try:
                apt = ticker.analyst_price_targets
                if apt is not None and isinstance(apt, dict):
                    mean_t = _safe_float(apt.get("mean", apt.get("current")))
                    if mean_t is not None:
                        record.set_field("target_price_consensus",
                                         round(mean_t, 2), self.get_source_name())
                        fields.append("target_price_consensus")
            except Exception as e:
                logger.debug(f"analyst_price_targets: {e}")

        # If .info didn't have recommendation, try .recommendations
        if "analyst_rating_consensus" not in fields:
            try:
                recs = ticker.recommendations
                if recs is not None and not recs.empty:
                    # Most recent recommendation
                    latest_rec = recs.iloc[-1]
                    grade = None
                    for col in ["To Grade", "toGrade", "Action"]:
                        if col in recs.columns:
                            grade = str(latest_rec[col])
                            break
                    if grade:
                        record.set_field("analyst_rating_consensus", grade,
                                         self.get_source_name())
                        fields.append("analyst_rating_consensus")
            except Exception as e:
                logger.debug(f"recommendations: {e}")

        return fields

    # ──────────────────────────────────────────────────────────────────────
    # Global market data (standalone utility)
    # ──────────────────────────────────────────────────────────────────────

    async def extract_global_market_data(self) -> Dict[str, Any]:
        """
        Fetch global market indices, commodities, and FX rates from yfinance.

        Returns a flat dict with V2 field names as keys:
            sp500_return_1d, nasdaq_return_1d, usdinr_rate,
            crude_brent_price, gold_price, copper_price,
            india_vix, nifty_50_return_1m
        """
        if not YFINANCE_AVAILABLE:
            return {}

        result: Dict[str, Any] = {}

        for name, ticker_sym in GLOBAL_TICKERS.items():
            try:
                ticker = yf.Ticker(ticker_sym)
                hist = ticker.history(period="1mo", auto_adjust=True)
                if hist is None or hist.empty:
                    continue

                latest_close = _safe_float(hist["Close"].iloc[-1])

                if name == "sp500" and len(hist) >= 2:
                    prev = _safe_float(hist["Close"].iloc[-2])
                    if latest_close and prev and prev > 0:
                        result["sp500_return_1d"] = round((latest_close - prev) / prev * 100, 4)

                elif name == "nasdaq" and len(hist) >= 2:
                    prev = _safe_float(hist["Close"].iloc[-2])
                    if latest_close and prev and prev > 0:
                        result["nasdaq_return_1d"] = round((latest_close - prev) / prev * 100, 4)

                elif name == "usdinr":
                    if latest_close:
                        result["usdinr_rate"] = round(latest_close, 2)

                elif name == "crude_brent":
                    if latest_close:
                        result["crude_brent_price"] = round(latest_close, 2)

                elif name == "gold":
                    if latest_close:
                        result["gold_price"] = round(latest_close, 2)

                elif name == "copper":
                    if latest_close:
                        result["copper_price"] = round(latest_close, 2)

                elif name == "india_vix":
                    if latest_close:
                        result["india_vix"] = round(latest_close, 2)

                elif name == "nifty_50" and len(hist) >= 2:
                    first = _safe_float(hist["Close"].iloc[0])
                    if latest_close and first and first > 0:
                        result["nifty_50_return_1m"] = round(
                            (latest_close - first) / first * 100, 2
                        )

            except Exception as e:
                logger.warning(f"Global ticker {name} ({ticker_sym}) failed: {e}")

        logger.info(f"Global market data: {len(result)} fields fetched")
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Standalone full report (all data as a single dict)
    # ──────────────────────────────────────────────────────────────────────

    async def extract_full_report(self, symbol: str) -> Dict[str, Any]:
        """
        Extract all available data for a symbol and return as a single dict.

        Useful for standalone usage, debugging, and offline loading.
        Does NOT require a StockDataRecord.
        """
        record = StockDataRecord(symbol=symbol, company_name="")
        extraction = await self.extract(symbol, record)

        report = {
            "symbol": symbol,
            "extraction_status": extraction.status.value,
            "fields_extracted": extraction.fields_extracted,
            "fields_failed": extraction.fields_failed,
            "field_count": len(extraction.fields_extracted),
            "total_possible": len(self.get_provided_fields()),
            "coverage_pct": round(
                len(extraction.fields_extracted) / len(self.get_provided_fields()) * 100, 1
            ),
            "error": extraction.error_message,
            "duration_ms": extraction.duration_ms,
            "data": record.to_dict(),
            "price_history_length": len(record.price_history),
            "quarterly_results_count": len(record.quarterly_results),
            "annual_results_count": len(record.annual_results),
        }

        return report
